"""Fetch grocery offers and save the results to JSON."""

import copy
import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

FETCH_DATA = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "offers_dataset.json"

# Shop configuration

USER_AGENT = "AngebotFinderDE-Learning/0.1"
SOURCES = {
    "REWE": "https://www.marktguru.de/r/rewe",
    "EDEKA": "https://www.marktguru.de/r/edeka",
    "ALDI Nord": "https://www.aktionspreis.de/prospekt/aldi-nord-angebote",
    "ALDI Süd": "https://www.aldi-sued.de/angebote",
    "PENNY": "https://www.marktguru.de/r/penny",
    "Lidl": "https://www.marktguru.de/r/lidl",
    "Kaufland": "https://filiale.kaufland.de/angebote.html",
    "Netto Marken-Discount": "https://www.marktguru.de/r/netto-marken-discount",
}
page_cache = {}
robots_cache = {}

SCHEMA_VERSION = "1.0.0"
PARSER_VERSION = "notebook-0.2"
STORE_IDS = {
    "REWE": "rewe", "EDEKA": "edeka", "ALDI Nord": "aldi-nord",
    "ALDI Süd": "aldi-sued", "PENNY": "penny", "Lidl": "lidl",
    "Kaufland": "kaufland", "Netto Marken-Discount": "netto-marken-discount",
}


# Fetching pages

def crawler_allowed(text, url):
    groups, agents, directives = [], [], []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            if directives:
                groups.append((agents, directives))
                agents, directives = [], []
            agents.append(value.lower())
        elif key in ("allow", "disallow") and agents:
            directives.append((key, value))
    if agents:
        groups.append((agents, directives))
    if not groups:
        raise ValueError("No crawler groups found; inspect the rules manually.")
    agent = USER_AGENT.lower()
    specific = [a for names, _ in groups for a in names if a != "*" and a in agent]
    selected = max(specific, key=len) if specific else "*"
    parts = urlsplit(url)
    target = parts.path + ("?" + parts.query if parts.query else "")
    matches = []
    for names, rules in groups:
        if selected not in names:
            continue
        for kind, path in rules:
            if not path:
                continue
            terminal = path.endswith("$")
            pattern = path[:-1] if terminal else path
            pattern = "^" + re.escape(pattern).replace(r"\*", ".*") + ("$" if terminal else "")
            if re.search(pattern, target):
                matches.append((len(path.replace("*", "").rstrip("$")), kind == "allow"))
    return max(matches)[1] if matches else True


def fetch_shop(store, refresh=False):
    if store in page_cache and not refresh:
        return page_cache[store]
    url = SOURCES[store]
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    result = {"store": store, "url": url, "fetched_at": None,
              "status": "source_failed", "http_status": None, "message": "", "html": None}
    try:
        if origin not in robots_cache:
            robots = requests.get(origin + "/robots.txt", headers={"User-Agent": USER_AGENT},
                                  timeout=25, allow_redirects=False)
            if robots.status_code != 200 or "<html" in robots.text[:1000].lower():
                result["message"] = f"Crawler rules unavailable: HTTP {robots.status_code}"
                page_cache[store] = result
                return result
            robots_cache[origin] = robots.text
        if not crawler_allowed(robots_cache[origin], url):
            result.update(status="robots_disallowed", message="Configured path is disallowed")
        else:
            response = requests.get(url, headers={"User-Agent": USER_AGENT},
                                    timeout=30, allow_redirects=False)
            result.update(http_status=response.status_code,
                          fetched_at=datetime.now(timezone.utc).isoformat())
            if response.status_code in (401, 403, 429):
                result.update(status="blocked", message=f"HTTP {response.status_code}; no bypass attempted")
            elif 300 <= response.status_code < 400:
                result.update(status="redirect_requires_review", message=response.headers.get("Location", ""))
            elif response.status_code != 200:
                result["message"] = f"HTTP {response.status_code}"
            elif "text/html" not in response.headers.get("Content-Type", ""):
                result["message"] = "Unexpected content type"
            else:
                result.update(status="fetched", html=response.content.decode(response.apparent_encoding or "utf-8", errors="replace"), message="HTML fetched; extraction still needs checking")
    except (requests.RequestException, ValueError) as error:
        result["message"] = str(error)
    page_cache[store] = result
    return result


# Building and validating offer records

def text_of(node, selector=None):
    selected = node.select_one(selector) if selector else node
    return selected.get_text(" ", strip=True) if selected else None


def money(text):
    if text is None:
        return None
    cleaned = str(text).replace("\xa0", " ").strip()
    # Require a whole price, never grab a discount, old price, or unit-price substring.
    match = re.fullmatch(r"(\d+)[,.](\d{2})\s*€?", cleaned)
    if not match:
        return None
    value = Decimal(match[1] + "." + match[2])
    return format(value, ".2f") if value > 0 else None


