"""Offline checks for the script's offer extraction and JSON export.
Run: .venv/bin/python -m unittest discover -s tests -v
No websites are requested.
"""

import json
import unittest
from pathlib import Path

from scripts import fetch_offers


def fixture(**fields):
    record = dict(
        store="ALDI Süd",
        product_name="Champignons braun",
        brand="NATUR LIEBLINGE",
        variant=None,
        branch_region=None,
        offer_price="1.59",
        currency="EUR",
        pack_size_text="400 g",
        unit_price_text="(3,98 €/1 kg)",
        source_text="Champignons braun 400 g 1,59 €",
        source_html="<div>example</div>",
        source_url=fetch_offers.SOURCES["ALDI Süd"],
        product_url=None,
        fetched_at="2026-10-28T10:00:00+00:00",
        extraction_method="ALDI Süd visible weekly product tile",
        valid_from=None,
        valid_to=None,
        validity_text="26.10. bis 31.10.",
        requires_loyalty=None,
        section_context="Wochenangebote",
        loyalty_conditions=None,
        conditions_text=None,
    )
    record.update(fields)
    return record


def dataset(*records):
    return fetch_offers.build_dataset(
        {
            "ALDI Süd": dict(
                store="ALDI Süd",
                status="candidates_extracted",
                fetched_at="2026-10-28T10:00:00+00:00",
                http_status=200,
                message="candidate records",
                records=list(records),
                page_context="Participation unknown",
            )
        }
    )


class OfferDataTests(unittest.TestCase):
    def test_exact_decimal_calculation_and_published_rounding_stay_separate(self):
        r = fetch_offers.enrich_record(fixture())
        self.assertEqual(r["net_weight_g"], "400")
        self.assertEqual(r["calculated_unit_price"]["price"], "0.3975")
        self.assertEqual(r["unit_price"], "3.98")
        self.assertEqual(r["unit_price_basis"]["unit"], "kg")

    def test_yearless_dates_never_become_current_validity(self):
        r = fetch_offers.enrich_record(fixture())
        self.assertIsNone(r["valid_from"])

    def test_ranges_multipacks_and_drained_weight_do_not_get_unsafe_comparisons(self):
        for pack in ["150 - 200-g-Packg.", "2 x 100 g", "0 g"]:
            self.assertIsNone(
                fetch_offers.enrich_record(fixture(pack_size_text=pack))[
                    "calculated_unit_price"
                ]
            )
        r = fetch_offers.enrich_record(
            fixture(pack_size_text="je 540-g-Glas", source_text="250 g Abtropfgewicht")
        )
        self.assertEqual(r["drained_weight_g"], "250")
        self.assertIsNone(r["calculated_unit_price"])

    def test_standard_and_card_offers_have_different_ids(self):
        normal = fetch_offers.enrich_record(fixture())
        card = fetch_offers.enrich_record(fixture(requires_loyalty=True))
        self.assertEqual(normal["product_id"], card["product_id"])
        self.assertNotEqual(normal["offer_id"], card["offer_id"])

    def test_stable_offer_and_separate_snapshot_ids(self):
        before = fetch_offers.enrich_record(fixture())
        after = fetch_offers.enrich_record(fixture(fetched_at="2026-10-28T11:00:00+00:00"))
        self.assertEqual(before["offer_id"], after["offer_id"])
        self.assertNotEqual(before["record_id"], after["record_id"])

    def test_dataset_lists_all_configured_sources(self):
        d = dataset(fixture())
        self.assertEqual(len(d["sources"]), 8)

    def test_dataset_deduplicates_records(self):
        d = dataset(fixture(), fixture())
        self.assertEqual(len(d["offers"]), 1)
        self.assertNotIn("source_html", d["offers"][0])

    def test_invalid_money_is_flagged(self):
        # Validation is also callable on raw records before enrichment.
        self.assertIn(
            "offer_price must be positive and finite",
            fetch_offers.validate_record(fixture(offer_price="NaN")),
        )

    def test_loose_kg_price_is_not_pack_price(self):
        r = fetch_offers.enrich_record(fixture(pack_size_text="je kg"))
        self.assertEqual(r["price_quantity_basis"], "per_kg")
        self.assertIsNone(r["calculated_unit_price"])


class ReweParserTests(unittest.TestCase):
    def report(self):
        page = dict(
            store="REWE",
            url="https://www.rewe.de/angebote/nationale-angebote/kochen-und-backen/",
            fetched_at="2026-10-28T10:00:00+00:00",
            status="fetched",
            http_status=200,
            message="",
            fetch_method="saved_test_fixture",
        )
        page[
            "html"
        ] = """<button id="sos-week-tabs__tab-0"><span class="sos-tabs__tab-subtitle">26.10. bis 1.11.</span></button>
          <p id="sop-loyalty-terms" class="sop-footnotes_item">Register and scan app for credit.</p>
          <section id="kochen-und-backen-current-week"><h2>Kochen und Backen</h2>
           <article class="cor-offer-renderer-tile">
            <div class="cor-loyalty-badge">0,20 €</div>
            <a data-offer-title="Pesto" data-offer-week="2026/44" data-offer-nan="9452734">Pesto</a>
            <span class="cor-offer-information__additional">je 200-g-Glas</span>
            <span class="cor-offer-information__additional">, (1 kg = 9,45 €)</span>
            <div class="cor-offer-price__tag-price">1,89 €</div>
           </article>
          </section>"""
        return fetch_offers.extract_page(page)

    def test_checkout_price_bonus_and_retailer_id_stay_distinct(self):
        record = self.report()["records"][0]
        self.assertEqual(record["offer_price"], "1.89")
        self.assertEqual(record["benefits"][0]["amount"], "0.20")
        self.assertEqual(record["retailer_product_id"], "9452734")
        self.assertEqual(record["category"], "Kochen und Backen")
        self.assertEqual(record["calculated_unit_price"]["price"], "0.945")
        self.assertIsNone(record["requires_loyalty"])

    def test_published_week_resolves_year_without_fetch_time_guess(self):
        record = self.report()["records"][0]
        self.assertEqual(
            (record["valid_from"], record["valid_to"]), ("2026-10-26", "2026-11-01")
        )
        self.assertEqual(
            fetch_offers.rewe_validity("2020/53", "28.12. bis 3.1."),
            ("2020-12-28", "2021-01-03"),
        )
        self.assertEqual(fetch_offers.rewe_validity("2026/44", "1.1. bis 7.1."), (None, None))


