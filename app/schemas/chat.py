from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

QuestionIntent = Literal[
    "concept",          #용어, 제도 설명
    "family",           #등록된 가족에 대한 증여세 계산
    "assessment",       #과세 여부 판단 및 간이 세액 계산
    "procedure",        #신고, 납부 절차
    "product"           #등록된 상품에 대한 설명
    "other_gift",       #위 유형에 포함되지 않는 증여세 관련 질문
    "other",            #기타 다른 질문 -> reject 해당 질문은 대답해 드릴 수가 없어요
    "jailbreak"         #탈옥 관련 프롬프트, 문자 인코딩 디코딩 관련 질문
]

class QuestionIntentResult(BaseModel):
    intent: QuestionIntent
    requires_calculation: bool
    reason: str

class ClarificationQuestion(BaseModel):
    key: str
    question: str
    reason: str
    required: bool

class KnownFact(BaseModel):
    key: str
    value: str

class ClarificationResult(BaseModel):
    needs_clarification: bool
    questions: list[ClarificationQuestion]
    known_facts: list[KnownFact]
    reason: str

class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
    )

    family_context: dict[str, Any] | None = None
    product_context: dict[str, Any] | None = None

    additional_facts: dict[str, Any] = Field(
        default_factory=dict,
    )


class ChatResponse(BaseModel):
    intent: QuestionIntent
    answer: str
    rejected: bool = False