def section_context(node):
    for parent in node.parents:
        if parent.name in ("section", "article") or "k-product-section" in parent.get("class", []):
            headers = parent.select("h1,h2,h3,.k-product-section__header")
            return " | ".join(h.get_text(" ", strip=True) for h in headers[:4])
    return None


def make_record(page, node, name, price, method, **fields):
    record = dict(store=page["store"], branch_region=None, product_name=name,
                  brand=None, variant=None, offer_price=price, currency="EUR",
                  price_quantity_basis=None, pack_size_text=None, net_weight_g=None,
                  drained_weight_g=None, unit_price=None, unit_price_basis=None,
                  unit_price_text=None, valid_from=None, valid_to=None,
                  validity_text=None, requires_loyalty=None, loyalty_conditions=None,
                  conditions_text=None, product_url=None, source_url=page["url"],
                  fetched_at=page["fetched_at"], extraction_method=method,
                  fetch_method=page.get("fetch_method", "requests"),
                  verification="candidate: inspect source evidence",
                  source_text=text_of(node),
                  section_context=section_context(node),
                  value_origin={"offer_price": "published", "calculated_values": []})
    record.update(fields)
    return record


def unique_records(records):
    output, seen = [], set()
    for record in records:
        key = (record["store"], record["product_name"], record["offer_price"],
               record["pack_size_text"], record["requires_loyalty"], record["section_context"])
        if key not in seen:
            seen.add(key)
            output.append(record)
    return output


def stable_id(prefix, *values):
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def normalize_text(value):
    # Search aid only: this does not translate or classify a product.
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"\w+", value))


def decimal_string(value):
    return format(value.normalize(), "f")


def parse_quantity(pack_text, source_text):
    quantity = dict(pack_count=None, amount=None, unit=None, basis=None,
                    net_weight_g=None, volume_ml=None, drained_weight_g=None,
                    price_basis=None, evidence=None)
    pack = (pack_text or "").replace("\xa0", " ").strip()
    # Accept only simple, explicit pack sizes. Ranges and multipacks stay unknown.
    match = re.fullmatch(
        r"(?:je\s+)?(\d+(?:[.,]\d+)?)\s*-?\s*(kg|g|ml|l)"
        r"(?:\s*-\s*(?:Packg\.?|Pckg\.?|Btl\.?|Becher|Glas|Dose|Fl\.?|Netz|Sack|Stück))?",
        pack, re.IGNORECASE)
    if match:
        amount = Decimal(match[1].replace(",", "."))
        unit = match[2].lower()
        if amount > 0:
            quantity.update(pack_count=1, amount=decimal_string(amount), unit=unit,
                            basis="net_weight" if unit in ("g", "kg") else "volume",
                            price_basis="per_pack", evidence=pack)
            if unit in ("g", "kg"):
                quantity["net_weight_g"] = decimal_string(amount * (1000 if unit == "kg" else 1))
            else:
                quantity["volume_ml"] = decimal_string(amount * (1000 if unit == "l" else 1))
    elif re.fullmatch(r"je\s+(?:kg|l)", pack, re.IGNORECASE):
        quantity.update(price_basis="per_kg" if pack.lower().endswith("kg") else "per_l", evidence=pack)
    drained = re.findall(
        r"(?:Abtropfgewicht\s*:?\s*(\d+(?:[.,]\d+)?)\s*g|"
        r"(\d+(?:[.,]\d+)?)\s*g\s*Abtropfgewicht)", source_text or "", re.IGNORECASE)
    if len(drained) == 1:
        quantity["drained_weight_g"] = decimal_string(Decimal(next(v for v in drained[0] if v).replace(",", ".")))
    return quantity


def parse_published_unit_prices(raw):
    # Preserve multiple standard/card or range prices raw; never choose one silently.
    raw = raw or ""
    patterns = [
        r"(?<![\d.,])(1|100)\s*(kg|g|l|ml)\s*=\s*€?\s*(\d+[.,]\d{2})(?![\d.,])",
        r"(?<![\d.,])(\d+[.,]\d{2})\s*€\s*/\s*(1|100)\s*(kg|g|l|ml)\b",
    ]
    found = []
    for match in re.finditer(patterns[0], raw, re.IGNORECASE):
        found.append({"price": match[3].replace(",", "."), "currency": "EUR",
                      "basis_amount": match[1], "basis_unit": match[2].lower()})
    for match in re.finditer(patterns[1], raw, re.IGNORECASE):
        found.append({"price": match[1].replace(",", "."), "currency": "EUR",
                      "basis_amount": match[2], "basis_unit": match[3].lower()})
    # Ranges may otherwise look like a single price at the start of the range.
    ambiguous = bool(re.search(r"\d+[.,]\d+\s*[-–]\s*\d", raw))
    return found, bool(len(found) == 1 and not ambiguous)


