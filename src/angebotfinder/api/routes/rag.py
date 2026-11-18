"""Download prepared retrieval data without running models."""

import logging

from fastapi import APIRouter, HTTPException
from psycopg import OperationalError

from ..schemas.rag import RetrievalBundleResponse
from ...retrieval import build_mobile_bundle

router = APIRouter(prefix="/rag", tags=["RAG data"])
logger = logging.getLogger(__name__)


@router.get("/data", response_model=RetrievalBundleResponse)
def download_retrieval_data():
    try:
        return build_mobile_bundle()
    except (OSError, ValueError, KeyError, OperationalError):
        logger.exception("Retrieval export is unavailable")
        raise HTTPException(
            status_code=503,
            detail="Retrieval data unavailable. Check PostgreSQL, pgvector and rebuild embeddings.",
        ) from None
