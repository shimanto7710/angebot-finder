"""Download format for local Android retrieval."""

from pydantic import BaseModel


class RetrievalBundleResponse(BaseModel):
    schema_version: str
    dataset_version: str
    config: dict
    chunks: list[dict]
    embeddings: list[list[float]]