def explicit_iso_date(raw):
    # Do not assign a year from the fetch timestamp to a yearless weekly heading.
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value).isoformat()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+", value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
    except ValueError:
        pass
    return None


def enrich_record(original):
    record = copy.deepcopy(original)
    record.update(schema_version=SCHEMA_VERSION, parser_version=PARSER_VERSION,
                  store_id=STORE_IDS[record["store"]], country_code="DE", source_language="de",
                  canonical_product_id=None, gtin=None, dietary_tags=None,
                  availability="unknown", branch_id=None, postal_code=None,
                  coverage_scope="configured_page_only", geographic_scope_confirmed=False)
    record.setdefault("category", None)
    record["source_id"] = stable_id("src", record["store_id"], record["source_url"])
    record["snapshot_id"] = stable_id("snap", record["source_id"], record.get("fetched_at"))
    record["search_text"] = normalize_text(" ".join(
        str(record.get(key) or "") for key in ("product_name", "brand", "variant")))
    record["quantity"] = parse_quantity(record.get("pack_size_text"), record.get("source_text"))
    quantity = record["quantity"]
    for field in ("net_weight_g", "drained_weight_g"):
        record[field] = quantity[field]
    record["price_quantity_basis"] = quantity["price_basis"]
    published, unambiguous = parse_published_unit_prices(record.get("unit_price_text"))
    record["published_unit_prices"] = published
    record["unit_price"] = published[0]["price"] if unambiguous else None
    record["unit_price_basis"] = ({"amount": published[0]["basis_amount"],
                                    "unit": published[0]["basis_unit"], "weight_basis": None}
                                   if unambiguous else None)
    record.setdefault("price_type", "loyalty" if record.get("requires_loyalty") is True else "unspecified")
    record.setdefault("deposit_price", None)
    record.setdefault("deposit_included", None)
    record["minimum_purchase_quantity"] = None
    record["maximum_purchase_quantity"] = None
    record.setdefault("benefits", None)
    record.setdefault("old_price", None)
    record.setdefault("retailer_product_id", None)
    record["first_seen_at"] = None  # Requires persistent history, not one fetch.
    record["last_seen_at"] = None
    record["content_hash"] = stable_id("content", record.get("source_text"), record.get("section_context"))
    record["published_validity_fields"] = {"valid_from": record.get("valid_from"), "valid_to": record.get("valid_to")}
    record["valid_from"] = explicit_iso_date(record.get("valid_from"))
    record["valid_to"] = explicit_iso_date(record.get("valid_to"))
    record["timezone"] = "Europe/Berlin"
    record["validity_precision"] = "full_dates" if record["valid_from"] and record["valid_to"] else "unknown_or_partial"
    record["is_advertised_offer"] = True if "visible" in record["extraction_method"] else None
    record["calculated_unit_price"] = None
    # Only compare plain single-pack mass/volume quantities, without drained-weight ambiguity.
    try:
        price_value = Decimal(record["offer_price"])
        price_is_valid = price_value.is_finite() and price_value > 0
    except (InvalidOperation, TypeError):
        price_is_valid = False
    if (quantity["price_basis"] == "per_pack" and not quantity["drained_weight_g"]
            and record["is_advertised_offer"] is True and price_is_valid):
        amount = quantity["net_weight_g"] or quantity["volume_ml"]
        record["calculated_unit_price"] = {
            "price": decimal_string(Decimal(record["offer_price"]) * 100 / Decimal(amount)),
            "currency": record["currency"], "basis_amount": "100",
            "basis_unit": "g" if quantity["net_weight_g"] else "ml",
            "weight_basis": quantity["basis"],
            "formula": "offer_price * 100 / quantity_in_g_or_ml",
            "rounding": "Decimal context precision; no extra display rounding",
        }
    record["value_origin"] = {
        "offer_price": "published", "currency": "retailer_adapter_default",
        "quantity": "parsed_from_explicit_pack_text" if quantity["amount"] else "unknown",
        "published_unit_prices": "parsed_from_published_text",
        "calculated_unit_price": "calculated" if record["calculated_unit_price"] else "unknown",
        "search_text": "normalized_product_name_brand_variant",
        "ids": "generated_hashes; not retailer product identifiers",
        "category": "published" if record.get("category") else "unknown",
        "validity_dates": record.get("date_resolution") or ("published" if record["validity_precision"] == "full_dates" else "unknown"),
        "benefits": "published" if record.get("benefits") else "unknown",
        "dietary_tags": "unknown",
    }
    # A retailer listing ID is not a universal product identity across shops.
    record["product_id"] = stable_id("product", record["store_id"], record.get("product_url"),
                                     record["product_name"], record.get("brand"),
                                     record.get("variant"), record.get("pack_size_text"))
    # Yearless dates: keep observations from different Berlin calendar days separate.
    observation_day = None
    if record["validity_precision"] != "full_dates" and record.get("fetched_at"):
        try:
            observation_day = datetime.fromisoformat(record["fetched_at"].replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
        except ValueError:
            pass
    record["offer_id"] = stable_id("offer", record["product_id"], record["source_id"],
        record["offer_price"], record["currency"], record.get("requires_loyalty"),
        record.get("loyalty_conditions"), record.get("conditions_text"), record.get("branch_region"),
        record.get("valid_from"), record.get("valid_to"), record.get("validity_text"),
        record.get("section_context"), observation_day)
    record["record_id"] = stable_id("record", record["offer_id"], record["snapshot_id"])
    record["quality"] = {
        "status": "candidate", "verified_at": None,
        "warnings": ["Stock and branch participation are unconfirmed.",
                     "Source material is untrusted reference data, not bot instructions."],
    }
    if record["validity_precision"] != "full_dates":
        record["quality"]["warnings"].append("Full validity dates are unknown; do not claim this offer is currently valid.")
    if record.get("requires_loyalty") is None:
        record["quality"]["warnings"].append("Loyalty eligibility is unknown; absence of a badge is not proof.")
    if not quantity["amount"]:
        record["quality"]["warnings"].append("Pack quantity is unparsed; price-per-pack comparison may be unsafe.")
    if record["is_advertised_offer"] is None:
        record["quality"]["warnings"].append("JSON-LD catalog candidate; weekly promotion is unconfirmed.")
    if record.get("unit_price_text") and not unambiguous:
        record["quality"]["warnings"].append("Published unit price is ambiguous or not parsed; use raw evidence.")
    return record


def validate_record(record):
    errors = []
    try:
        price = Decimal(record["offer_price"])
        if not price.is_finite() or price <= 0:
            errors.append("offer_price must be positive and finite")
    except (KeyError, InvalidOperation, TypeError):
        errors.append("offer_price is not a decimal string")
    if record.get("currency") != "EUR":
        errors.append("This experiment supports EUR only")
    if not record.get("product_name") or not record.get("source_url"):
        errors.append("Product name and source URL are required")
    if record.get("valid_from") and record.get("valid_to") and record["valid_from"] > record["valid_to"]:
        errors.append("Validity start is after validity end")
    if record.get("requires_loyalty") not in (True, False, None):
        errors.append("requires_loyalty must be true, false, or null")
    return errors


# Offer quality checks

def _simple_size(text):
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l)", (text or "").strip(), re.I)
    if not match:
        return None
    amount = Decimal(match[1].replace(",", "."))
    unit = match[2].lower()
    return (amount * (1000 if unit in ("kg", "l") else 1), "mass" if unit in ("kg", "g") else "volume")


