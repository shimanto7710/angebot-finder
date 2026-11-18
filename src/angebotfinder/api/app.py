"""FastAPI entry point for AngebotFinder DE."""

from fastapi import FastAPI

from .routes.auth import router as auth_router
from .routes.chats import router as chat_router
from .routes.offers import router as offers_router
from .routes.rag import router as rag_router

app = FastAPI(title="AngebotFinder DE API")
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(offers_router)
app.include_router(rag_router)
