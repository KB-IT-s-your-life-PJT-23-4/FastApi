from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.family import FamilyData
from app.schemas.product import ProductData

ChatStatus = Literal[
    "COMPLETED",
    "CLARIFICATION_REQUIRED",
    "REJECTED",
]

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    question: str = Field(
        min_length=1,
        max_length=2000,
    )
    family: FamilyData | None = None
    product: ProductData | None = None
    facts: dict[str, Any] = Field(default_factory=dict)

class ClarificationQuestion(BaseModel):
    key: str
    question: str
    reason: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    status: ChatStatus
    intent: str
    requires_calculation: bool = False
    answer: str | None = None
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list
    )
    facts: dict[str, Any] = Field(default_factory=dict)

class ClarificationRequest(BaseModel):
    conversation_id: str
    question: str
    intent: str
    facts: dict[str, Any]
    answers: dict[str, Any]
    family: FamilyData | None = None
    product: ProductData | None = None