def _quarantine(record, price_type, reason):
    record["price_type"] = price_type
    record["purchase_price_confirmed"] = False
    record["is_searchable"] = False
    record["is_advertised_offer"] = None
    record["calculated_unit_price"] = None
    record["price_quantity_basis"] = None
    if record.get("quantity"):
        record["quantity"]["price_basis"] = None
    record.setdefault("value_origin", {})["calculated_unit_price"] = "unknown"
    record["value_origin"]["offer_price"] = "published reference amount; purchase price unconfirmed"
    record.setdefault("quality", {})["status"] = "needs_review"
    warnings = record["quality"].setdefault("warnings", [])
    if reason not in warnings:
        warnings.append(reason)


def apply_offer_quality(records):
    """Remove repeated offer cards and flag unclear purchase prices."""
    grouped = defaultdict(list)
    for original in records:
        record = copy.deepcopy(original)
        key = tuple(record.get(k) for k in (
            "source_id", "fetched_at", "store", "product_name", "brand", "variant",
            "offer_price", "currency", "pack_size_text", "requires_loyalty",
            "loyalty_conditions", "conditions_text", "valid_from", "valid_to",
            "branch_region", "source_text"))
        # Do not combine records whose evidence is missing.
        if not record.get("source_text"):
            key += (record.get("record_id"),)
        grouped[key].append(record)
    output = []
    for duplicates in grouped.values():
        duplicates.sort(key=lambda r: (bool(r.get("validity_text")), bool(r.get("section_context"))), reverse=True)
        record = duplicates[0]
        duplicate_ids = set(record.get("duplicate_record_ids", []))
        for other in duplicates[1:]:
            duplicate_ids.update(other.get("duplicate_record_ids", []))
            if other.get("record_id") != record.get("record_id"):
                duplicate_ids.add(other["record_id"])
        if duplicate_ids:
            record["duplicate_record_ids"] = sorted(duplicate_ids)
        record["is_searchable"] = (record.get("is_advertised_offer") is True
                                   and not record.get("quality", {}).get("validation_errors"))
        output.append(record)
    for record in output:
        if urlsplit(record.get("source_url", "")).hostname != "www.aktionspreis.de":
            continue
        pack = record.get("pack_size_text") or ""
        if re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:WL|Waschladungen?)", pack.strip(), re.I):
            _quarantine(record, "unit_reference", "Amount is per wash, not the purchase price of a pack.")
            continue
        size = _simple_size(pack)
        if not size or size[0] != 1000:
            continue
        for peer in output:
            peer_size = _simple_size(peer.get("pack_size_text"))
            if (peer is record or peer.get("source_id") != record.get("source_id")
                    or peer.get("fetched_at") != record.get("fetched_at")
                    or peer.get("product_name") != record.get("product_name")
                    or not peer_size or peer_size[1] != size[1] or peer_size[0] <= size[0]):
                continue
            reference = (Decimal(peer["offer_price"]) * size[0] / peer_size[0]).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            if reference == Decimal(record["offer_price"]):
                _quarantine(record, "ambiguous_price_basis",
                            "Possible normalized unit-price listing beside a larger pack; purchase price requires review.")
                break
    return output


