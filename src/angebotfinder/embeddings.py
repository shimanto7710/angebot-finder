import json
import numpy as np


def load_files(data_path):
    with data_path.open(encoding="utf-8") as f:
        data = json.load(f)

    offers = data["offers"]
    return offers


def prepare_documents(offers):
    documents = []

    for offer in offers:
        if offer.get("is_searchable") is False:
            continue

        parts = [offer["product_name"]]

        details = [
            ("Marke", offer.get("brand")),
            ("Variante", offer.get("variant")),
            ("Kategorie", offer.get("category")),
            ("Packung", offer.get("pack_size_text")),
            ("Händler", offer["store"]),
            ("Region", offer.get("branch_region")),
            ("Angegebener Preis", f'{offer["offer_price"]} {offer["currency"]}'),
            ("Grundpreis", offer.get("unit_price_text")),
            ("Gültigkeit laut Anzeige", offer.get("validity_text")),
            ("Kundenkartenbedingungen", offer.get("loyalty_conditions")),
            ("Weitere Hinweise", offer.get("conditions_text")),
        ]

        for label, value in details:
            if value:
                parts.append(f"{label}: {value}")

        if offer.get("requires_loyalty") is True:
            parts.append("Kundenkarte erforderlich")

        documents.append(
            {
                "record_id": offer["record_id"],
                "text": ". ".join(parts),
                "price": offer["offer_price"],
                "currency": offer["currency"],
                "price_quantity_basis": offer.get("price_quantity_basis"),
                "location": offer.get("branch_region"),
                "category": offer.get("category"),
                "store": offer["store"],
                "valid_from": offer.get("valid_from"),
                "valid_to": offer.get("valid_to"),
                "requires_loyalty": offer.get("requires_loyalty"),
                "source_url": offer["source_url"],
                "source_text": offer["source_text"],
            }
        )

    return documents


def do_chunking(documents, chunk_size=1200, overlap=200):
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Use chunk_size > 0 and 0 <= overlap < chunk_size.")

    chunks = []

    for doc in documents:
        text = doc["text"].strip()
        start = 0
        chunk_number = 1

        while start < len(text):
            end = min(start + chunk_size, len(text))

            chunk = doc.copy()
            chunk["chunk_id"] = f"{doc['record_id']}::chunk-{chunk_number}"
            chunk["text"] = text[start:end]
            chunks.append(chunk)

            if end == len(text):
                break

            start = end - overlap
            chunk_number += 1

    return chunks


def do_embedding(chunks, model):
    if not chunks:
        raise ValueError("No offer chunks to embed.")

    texts = [f"passage: {chunk['text']}" for chunk in chunks]

    embeddings = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    return embeddings


def save_chunks_embeddings(chunks, embeddings, output_dir, model_name):
    if embeddings.ndim != 2 or len(chunks) != embeddings.shape[0]:
        raise ValueError("Each chunk must have one embedding row.")

    saved_chunks = [
        {key: value for key, value in chunk.items() if key != "embedding"}
        for chunk in chunks
    ]

    config = {
        "embedding_model": model_name,
        "normalized": True,  # Matches normalize_embeddings=True in do_embedding()
        "chunk_count": len(saved_chunks),
        "embedding_dimension": int(embeddings.shape[1]),
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "chunks.json").write_text(
        json.dumps(saved_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    np.save(output_dir / "embeddings.npy", embeddings, allow_pickle=False)
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    print(f"Saved {len(saved_chunks)} chunks and embeddings to {output_dir}")
