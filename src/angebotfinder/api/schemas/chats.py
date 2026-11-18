"""Chat requests, answers and saved conversation history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    user_id: UUID
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank.")
        return value


class ChatResponse(BaseModel):
    user_id: UUID
    question: str
    search_question: str
    answer: str
    status: str
    sources: list[dict]


class ChatTurnResponse(BaseModel):
    id: int
    question: str
    answer: str
    created_at: datetime