def prepare_report(original):
    report = copy.deepcopy(original)
    report["records"] = [enrich_record(record) for record in report.get("records", [])]
    for record in report["records"]:
        record["quality"]["validation_errors"] = validate_record(record)
    report["records"] = apply_offer_quality(report["records"])
    return report


def build_dataset(reports):
    """App-friendly offers plus source coverage and source text evidence."""
    sources, offers, seen = [], [], set()
    for store, url in SOURCES.items():
        report = reports.get(store)
        source = dict(source_id=stable_id("src", STORE_IDS[store], url),
                      store_id=STORE_IDS[store], store=store, source_url=url,
                      source_provider=urlsplit(url).hostname,
                      source_type="third_party_aggregator" if urlsplit(url).hostname in ("www.marktguru.de", "www.aktionspreis.de") else "retailer",
                      status="not_checked", fetched_at=None, http_status=None,
                      message="This source has not been checked in this run.", record_count=0,
                      coverage_scope="configured_page_only", branch_region=None,
                      page_context=None)
        if report:
            source.update(status=report["status"], fetched_at=report.get("fetched_at"),
                          http_status=report.get("http_status"), message=report.get("message"),
                          record_count=len(report.get("records", [])), page_context=report.get("page_context"))
            for original in report.get("records", []):
                record = enrich_record(original)
                record["quality"]["validation_errors"] = validate_record(record)
                if record["record_id"] in seen:
                    continue
                seen.add(record["record_id"])
                record.pop("source_html", None)
                offers.append(record)
        sources.append(source)
    offers = apply_offer_quality(offers)
    for source in sources:
        source["record_count"] = sum(r["source_id"] == source["source_id"] for r in offers)
    return dict(schema_version=SCHEMA_VERSION, generated_at=datetime.now(timezone.utc).isoformat(),
                currency="EUR", offer_timezone="Europe/Berlin", offers=offers, sources=sources,
                limitations=["Only configured pages are covered, not every branch or every offer.",
                             "Candidate records are not automatically verified or currently valid.",
                             "No stock availability is confirmed.",
                             "Unknown conditions must not be treated as unrestricted."])


# Shop parsers

def extract_aldi_sued(soup, page):
    records = []
    for tile in soup.select('[data-test="product-tile"]'):
        context = section_context(tile)
        if not context or "Wochenangebote" not in context:
            continue
        name = text_of(tile, '[data-test="product-tile__name"]')
        price = money(text_of(tile, ".base-price__discounted") or text_of(tile, ".base-price__regular"))
        if not name or price is None:
            continue
        link = tile.select_one("a.product-tile__link[href]")
        records.append(make_record(
            page, tile, name, price, "ALDI Süd visible weekly product tile",
            old_price=money(text_of(tile, ".base-price__was-price del")),
            brand=text_of(tile, '[data-test="product-tile__brandname"]'),
            pack_size_text=text_of(tile, '[data-test="product-tile__unit-of-measurement"]'),
            unit_price_text=text_of(tile, '[data-test="product-tile__comparison-price"]'),
            validity_text=context,
            product_url=urljoin(page["url"], link["href"]) if link else None))
    return unique_records(records)


