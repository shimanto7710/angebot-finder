"""Authentication and shared RAG resources."""

from uuid import UUID
from functools import lru_cache, partial

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from ..database.users import get_user_by_id
from ..security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise unauthorized from None

    user = get_user_by_id(user_id)
    if user is None:
        raise unauthorized
    return user


@lru_cache(maxsize=1)
def get_rag_pipeline():
    """Load local RAG resources once per API process, on first use."""
    from ..database.embeddings import search_chunk_ids
    from ..models import load_models
    from ..rag_pipeline import RAGPipeline
    from ..retrieval import load_retrieval_data

    _, chunks, config, embeddings = load_retrieval_data()
    if not chunks:
        raise ValueError("No searchable chunks. Import offers and build embeddings first.")
    embedding_model, reranker, generator, tokenizer = load_models(
        config["embedding_model"], local_files_only=True,
    )
    return RAGPipeline(
        embeddings, chunks, embedding_model, reranker, generator, tokenizer,
        use_rewriting=True, min_score=0,
        semantic_search=partial(search_chunk_ids, model_name=config["embedding_model"]),
    )
