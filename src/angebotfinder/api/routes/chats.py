"""Authenticated chat and per-user history."""

import logging
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_current_user, get_rag_pipeline
from ..schemas.chats import ChatRequest, ChatResponse, ChatTurnResponse
from ...database.chats import get_chat_history, save_chat_turn

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)
# Serialize local model use and history updates in this API process.
chat_lock = Lock()


@router.post("", response_model=ChatResponse)
def ask_question(request: ChatRequest, user=Depends(get_current_user)):
    if request.user_id != user["id"]:
        raise HTTPException(status_code=403, detail="You can only access your own chat.")

    with chat_lock:
        history = get_chat_history(user["id"], limit=3)
        try:
            pipeline = get_rag_pipeline()
        except (OSError, RuntimeError, ValueError):
            logger.exception("RAG initialization failed")
            raise HTTPException(
                status_code=503,
                detail="RAG is not ready. Check database offers, embeddings and cached models.",
            ) from None

        result = pipeline.ask_question(request.question, history=history)
        response = ChatResponse(user_id=user["id"], **result)
        save_chat_turn(user["id"], request.question, response.answer)
        return response


@router.get("/history", response_model=list[ChatTurnResponse])
def chat_history(
    user_id: UUID,
    limit: int = Query(default=3, ge=1, le=100),
    user=Depends(get_current_user),
):
    if user_id != user["id"]:
        raise HTTPException(status_code=403, detail="You can only access your own chat.")
    return get_chat_history(user["id"], limit=limit)