def extract_kaufland(soup, page):
    records = []
    for tile in soup.select(".k-product-tile"):
        # Multi-buy prices require a dedicated quantity model in a later lesson.
        if tile.select_one(".k-price-tag__bby-message"):
            continue
        name = " ".join(filter(None, [text_of(tile, ".k-product-tile__title"),
                                       text_of(tile, ".k-product-tile__subtitle")]))
        for selector, card in [(".k-product-tile__pricetags-normal", None),
                               (".k-product-tile__pricetags-loyalty", True)]:
            group = tile.select_one(selector)
            if not group:
                continue
            price = money(text_of(group, ".k-price-tag__price"))
            if not name or price is None:
                continue
            records.append(make_record(
                page, tile, name, price, "Kaufland visible product tile",
                old_price=money(text_of(group, ".k-price-tag__old-price-line-through")),
                pack_size_text=text_of(tile, ".k-product-tile__unit-price"),
                unit_price_text=text_of(tile, ".k-product-tile__base-price"),
                validity_text=section_context(tile), requires_loyalty=card,
                loyalty_conditions=text_of(group, ".k-price-tag__with-card") if card else None,
                conditions_text=text_of(tile)))
    return unique_records(records)


def rewe_validity(week, label):
    """Resolve yearless dates only using the card's explicitly published ISO week."""
    week_match = re.fullmatch(r"(\d{4})/(\d{1,2})", week or "")
    dates_match = re.search(r"(\d{1,2})\.(\d{1,2})\.\s*bis\s*(\d{1,2})\.(\d{1,2})\.", label or "")
    if not week_match or not dates_match:
        return None, None
    try:
        monday = date.fromisocalendar(int(week_match[1]), int(week_match[2]), 1)
    except ValueError:
        return None, None
    days = [monday + timedelta(days=i) for i in range(7)]
    start = [day for day in days if (day.day, day.month) == (int(dates_match[1]), int(dates_match[2]))]
    end = [day for day in days if (day.day, day.month) == (int(dates_match[3]), int(dates_match[4]))]
    if len(start) == len(end) == 1 and start[0] <= end[0]:
        return start[0].isoformat(), end[0].isoformat()
    return None, None


def extract_rewe_saved_page(soup, page):
    records = []
    date_label = text_of(soup, '#sos-week-tabs__tab-0 .sos-tabs__tab-subtitle')
    loyalty_terms = text_of(soup, '#sop-loyalty-terms')
    for tile in soup.select('section[id$="-current-week"] article.cor-offer-renderer-tile'):
        link = tile.select_one('a[data-offer-title]')
        price = money(text_of(tile, '.cor-offer-price__tag-price'))
        if not link or not price:
            continue
        parts = [text_of(part).lstrip(', ').strip()
                 for part in tile.select('.cor-offer-information__additional')]
        pack = next((part for part in parts if re.match(r'^je\s+\d', part)), None)
        unit_text = next((part for part in parts if re.search(r'\([^)]*=.*\)', part)), None)
        variants = [part for part in parts if part != pack and part != unit_text and 'Abtropfgewicht' not in part]
        week = link.get('data-offer-week')
        start, end = rewe_validity(week, date_label)
        bonus = money(text_of(tile, '.cor-loyalty-badge'))
        record = make_record(
            page, tile, link['data-offer-title'], price, 'REWE visible offer card',
            retailer_product_id=link.get('data-offer-nan'),
            variant='; '.join(variants) or None,
            category=text_of(tile.find_parent('section'), 'h2'),
            pack_size_text=pack, unit_price_text=unit_text,
            validity_text=date_label, valid_from=start, valid_to=end,
            published_offer_week=week,
            date_resolution='published ISO week plus displayed day/month range' if start else None,
            price_type='advertised_checkout_price',
            benefits=[dict(type='loyalty_credit', amount=bonus, currency='EUR',
                           program='REWE Bonus', requires_loyalty=True, conditions=loyalty_terms)] if bonus else None,
            conditions_text='; '.join(parts),
            source_footnotes=[text_of(note) for note in soup.select('.sop-footnotes_item')])
        records.append(record)
    return unique_records(records)



