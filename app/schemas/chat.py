from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.family import FamilyData
from app.schemas.product import ProductData, EtfProductData

ChatStatus = Literal[
    "COMPLETED",
    "CLARIFICATION_REQUIRED",
    "REJECTED",
]

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    question: str = Field(
        min_length=1,
        max_length=2000,
    )
    families: list[FamilyData] = Field(
        default_factory=list,
        max_length=3,
    )
    products: list[ProductData] = Field(
        default_factory=list,
    )
    etf_products: list[EtfProductData] = Field(
        default_factory=list,
    )
    facts: dict[str, Any] = Field(default_factory=dict)

class ClarificationQuestion(BaseModel):
    key: str
    data_type: Literal[
        "string",
        "integer",
        "boolean",
        "date",
    ]
    question: str
    reason: str | None = None


class LawReference(BaseModel):
    law_name: str
    article_no: str
    title: str | None = None
    url: str


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
    references: list[LawReference] = Field(default_factory=list)

class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    question: str
    intent: str
    requires_calculation: bool = False
    facts: dict[str, Any]
    answers: dict[str, Any]
    families: list[FamilyData] = Field(
        default_factory=list,
        max_length=3,
    )
    products: list[ProductData] = Field(
        default_factory=list,
    )
    etf_products: list[EtfProductData] = Field(
        default_factory=list,
    )

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
    )

class KnownFact(BaseModel):
    key: str
    value: str

class ClarificationResult(BaseModel):
    needs_clarification: bool
    questions: list[ClarificationQuestion]
    known_facts: list[KnownFact]
    reason: str