class RefreshAllTests(unittest.TestCase):
    def test_all_source_failure_keeps_old_json(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text("previous data")

            def fail(store, refresh=False):
                return dict(
                    store=store,
                    url=fetch_offers.SOURCES[store],
                    status="blocked",
                    records=[],
                    html=None,
                    fetched_at=None,
                    http_status=403,
                    message="blocked",
                )

            with patch.object(fetch_offers, "fetch_shop", fail), patch("time.sleep"):
                result = fetch_offers.refresh_all_offers_json(enabled=True, output_path=path)
            self.assertFalse(result["success"])
            self.assertEqual(path.read_text(), "previous data")
            self.assertEqual(len(result["sources"]), 8)

    def test_partial_success_saved_with_failures_and_fresh_fetches(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        calls = []

        def fetch(store, refresh=False):
            calls.append((store, refresh))
            return {"store": store}

        def extract(page):
            store = page["store"]
            return dict(
                store=store,
                url=fetch_offers.SOURCES[store],
                status=(
                    "candidates_extracted" if store == "ALDI Süd" else "source_failed"
                ),
                records=[fixture()] if store == "ALDI Süd" else [],
                fetched_at="2026-10-28T10:00:00+00:00",
                message="test",
            )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            with (
                patch.object(fetch_offers, "fetch_shop", fetch),
                patch.object(fetch_offers, "extract_page", extract),
                patch("time.sleep"),
            ):
                result = fetch_offers.refresh_all_offers_json(enabled=True, output_path=path)
            self.assertEqual(result["status"], "partial_saved")
            self.assertEqual(result["offer_count"], 1)
            self.assertEqual(len(json.loads(path.read_text())["sources"]), 8)
            self.assertEqual(calls, [(store, True) for store in fetch_offers.SOURCES])

    def test_source_mapping_excludes_direct_rewe_network_fetch(self):
        self.assertEqual(fetch_offers.SOURCES["REWE"], "https://www.marktguru.de/r/rewe")
        self.assertIn("aktionspreis.de", fetch_offers.SOURCES["ALDI Nord"])
        self.assertIn("aldi-sued.de", fetch_offers.SOURCES["ALDI Süd"])
        self.assertIn("kaufland.de", fetch_offers.SOURCES["Kaufland"])


class ThirdPartyParserTests(unittest.TestCase):
    def test_expired_and_other_retailer_cards_are_excluded(self):
        card = '<li class="offer-list-item {expired}"><h3>Pasta</h3><dd class="retailer-name"><a href="{retailer}">Shop</a></dd><dd class="price"><span class="price">€ 1,59</span></dd><dd class="valid">25.10. - 31.10.</dd></li>'
        soup = fetch_offers.BeautifulSoup(
            "".join(
                [
                    card.format(expired="", retailer="/r/rewe"),
                    card.format(expired="expired", retailer="/r/rewe"),
                    card.format(expired="", retailer="/r/edeka"),
                ]
            ),
            "html.parser",
        )
        page = dict(store="REWE", url=fetch_offers.SOURCES["REWE"], fetched_at=None)
        records = fetch_offers.extract_marktguru(soup, page)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["offer_price"], "1.59")
        self.assertIsNone(records[0]["valid_from"])

    def test_aktionspreis_published_year_resolves_dates_and_exact_duplicates(self):
        card = '<div class="produkt_box"><div class="beschreibung"><b>Butter</b></div><b>1,49 €</b><span class="grundpreis">5,96 € je kg</span></div>'
        soup = fetch_offers.BeautifulSoup(
            "<span>Angebote vom 26.10. - 01.11.2026</span>" + card + card, "html.parser"
        )
        records = fetch_offers.extract_aktionspreis(
            soup,
            dict(store="ALDI Nord", url=fetch_offers.SOURCES["ALDI Nord"], fetched_at=None),
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(
            (records[0]["valid_from"], records[0]["valid_to"]),
            ("2026-10-26", "2026-11-01"),
        )


class RefreshFlagTests(unittest.TestCase):
    def test_default_and_false_do_not_fetch_sleep_or_write(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            path = Path(directory) / "offers.json"
            path.write_text("keep existing data")
            with (
                patch.object(fetch_offers, "fetch_shop", side_effect=AssertionError("must not fetch")) as fetch,
                patch("time.sleep") as sleep,
            ):
                for kwargs in ({}, {"enabled": False}):
                    result = fetch_offers.refresh_all_offers_json(output_path=path, **kwargs)
                    self.assertEqual(result["status"], "skipped")
                    self.assertFalse(result["updated"])
            fetch.assert_not_called()
            sleep.assert_not_called()
            self.assertEqual(path.read_text(), "keep existing data")


if __name__ == "__main__":
    unittest.main()
