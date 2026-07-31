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

QuestionIntent = Literal[
    "concept",
    "family",
    "product",
    "assessment",
    "procedure",
    "other_gift",
    "other",
    "jailbreak",
]


class QuestionIntentResult(BaseModel):
    intent: QuestionIntent

    requires_calculation: bool = Field(
        default=False,
        description="증여세 또는 금융상품 수익 계산이 필요한지 여부",
    )

    reason: str = Field(
        default="",
        description="질문 유형을 이렇게 판정한 이유",
    )

    extracted_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="사용자 질문에서 추출한 사실 정보",
<<<<<<< HEAD
    )

class KnownFact(BaseModel):
    key: str
    value: str

class ClarificationResult(BaseModel):
    needs_clarification: bool
    questions: list[ClarificationQuestion]
    known_facts: list[KnownFact]
    reason: str
=======
    )
>>>>>>> aef42c0217b2aa57ac425db7cffce18a2f32bec3