def extract_marktguru(soup, page):
    """Only cards for the configured retailer; explicitly expired cards are excluded."""
    retailer_path = urlsplit(page["url"]).path.rstrip("/")
    records = []
    for card in soup.select("li.offer-list-item"):
        retailer = card.select_one("dd.retailer-name a[href]")
        if not retailer or retailer["href"].rstrip("/") != retailer_path:
            continue
        if "expired" in card.get("class", []) or card.select_one(".time-over"):
            continue
        raw_price = text_of(card, "dd.price span.price")
        price = money(raw_price.removeprefix("€").strip()) if raw_price else None
        name = text_of(card, "h3")
        if not name or not price:
            continue
        description = text_of(card, ".info")
        packs = re.findall(r"\bje\s+\d+(?:[,.]\d+)?\s*-?\s*(?:kg|g|ml|l)\s*-?\s*"
                           r"(?:Pckg\.?|Packg\.?|Btl\.?|Glas|Dose|Fl\.?|Becher|Netz|Schale)\b", description or "", re.I)
        old = text_of(card, "s.old-price")
        records.append(make_record(
            page, card, name, price, "marktguru visible offer card",
            brand=text_of(card, "dd.brand"),
            pack_size_text=packs[0] if len(packs) == 1 else None,
            unit_price_text=text_of(card, ".info strong"),
            validity_text=text_of(card, "dd.valid"), conditions_text=description,
            old_price=money(old.removeprefix("€").strip()) if old else None,
            source_provider="marktguru", source_type="third_party_aggregator",
            source_reported_expired=False,
            description_truncated=bool(description and description.endswith(("...", "…")))))
    return unique_records(records)


def extract_aktionspreis(soup, page):
    records = []
    label_node = soup.find(string=lambda value: value and "Angebote vom" in value)
    label = text_of(label_node.parent) if label_node else None
    period = re.search(r"(\d{2})\.(\d{2})\.\s*-\s*(\d{2})\.(\d{2})\.(\d{4})", label or "")
    start = end = None
    if period:
        try:
            year = int(period[5])
            start = date(year - (int(period[2]) > int(period[4])), int(period[2]), int(period[1])).isoformat()
            end = date(year, int(period[4]), int(period[3])).isoformat()
        except ValueError:
            start = end = None
    for card in soup.select(".produkt_box"):
        name = text_of(card, ".beschreibung b")
        prices = [money(text_of(b)) for b in card.select("b") if money(text_of(b)) is not None]
        if not name or len(prices) != 1:
            continue
        quantity = card.find("div", style=lambda value: value and "float:left" in value and "margin-top" in value)
        records.append(make_record(
            page, card, name, prices[0], "Aktionspreis visible offer card",
            pack_size_text=text_of(quantity) if quantity else None,
            unit_price_text=text_of(card, ".grundpreis"), validity_text=label,
            valid_from=start, valid_to=end,
            source_provider="Aktionspreis", source_type="third_party_aggregator",
            conditions_text=text_of(card)))
    return unique_records(records)


def extract_rewe(soup, page):
    # Direct HTML is only supported for the optional user-saved-file importer.
    if urlsplit(page["url"]).hostname == "www.marktguru.de":
        return extract_marktguru(soup, page)
    return extract_rewe_saved_page(soup, page)


def extract_edeka(soup, page):
    return extract_marktguru(soup, page)


def extract_aldi_nord(soup, page):
    return extract_aktionspreis(soup, page)


def extract_penny(soup, page):
    return extract_marktguru(soup, page)


def extract_lidl(soup, page):
    return extract_marktguru(soup, page)


def extract_netto(soup, page):
    return extract_marktguru(soup, page)


EXTRACTORS = {
    "REWE": extract_rewe, "EDEKA": extract_edeka,
    "ALDI Nord": extract_aldi_nord, "ALDI Süd": extract_aldi_sued,
    "PENNY": extract_penny, "Lidl": extract_lidl,
    "Kaufland": extract_kaufland, "Netto Marken-Discount": extract_netto,
}


def extract_page(page):
    report = {key: value for key, value in page.items() if key != "html"}
    report.update(records=[], page_context=None, inspection={})
    if page["status"] != "fetched":
        return report
    soup = BeautifulSoup(page["html"], "html.parser")
    visible = BeautifulSoup(page["html"], "html.parser")
    for tag in visible.select("script,style,template,noscript"):
        tag.decompose()
    report["page_context"] = visible.get_text(" ", strip=True)
    report["inspection"] = {
        "title": text_of(soup.title) if soup.title else None,
        "headings": [text_of(h) for h in soup.select("h1,h2,h3")[:30]],
        "jsonld_blocks": len(soup.select('script[type="application/ld+json"]')),
        "brochure_links": list(dict.fromkeys(
            urljoin(page["url"], a["href"]) for a in soup.select("a[href]")
            if any(word in (a["href"] + " " + text_of(a)).lower()
                   for word in ["prospekt", "brochure"])) )[:20],
    }
    report["records"] = EXTRACTORS[page["store"]](soup, page)
    report["status"] = "candidates_extracted" if report["records"] else "needs_inspection"
    report["message"] = (f'{len(report["records"])} candidates; validate source evidence'
                          if report["records"] else
                          "No validated extraction path found. Rendering, market selection, or a new parser may be needed.")
    return prepare_report(report)


# Refresh the dataset

def refresh_all_offers_json(enabled=False, output_path=DEFAULT_DATA_PATH, pause_seconds=2):
    """Fetch configured pages, extract candidates, and save one dataset. No browser control.

    Per-source failures are included in the output; old offers from failed sources
    are not silently copied forward as fresh. If every source fails, the previous
    JSON is kept. Output replacement is atomic.
    """
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be True or False")
    if not enabled:
        return {"success": True, "status": "skipped", "updated": False,
                "message": "Fetching disabled. Existing JSON kept unchanged."}
    if not isinstance(pause_seconds, (int, float)) or not 2 <= pause_seconds <= 60:
        raise ValueError("pause_seconds must be between 2 and 60")
    reports = {}
    # Recheck crawler rules once per origin for each deliberate refresh run.
    robots_cache.clear()
    for index, store in enumerate(SOURCES):
        if index:
            time.sleep(pause_seconds)
        try:
            report = extract_page(fetch_shop(store, refresh=True))
            invalid = [r for r in report["records"] if r.get("quality", {}).get("validation_errors")]
            if invalid:
                report["records"] = [r for r in report["records"] if r not in invalid]
                report["message"] += f"; rejected {len(invalid)} invalid records"
                if not report["records"]:
                    report["status"] = "needs_inspection"
        except Exception as error:
            # Isolate a broken store/parser so the other sources can still run.
            report = dict(store=store, url=SOURCES[store], status="source_failed",
                          http_status=None, fetched_at=None, records=[],
                          message=f"Extraction failed: {type(error).__name__}: {error}")
        reports[store] = report
    dataset = build_dataset(reports)
    statuses = [{"store": s["store"], "status": s["status"], "records": s["record_count"],
                 "message": s["message"]} for s in dataset["sources"]]
    if not dataset["offers"]:
        return {"success": False, "status": "no_data_saved", "updated": False, "offer_count": 0,
                "output_path": None, "sources": statuses,
                "message": "No usable candidates. Previous JSON was kept unchanged."}
    path = Path(output_path)
    payload = json.dumps(dataset, ensure_ascii=False, indent=2)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                prefix="." + path.name, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    complete = all(s["status"] == "candidates_extracted" for s in dataset["sources"])
    return {"success": True, "status": "saved" if complete else "partial_saved", "updated": True,
            "offer_count": len(dataset["offers"]), "output_path": str(path.resolve()),
            "sources": statuses,
            "message": "Configured-page candidates saved; this is not complete national or branch coverage."}


# Optional import of a locally saved REWE page

def export_rewe_saved_html(html_path, output_path=PROJECT_ROOT / "data" / "processed" / "rewe_saved_offers.json", observed_at=None):
    """Read your saved HTML and export JSON. No HTTP requests or browser control."""
    if observed_at is not None:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("observed_at must include a timezone, or leave it None")
    source = Path(html_path)
    target = Path(output_path)
    if source.resolve() == target.resolve():
        raise ValueError("The output must not overwrite your source HTML")
    page = dict(store="REWE", url="https://www.rewe.de/angebote/nationale-angebote/kochen-und-backen/", fetched_at=observed_at,
                status="fetched", http_status=None,
                fetch_method="user_saved_html", html=source.read_text(encoding="utf-8"),
                message="User-supplied saved HTML; no network request was made")
    report = extract_page(page)
    expected = len(BeautifulSoup(page["html"], "html.parser").select(
        'section[id$="-current-week"] article.cor-offer-renderer-tile'))
    errors = [error for record in report["records"]
              for error in record["quality"].get("validation_errors", [])]
    if not report["records"] or len(report["records"]) != expected or errors:
        raise ValueError("Saved HTML did not produce a complete valid candidate extraction; output unchanged")
    dataset = build_dataset({"REWE": report})
    dataset["imported_from_file"] = str(source.resolve())
    payload = json.dumps(dataset, ensure_ascii=False, indent=2)
    # Create a temporary file beside the destination; replace only after writing succeeds.
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                prefix="." + target.name, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {"records": len(report["records"]), "output": str(target.resolve()),
            "observation_time_known": observed_at is not None}


def main():
    result = refresh_all_offers_json(enabled=FETCH_DATA)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
