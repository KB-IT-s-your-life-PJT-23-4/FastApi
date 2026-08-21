from __future__ import annotations

import os
from typing import Any
import re

from dotenv import load_dotenv
from openai import OpenAI
import json
from dataclasses import dataclass

from app.collectors.law_article_collector import (
    law_collection,
    search_gift_tax_law,
)

from app.collectors.nts_interpretation_collector import (
    collection as interpretation_collection,
    search_interpretations,
)
from app.prompts.answer import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    build_final_answer_prompt,
)
from app.prompts.clarification import (
    CLARIFICATION_SCHEMA,
    CLARIFICATION_SYSTEM_PROMPT,
    build_clarification_prompt,
)
from app.prompts.context import (
    build_calculation_failure_context,
    build_family_context,
    build_gift_tax_rule_context,
    build_product_context,
    combine_contexts,
)
from app.prompts.intent import (
    QUESTION_INTENT_SCHEMA,
    QUESTION_INTENT_SYSTEM_PROMPT,
    build_question_intent_prompt,
)
from app.schemas.chat import (
    ClarificationResult,
    QuestionIntentResult,
)
from app.services.fact_normalization_service import (
    extract_calculation_facts_from_question,
    normalize_calculation_facts as normalize_shared_calculation_facts,
)

load_dotenv()

PREVIOUS_GIFT_KEYS = {
    "has_previous_gifts",       #최근 10년 내 이전 증여가 있는지
    "previous_gift_amount",     #합산 대상 이전 증여금액
    "previous_gift_date",       #이전 증여일
    "previous_gift_same_donor", #현재 증여자와 동일한 증여자인지
}

FACT_KEY_ALIASES = {
    # 현재 증여금액
    "증여 금액": "gift_amount",
    "증여금액": "gift_amount",
    "현재 증여 금액": "gift_amount",
    "현재 증여금액": "gift_amount",

    # 증여 관계
    "증여자와 수증자의 관계": (
        "relationship_type"
    ),
    "증여 관계": "relationship_type",
    "관계": "relationship_type",

    # 미성년 여부
    "수증자의 미성년 여부": (
        "recipient_is_minor"
    ),
    "미성년 여부": "recipient_is_minor",

    # 현재 증여일
    "증여 날짜": "gift_date",
    "증여 예정일": "gift_date",
    "증여일": "gift_date",

    # 과거 증여
    "이전 증여 여부": "has_previous_gifts",
    "이전의 증여 여부": "has_previous_gifts",
    "previous_gifts": "has_previous_gifts",

    "이전 증여 금액": (
        "previous_gift_amount"
    ),
    "과거 증여 금액": (
        "previous_gift_amount"
    ),
    "gift_amounts": (
        "previous_gift_amount"
    ),

    "이전 증여일": "previous_gift_date",
    "과거 증여일": "previous_gift_date",

    "동일 증여자 여부": (
        "previous_gift_same_donor"
    ),
}

def normalize_fact_keys(
    facts: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for key, value in facts.items():
        canonical_key = FACT_KEY_ALIASES.get(
            key,
            key,
        )

        normalized[canonical_key] = value

    return normalized

def parse_korean_amount(
    value: Any,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    text = str(value).replace(
        ",",
        "",
    ).replace(
        " ",
        "",
    )

    if not text:
        return None

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)(억원|억|천만원|만원|원)?",
        text,
    )

    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2) or "원"

    multiplier = {
        "억원": 100_000_000,
        "억": 100_000_000,
        "천만원": 10_000_000,
        "만원": 10_000,
        "원": 1,
    }[unit]

    return int(
        number * multiplier
    )

def normalize_relationship_type(
    value: Any,
    recipient_is_minor: bool | None = None,
) -> str | None:
    text = str(value).strip()

    if text in {
        "자녀",
        "성년 자녀",
        "직계비속",
    }:
        if recipient_is_minor:
            return "parent_to_minor_child"

        return "parent_to_adult_child"

    if text in {
        "미성년 자녀",
    }:
        return "parent_to_minor_child"

    if text in {
        "배우자",
        "남편",
        "아내",
    }:
        return "spouse"

    if text in {
        "부모",
        "직계존속",
    }:
        return "child_to_parent"

    if text in {
        "기타 친족",
        "형제",
        "자매",
    }:
        return "other_relative"

    return None

def normalize_boolean_value(
    value: Any,
) -> bool | None:
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    normalized = str(value).strip().lower()

    if normalized in {
        "예",
        "네",
        "맞음",
        "맞습니다",
        "미성년자",
        "true",
        "1",
    }:
        return True

    if normalized in {
        "아니오",
        "아니요",
        "아님",
        "아닙니다",
        "성년",
        "성인",
        "false",
        "0",
    }:
        return False

    return None


def normalize_calculation_facts(
    facts: dict[str, Any],
    question: str = "",
) -> dict[str, Any]:
    normalized = normalize_fact_keys(
        facts
    )

    # 증여금액 변환: "6000만원" → 60000000
    normalized["gift_amount"] = (
        parse_korean_amount(
            normalized.get("gift_amount")
        )
    )

    # 미성년 여부
    recipient_is_minor = (
        normalize_boolean_value(
            normalized.get(
                "recipient_is_minor"
            )
        )
    )

    normalized[
        "recipient_is_minor"
    ] = recipient_is_minor

    # 관계값 변환
    raw_relationship = normalized.get(
        "relationship_type"
    )

    relationship_type = normalize_relationship_type(
        raw_relationship,
        recipient_is_minor=recipient_is_minor,
    )

    # 모델이 relationship_type에 "맞음", "아님"처럼
    # 잘못된 값을 넣은 경우 사용자 질문에서 관계를 다시 찾음
    if relationship_type is None:
        question_text = question.strip()

        if any(
            keyword in question_text
            for keyword in {
                "자녀",
                "아들",
                "딸",
            }
        ):
            relationship_type = (
                "parent_to_minor_child"
                if recipient_is_minor
                else "parent_to_adult_child"
            )

        elif any(
            keyword in question_text
            for keyword in {
                "배우자",
                "남편",
                "아내",
            }
        ):
            relationship_type = "spouse"

        elif any(
            keyword in question_text
            for keyword in {
                "부모",
                "아버지",
                "어머니",
            }
        ):
            relationship_type = "child_to_parent"

    normalized[
        "relationship_type"
    ] = relationship_type

    # 이전 증여 여부 정규화
    has_previous = normalized.get(
        "has_previous_gifts"
    )

    if means_no_previous_gifts(
        has_previous
    ):
        normalized[
            "has_previous_gifts"
        ] = False

        normalized[
            "previous_gift_amount"
        ] = 0

        normalized[
            "previous_gift_date"
        ] = ""

        normalized[
            "previous_gift_same_donor"
        ] = False

    elif means_has_previous_gifts(
        has_previous
    ):
        normalized[
            "has_previous_gifts"
        ] = True

        normalized[
            "previous_gift_amount"
        ] = parse_korean_amount(
            normalized.get(
                "previous_gift_amount"
            )
        )

        normalized[
            "previous_gift_same_donor"
        ] = normalize_boolean_value(
            normalized.get(
                "previous_gift_same_donor"
            )
        )

    # 기존 사용 공제액
    previously_used_deduction = (
        parse_korean_amount(
            normalized.get(
                "previously_used_deduction",
                0,
            )
        )
    )

    normalized[
        "previously_used_deduction"
    ] = (
        previously_used_deduction or 0
    )

    return normalized

GIFT_TAX_RATE_TABLE = [
    {
        "upper_limit": 100_000_000,
        "rate": 0.10,
        "progressive_deduction": 0,
    },
    {
        "upper_limit": 500_000_000,
        "rate": 0.20,
        "progressive_deduction": 10_000_000,
    },
    {
        "upper_limit": 1_000_000_000,
        "rate": 0.30,
        "progressive_deduction": 60_000_000,
    },
    {
        "upper_limit": 3_000_000_000,
        "rate": 0.40,
        "progressive_deduction": 160_000_000,
    },
    {
        "upper_limit": None,
        "rate": 0.50,
        "progressive_deduction": 460_000_000,
    },
]

GIFT_DEDUCTION_TABLE = {
    "spouse": 600_000_000,
    "parent_to_adult_child": 50_000_000,
    "parent_to_minor_child": 20_000_000,
    "child_to_parent": 50_000_000,
    "other_relative": 10_000_000,
    "other": 0,
}

@dataclass
class GiftTaxEstimate:
    gift_amount: int
    previous_gift_amount: int
    deduction_limit: int
    previously_used_deduction: int
    available_deduction: int
    taxable_base: int
    tax_rate: float
    progressive_deduction: int
    estimated_calculated_tax: int
    is_estimate: bool = True


# def apply_gift_tax_rate(
#     taxable_base: int,
# ) -> tuple[float, int, int]:
#     if taxable_base <= 0:
#         return 0.0, 0, 0

#     for bracket in GIFT_TAX_RATE_TABLE:
#         upper_limit = bracket["upper_limit"]

#         if (
#             upper_limit is None
#             or taxable_base <= upper_limit
#         ):
#             rate = float(bracket["rate"])
#             progressive_deduction = int(
#                 bracket["progressive_deduction"]
#             )

#             calculated_tax = int(
#                 taxable_base * rate
#                 - progressive_deduction
#             )

#             return (
#                 rate,
#                 progressive_deduction,
#                 max(calculated_tax, 0),
#             )

#     raise RuntimeError(
#         "적용 가능한 증여세율 구간이 없습니다."
#     )

# def create_tax_estimate_from_facts(
#     facts: dict[str, Any],
# ) -> GiftTaxEstimate | None:
#     missing_keys = (
#         validate_estimate_facts(
#             facts
#         )
#     )

#     if missing_keys:
#         return None

#     gift_amount = facts.get(
#         "gift_amount"
#     )

#     relationship_type = facts.get(
#         "relationship_type"
#     )

#     previous_gift_amount = facts.get(
#         "previous_gift_amount",
#         0,
#     )

#     previously_used_deduction = (
#         facts.get(
#             "previously_used_deduction",
#             0,
#         )
#     )

#     if not isinstance(
#         gift_amount,
#         int,
#     ):
#         return None

#     if not isinstance(
#         relationship_type,
#         str,
#     ):
#         return None

#     if not isinstance(
#         previous_gift_amount,
#         int,
#     ):
#         return None

#     if not isinstance(
#         previously_used_deduction,
#         int,
#     ):
#         previously_used_deduction = 0

#     return calculate_simple_gift_tax(
#         gift_amount=gift_amount,
#         relationship_type=(
#             relationship_type
#         ),
#         previous_gift_amount=(
#             previous_gift_amount
#         ),
#         previously_used_deduction=(
#             previously_used_deduction
#         ),
#     )

# def calculate_simple_gift_tax(
#     gift_amount: int,
#     relationship_type: str,
#     previous_gift_amount: int = 0,
#     previously_used_deduction: int = 0,
# ) -> GiftTaxEstimate:
#     if gift_amount < 0:
#         raise ValueError(
#             "증여금액은 0원 이상이어야 합니다."
#         )

#     if previous_gift_amount < 0:
#         raise ValueError(
#             "과거 증여금액은 0원 이상이어야 합니다."
#         )

#     deduction_limit = GIFT_DEDUCTION_TABLE.get(
#         relationship_type,
#         0,
#     )

#     available_deduction = max(
#         deduction_limit
#         - previously_used_deduction,
#         0,
#     )

#     # 단순화를 위한 계산:
#     # 현재 증여액과 합산대상 과거 증여액을 합산
#     total_gift_tax_base = (
#         gift_amount
#         + previous_gift_amount
#     )

#     taxable_base = max(
#         total_gift_tax_base
#         - available_deduction,
#         0,
#     )

#     (
#         rate,
#         progressive_deduction,
#         calculated_tax,
#     ) = apply_gift_tax_rate(
#         taxable_base
#     )

#     return GiftTaxEstimate(
#         gift_amount=gift_amount,
#         previous_gift_amount=previous_gift_amount,
#         deduction_limit=deduction_limit,
#         previously_used_deduction=(
#             previously_used_deduction
#         ),
#         available_deduction=available_deduction,
#         taxable_base=taxable_base,
#         tax_rate=rate,
#         progressive_deduction=(
#             progressive_deduction
#         ),
#         estimated_calculated_tax=calculated_tax,
#     )

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

OPENAI_CHAT_MODEL = os.getenv(
    "OPENAI_CHAT_MODEL",
    "gpt-5-nano",
)

chat_client = OpenAI(
    api_key=OPENAI_API_KEY,
)

BLOCKED_INTENTS = {
    "other",
    "jailbreak",
}

RAG_INTENTS = {
    "concept",
    "family",
    "assessment",
    "procedure",
    "other_gift",
}

REJECTION_MESSAGE = (
    "해당 질문은 답변해 드릴 수 없습니다. "
    "증여세, 증여 절차, 등록 가족 또는 등록 금융상품과 "
    "관련된 질문을 입력해 주세요."
)

FAMILY_DATA_REQUIRED_MESSAGE = (
    "등록된 가족 정보를 확인할 수 없습니다. "
    "가족을 선택한 후 다시 질문해 주세요."
)

PRODUCT_DATA_REQUIRED_MESSAGE = (
    "등록된 상품 정보를 확인할 수 없습니다. "
    "상품을 선택한 후 다시 질문해 주세요."
)

FAMILY_FACT_KEYS = {
    "relationship_type",
    "recipient_is_minor",
    "has_previous_gifts",
    "previous_gift_amount",
    "previous_gift_date",
    "previous_gift_same_donor",
    "previously_used_deduction",
}

def is_unknown_value(
    value: Any,
) -> bool:
    if value is None:
        return True

    normalized = str(value).strip().lower()

    return normalized in {
        "",
        "모름",
        "알 수 없음",
        "확인 안 됨",
        "unknown",
        "none",
        "null",
    }

def has_previous_gift_answer(
    facts: dict[str, Any],
) -> bool:
    return not is_unknown_value(
        facts.get("has_previous_gifts")
    )

def means_no_previous_gifts(
    value: Any,
) -> bool:
    if value is False:
        return True

    if value is True:
        return False

    normalized = str(value).strip().lower()

    return normalized in {
        "없음",
        "없습니다",
        "없다",
        "아니오",
        "아니요",
        "no",
        "false",
        "0",
    }

def means_has_previous_gifts(
    value: Any,
) -> bool:
    if value is True:
        return True

    if value is False:
        return False

    normalized = str(value).strip().lower()

    return normalized in {
        "있음",
        "있습니다",
        "있다",
        "예",
        "네",
        "yes",
        "true",
        "1",
    }

def collect_previous_gift_facts(
    additional_facts: dict[str, Any],
) -> dict[str, Any]:
    facts = {
        **additional_facts,
    }

    if not has_previous_gift_answer(facts):
        answer = input(
            "\n최근 10년 동안 같은 증여자로부터 "
            "받은 이전 증여가 있나요? "
            "(있음/없음/모름): "
        ).strip()

        facts["has_previous_gifts"] = (
            answer or "모름"
        )

    has_previous = facts.get(
        "has_previous_gifts"
    )

    if means_no_previous_gifts(has_previous):
        facts["previous_gift_amount"] = 0
        facts["previous_gift_same_donor"] = False
        facts["previous_gift_date"] = ""

        return facts

    if means_has_previous_gifts(has_previous):
        if is_unknown_value(
            facts.get("previous_gift_amount")
        ):
            amount = input(
                "최근 10년 내 합산 대상 이전 증여금액을 "
                "원 단위로 입력하세요: "
            ).strip()

            facts["previous_gift_amount"] = (
                amount or "모름"
            )

        if is_unknown_value(
            facts.get("previous_gift_date")
        ):
            previous_date = input(
                "이전 증여일을 입력하세요 "
                "(예: 2022-05-03, 모르면 '모름'): "
            ).strip()

            facts["previous_gift_date"] = (
                previous_date or "모름"
            )

        if is_unknown_value(
            facts.get(
                "previous_gift_same_donor"
            )
        ):
            same_donor = input(
                "이전 증여자와 이번 증여자가 동일한가요? "
                "(예/아니오/모름): "
            ).strip()

            facts[
                "previous_gift_same_donor"
            ] = same_donor or "모름"

    return facts


def classify_question_intent(
    question: str,
) -> QuestionIntentResult:
    prompt = build_question_intent_prompt(
        question
    )

    response = chat_client.responses.create(
        model=OPENAI_CHAT_MODEL,
        instructions=QUESTION_INTENT_SYSTEM_PROMPT,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "question_intent",
                "strict": True,
                "schema": QUESTION_INTENT_SCHEMA,
            }
        },
    )

    if not response.output_text:
        raise RuntimeError(
            "질문 유형 판정 결과가 비어 있습니다."
        )

    result = QuestionIntentResult.model_validate_json(
        response.output_text
    )

    if result.intent in {"family", "assessment"}:
        result.extracted_facts = (
            extract_calculation_facts_from_question(
                question
            )
        )

    # 차단 질문은 계산하지 않도록 서버에서 강제
    if result.intent in BLOCKED_INTENTS:
        result.requires_calculation = False

    # 상품 설명 질문도 계산하지 않도록 방어
    if result.intent == "product":
        result.requires_calculation = False

    return result

DEFAULT_FACTS: dict[str, Any] = {
    "residency": "국내 거주자",
    "use_latest_tax_rate": True,
}

def validate_estimate_facts(
    facts: dict[str, Any],
) -> list[str]:
    missing: list[str] = []

    required_keys = [
        "gift_amount",
        "relationship_type",
        "has_previous_gifts",
    ]

    for key in required_keys:
        if is_unknown_value(
            facts.get(key)
        ):
            missing.append(key)

    has_previous = facts.get(
        "has_previous_gifts"
    )

    if means_has_previous_gifts(
        has_previous
    ):
        for key in [
            "previous_gift_amount",
            "previous_gift_date",
            "previous_gift_same_donor",
        ]:
            if is_unknown_value(
                facts.get(key)
            ):
                missing.append(key)

    return missing

# def build_tax_estimate_context(
#     estimate: GiftTaxEstimate,
# ) -> str:
#     return f"""
# [서버 간이 세액 계산 결과]
# 계산 유형: 국내 거주자 기본세율 간이 계산
# 증여금액: {estimate.gift_amount:,}원
# 과거 합산 증여금액: {estimate.previous_gift_amount:,}원
# 공제 한도: {estimate.deduction_limit:,}원
# 기존 사용 공제액: {estimate.previously_used_deduction:,}원
# 적용 가능 공제액: {estimate.available_deduction:,}원
# 간이 과세표준: {estimate.taxable_base:,}원
# 적용 세율: {estimate.tax_rate * 100:.0f}%
# 누진공제액: {estimate.progressive_deduction:,}원
# 간이 산출세액: 약 {estimate.estimated_calculated_tax:,}원

# 주의:
# 이 금액은 입력된 사실관계를 기준으로 한 간이 추정치입니다.
# 재산 평가, 채무인수, 과거 증여 합산, 납부세액공제,
# 혼인·출산 공제, 세대생략 할증 및 신고세액공제는
# 별도 확인이 필요할 수 있습니다.
# """.strip()

def get_first_result_list(
    search_result: dict[str, Any],
    key: str,
) -> list[Any]:
    """
    ChromaDB query 결과에서 첫 번째 쿼리의 결과 목록을 꺼낸다.

    예:
        result["documents"] == [[문서1, 문서2]]
        반환값 == [문서1, 문서2]
    """
    values = search_result.get(key) or []

    if not values:
        return []

    first = values[0]

    if not isinstance(first, list):
        return []

    return first


def format_interpretation_context(
    search_result: dict[str, Any],
) -> list[str]:
    """
    국세청 법령해석 검색 결과를 프롬프트용 문자열 목록으로 변환한다.
    """
    ids = get_first_result_list(
        search_result,
        "ids",
    )
    documents = get_first_result_list(
        search_result,
        "documents",
    )
    metadatas = get_first_result_list(
        search_result,
        "metadatas",
    )
    distances = get_first_result_list(
        search_result,
        "distances",
    )

    contexts: list[str] = []

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        section = metadata.get(
            "section_label",
            metadata.get("section", ""),
        )

        context = f"""
[법령해석 {index}]
자료 유형: 국세청 법령해석
제목: {metadata.get("title", "")}
안건번호: {metadata.get("case_number", "")}
해석일자: {metadata.get("interpretation_date", "")}
해석기관: {metadata.get("agency", "")}
문서 구분: {section}
문서 ID: {metadata.get("document_id", "")}
청크 ID: {chunk_id}
검색 거리: {float(distance):.6f}
출처: {metadata.get("source_url", "")}

내용:
{document}
""".strip()

        contexts.append(context)

    return contexts


def format_law_context(
    search_result: dict[str, Any],
) -> list[str]:
    """
    법령 원문 검색 결과를 프롬프트용 문자열 목록으로 변환한다.
    """
    ids = get_first_result_list(
        search_result,
        "ids",
    )
    documents = get_first_result_list(
        search_result,
        "documents",
    )
    metadatas = get_first_result_list(
        search_result,
        "metadatas",
    )
    distances = get_first_result_list(
        search_result,
        "distances",
    )

    contexts: list[str] = []

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            ids,
            documents,
            metadatas,
            distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        article_label = metadata.get(
            "article_label",
            "",
        )

        article_title = metadata.get(
            "article_title",
            "",
        )

        article_name = article_label

        if article_title:
            article_name = (
                f"{article_label}"
                f"({article_title})"
            )

        context = f"""
[법령 원문 {index}]
자료 유형: 법령 원문
법령명: {metadata.get("law_name", "")}
조문: {article_name}
항: {metadata.get("paragraph_number", "")}
조문 시행일: {metadata.get("article_effective_date", "")}
법령 시행일: {metadata.get("effective_date", "")}
세법 범위: {metadata.get("tax_scope", "")}
법령 ID: {metadata.get("law_id", "")}
조문키: {metadata.get("article_key", "")}
청크 ID: {chunk_id}
검색 거리: {float(distance):.6f}
출처: {metadata.get("source_url", "")}

내용:
{document}
""".strip()

        contexts.append(context)

    return contexts

def extract_family_facts(
    family_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if not family_data:
        return {}

    return {
        key: value
        for key, value in family_data.items()
        if key in FAMILY_FACT_KEYS
    }


def retrieve_context(
    question: str,
    interpretation_top_k: int = 4,
    law_top_k: int = 2,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
]:
    """
    법령해석 4개와 법령 원문 2개를 검색하고,
    하나의 context 문자열로 조립한다.
    """
    question = question.strip()

    if not question:
        raise ValueError(
            "검색 질문이 비어 있습니다."
        )

    if interpretation_top_k <= 0:
        raise ValueError(
            "법령해석 검색 개수는 1 이상이어야 합니다."
        )

    if law_top_k <= 0:
        raise ValueError(
            "법령 검색 개수는 1 이상이어야 합니다."
        )

    interpretation_count = (
        interpretation_collection.count()
    )

    law_count = law_collection.count()

    if interpretation_count == 0:
        raise RuntimeError(
            "법령해석 컬렉션에 데이터가 없습니다."
        )

    if law_count == 0:
        raise RuntimeError(
            "법령 원문 컬렉션에 데이터가 없습니다."
        )

    interpretation_result = search_interpretations(
        question=question,
        top_k=min(
            interpretation_top_k,
            interpretation_count,
        ),
    )

    law_result = search_gift_tax_law(
        question=question,
        top_k=min(
            law_top_k,
            law_count,
        ),
    )

    interpretation_contexts = (
        format_interpretation_context(
            interpretation_result
        )
    )

    law_contexts = format_law_context(
        law_result
    )

    context_parts = [
        "===== 국세청 법령해석 사례 =====",
        *interpretation_contexts,
        "",
        "===== 관련 법령 원문 =====",
        *law_contexts,
    ]

    context = "\n\n".join(context_parts)

    return (
        context,
        interpretation_result,
        law_result,
    )

def analyze_clarification_need(
    question: str,
    context: str,
    additional_facts: dict[str, Any] | None = None,
    intent: str = "other_gift",
    requires_calculation: bool = False,
) -> ClarificationResult:
    additional_facts = additional_facts or {}

    # assessment 이외에는 추가 질문 금지
    if intent != "assessment":
        return ClarificationResult(
            needs_clarification=False,
            questions=[],
            known_facts=[],
            reason=(
                "현재 질문 유형은 사용자 추가 확인 대상이 아닙니다."
            ),
        )

    prompt = build_clarification_prompt(
        question=question,
        context=context,
        additional_facts=additional_facts,
        intent=intent,
        requires_calculation=requires_calculation,
    )

    response = chat_client.responses.create(
        model=OPENAI_CHAT_MODEL,
        instructions=CLARIFICATION_SYSTEM_PROMPT,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "clarification_result",
                "strict": True,
                "schema": CLARIFICATION_SCHEMA,
            }
        },
    )

    if not response.output_text:
        raise RuntimeError(
            "추가정보 판정 결과가 비어 있습니다."
        )

    result = ClarificationResult.model_validate_json(
        response.output_text
    )

    if result.needs_clarification:
        result.questions = result.questions[:3]

        if not result.questions:
            result.needs_clarification = False

    return result


def generate_final_answer(
    question: str,
    context: str,
    additional_facts: dict[str, Any],
    intent: str,
) -> str:
    if intent in BLOCKED_INTENTS:
        return REJECTION_MESSAGE

    prompt = build_final_answer_prompt(
        question=question,
        context=context,
        additional_facts=additional_facts,
        intent=intent,
    )

    response = chat_client.responses.create(
        model=OPENAI_CHAT_MODEL,
        instructions=FINAL_ANSWER_SYSTEM_PROMPT,
        input=prompt,
    )

    answer = response.output_text.strip()

    if not answer:
        raise RuntimeError(
            "최종 답변이 비어 있습니다."
        )

    return answer

def print_retrieved_documents(
    interpretation_result: dict[str, Any],
    law_result: dict[str, Any],
) -> None:
    print("\n")
    print("=" * 100)
    print("검색된 국세청 법령해석 4개")
    print("=" * 100)

    interpretation_ids = get_first_result_list(
        interpretation_result,
        "ids",
    )
    interpretation_documents = get_first_result_list(
        interpretation_result,
        "documents",
    )
    interpretation_metadatas = get_first_result_list(
        interpretation_result,
        "metadatas",
    )
    interpretation_distances = get_first_result_list(
        interpretation_result,
        "distances",
    )

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            interpretation_ids,
            interpretation_documents,
            interpretation_metadatas,
            interpretation_distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        print(f"\n[법령해석 {index}]")
        print(f"거리: {float(distance):.6f}")
        print(f"청크 ID: {chunk_id}")
        print(
            "제목:",
            metadata.get("title", ""),
        )
        print(
            "안건번호:",
            metadata.get("case_number", ""),
        )
        print(
            "해석일자:",
            metadata.get(
                "interpretation_date",
                "",
            ),
        )
        print(
            "섹션:",
            metadata.get(
                "section_label",
                metadata.get("section", ""),
            ),
        )
        print(
            "출처:",
            metadata.get("source_url", ""),
        )
        print("\n본문 미리보기:")
        print(
            document[:500]
            + ("..." if len(document) > 500 else "")
        )

    print("\n")
    print("=" * 100)
    print("검색된 법령 원문 2개")
    print("=" * 100)

    law_ids = get_first_result_list(
        law_result,
        "ids",
    )
    law_documents = get_first_result_list(
        law_result,
        "documents",
    )
    law_metadatas = get_first_result_list(
        law_result,
        "metadatas",
    )
    law_distances = get_first_result_list(
        law_result,
        "distances",
    )

    for index, (
        chunk_id,
        document,
        metadata,
        distance,
    ) in enumerate(
        zip(
            law_ids,
            law_documents,
            law_metadatas,
            law_distances,
        ),
        start=1,
    ):
        metadata = metadata or {}

        print(f"\n[법령 원문 {index}]")
        print(f"거리: {float(distance):.6f}")
        print(f"청크 ID: {chunk_id}")
        print(
            "법령명:",
            metadata.get("law_name", ""),
        )
        print(
            "조문:",
            metadata.get("article_label", ""),
        )
        print(
            "조문 제목:",
            metadata.get("article_title", ""),
        )
        print(
            "항:",
            metadata.get("paragraph_number", ""),
        )
        print(
            "조문 시행일:",
            metadata.get(
                "article_effective_date",
                "",
            ),
        )
        print(
            "출처:",
            metadata.get("source_url", ""),
        )
        print("\n본문 미리보기:")
        print(
            document[:500]
            + ("..." if len(document) > 500 else "")
        )

def ask_clarification_questions(
    clarification: ClarificationResult,
    additional_facts: dict[str, Any],
    asked_keys: set[str],
) -> int:
    """
    추가 확인 질문을 콘솔에 출력하고 사용자 답변을 저장한다.

    반환값:
        이번 단계에서 실제로 답변받은 질문 수
    """
    answered_count = 0

    print("\n")
    print("=" * 100)
    print("정확한 답변을 위해 추가 확인이 필요합니다.")
    print("=" * 100)
    print(f"판정 이유: {clarification.reason}")

    for item in clarification.questions:
        if item.key in asked_keys:
            continue

        # 이전 증여가 없다고 이미 확인된 경우
        # 관련 후속 질문은 출력하지 않음
        if (
            additional_facts.get(
                "has_previous_gifts"
            ) is False
            and item.key in {
                "previous_gift_amount",
                "previous_gift_date",
                "previous_gift_same_donor",
            }
        ):
            continue

        print("\n" + "-" * 100)
        print(f"확인 항목: {item.key}")
        print(f"질문: {item.question}")
        print(f"필요한 이유: {item.reason}")

        while True:
            answer = input(
                "답변을 입력하세요 "
                "(모르면 '모름', 종료하려면 '/skip'): "
            ).strip()

            if answer:
                break

            print("답변을 입력해야 합니다.")

        asked_keys.add(item.key)

        if answer == "/skip":
            additional_facts[item.key] = (
                "사용자가 답변하지 않음"
            )

        else:
            additional_facts[item.key] = answer

            # 이전 증여가 없다는 답변이면
            # 관련 값을 계산 가능한 형태로 즉시 확정
            if (
                item.key == "has_previous_gifts"
                and means_no_previous_gifts(answer)
            ):
                additional_facts[
                    "has_previous_gifts"
                ] = False

                additional_facts[
                    "previous_gift_amount"
                ] = 0

                additional_facts[
                    "previous_gift_date"
                ] = ""

                additional_facts[
                    "previous_gift_same_donor"
                ] = False

            elif (
                item.key == "has_previous_gifts"
                and means_has_previous_gifts(answer)
            ):
                additional_facts[
                    "has_previous_gifts"
                ] = True

        answered_count += 1

    return answered_count


def run_clarification_flow(
    question: str,
    context: str,
    initial_facts: dict[str, Any] | None = None,
    intent: str = "other",
    requires_calculation: bool = False,
    max_rounds: int = 3,
) -> dict[str, Any]:
    additional_facts: dict[str, Any] = {
        **(initial_facts or {}),
    }

    asked_keys: set[str] = set()

    for round_index in range(
        1,
        max_rounds + 1,
    ):
        clarification = analyze_clarification_need(
            question=question,
            context=context,
            additional_facts=additional_facts,
            intent=intent,
            requires_calculation=(
                requires_calculation
            ),
        )

        # 모델이 질문에서 이미 파악한 사실은 참고용으로만 출력
        if clarification.known_facts:
            print("\n모델이 파악한 기존 사실:")

            known_facts_dict = {
                fact.key: fact.value
                for fact in clarification.known_facts
            }

            print(
                json.dumps(
                    known_facts_dict,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            for key, value in known_facts_dict.items():
                current_value = additional_facts.get(
                    key
                )

                if is_unknown_value(current_value):
                    additional_facts[key] = value

                elif key not in additional_facts:
                    additional_facts[key] = value

        if not clarification.needs_clarification:
            print("\n추가 확인 없이 최종 답변을 생성할 수 있습니다.")
            return additional_facts

        # 이미 물어본 키를 다시 생성한 경우 제외
        new_questions = [
            item
            for item in clarification.questions
            if item.key not in asked_keys
        ]

        if not new_questions:
            print(
                "\n새롭게 확인할 질문이 없어 "
                "현재 사실관계로 최종 답변을 생성합니다."
            )
            return additional_facts

        clarification.questions = new_questions

        answered_count = ask_clarification_questions(
            clarification=clarification,
            additional_facts=additional_facts,
            asked_keys=asked_keys,
        )

        if answered_count == 0:
            print(
                "\n추가로 수집된 답변이 없어 "
                "현재 사실관계로 최종 답변을 생성합니다."
            )
            return additional_facts

        print("\n현재까지 확인된 사실:")
        print(
            json.dumps(
                additional_facts,
                ensure_ascii=False,
                indent=2,
            )
        )

    print(
        "\n추가 질문 최대 횟수에 도달했습니다. "
        "확인된 사실만으로 최종 답변을 생성합니다."
    )

    return additional_facts

def should_run_clarification(
    intent: str,
) -> bool:
    return intent == "assessment"

def normalize_previous_gift_facts(
    facts: dict[str, Any],
) -> dict[str, Any]:
    normalized = {
        **facts,
    }

    if means_no_previous_gifts(
        normalized.get(
            "has_previous_gifts"
        )
    ):
        normalized[
            "has_previous_gifts"
        ] = False

        normalized[
            "previous_gift_amount"
        ] = 0

        normalized[
            "previous_gift_same_donor"
        ] = False

        normalized[
            "previous_gift_date"
        ] = ""

    elif means_has_previous_gifts(
        normalized.get(
            "has_previous_gifts"
        )
    ):
        normalized[
            "has_previous_gifts"
        ] = True

    return normalized

CALCULATION_INTENTS = {
    "family",
    "assessment",
}

def process_question(
    *,
    question: str,
    family_data: dict[str, Any] | None = None,
    product_data: dict[str, Any] | None = None,
    initial_facts: dict[str, Any] | None = None,
) -> tuple[QuestionIntentResult, str]:
    question = question.strip()

    if not question:
        raise ValueError(
            "사용자 질문을 입력해야 합니다."
        )

    # 1. 질문 유형 분류
    intent_result = classify_question_intent(
        question
    )

    intent = intent_result.intent

    # 2. other, jailbreak는 RAG 전에 차단
    if intent in BLOCKED_INTENTS:
        return intent_result, REJECTION_MESSAGE

    # 3. 서버 데이터 확인
    if intent == "family" and not family_data:
        return (
            intent_result,
            FAMILY_DATA_REQUIRED_MESSAGE,
        )

    if intent == "product" and not product_data:
        return (
            intent_result,
            PRODUCT_DATA_REQUIRED_MESSAGE,
        )

    # 4. 기본 사실 구성
    additional_facts: dict[str, Any] = {
        **DEFAULT_FACTS,
        **intent_result.extracted_facts,
        **(initial_facts or {}),
    }
    if intent in {"family", "assessment"}:
        additional_facts = normalize_shared_calculation_facts(
            additional_facts,
            question=question,
        )

    family_context = ""
    product_context = ""
    rag_context = ""

    # 5. family 데이터 주입
    if intent == "family":
        family_facts = extract_family_facts(
            family_data
        )

        # DB 데이터가 사용자 입력보다 우선
        additional_facts.update(
            family_facts
        )

        family_context = build_family_context(
            family_data
        )

    # 6. product 데이터 주입
    if intent == "product":
        product_context = build_product_context(
            product_data
        )

    # 7. 증여세 관련 유형만 RAG 검색
    if intent in RAG_INTENTS:
        (
            rag_context,
            _,
            _,
        ) = retrieve_context(
            question=question,
            interpretation_top_k=4,
            law_top_k=2,
        )

    # 상품 정보 설명만 필요한 경우에는
    # 법령 ChromaDB 검색을 하지 않음
    base_context = combine_contexts(
        family_context,
        product_context,
        rag_context,
    )

    # 8. assessment만 사용자 추가 질문
    if intent == "assessment":
        additional_facts = run_clarification_flow(
            question=question,
            context=base_context,
            initial_facts=additional_facts,
            intent=intent,
            requires_calculation=(
                intent_result.requires_calculation
            ),
            max_rounds=3,
        )

    gift_tax_rule_context = ""
    calculation_notice = ""

    should_calculate = (
        intent in {"family", "assessment"}
        and intent_result.requires_calculation
    )


     # 9. AI 계산용 데이터 준비
    if should_calculate:
        if intent == "assessment":
            additional_facts = (
                collect_previous_gift_facts(
                    additional_facts
                )
            )

        additional_facts = normalize_shared_calculation_facts(
            additional_facts,
            question=question,
        )

        missing_facts = (
            validate_estimate_facts(
                additional_facts
            )
        )

        if missing_facts:
            calculation_notice = (
                build_calculation_failure_context(
                    missing_facts
                )
            )

        else:
            gift_tax_rule_context = (
                build_gift_tax_rule_context(
                    rate_table=(
                        GIFT_TAX_RATE_TABLE
                    ),
                    deduction_table=(
                        GIFT_DEDUCTION_TABLE
                    ),
                )
            )

    # 10. 최종 Context 조립
    final_context = combine_contexts(
        base_context,
        gift_tax_rule_context,
        calculation_notice,
    )

    # 11. 최종 답변 생성
    answer = generate_final_answer(
        question=question,
        context=final_context,
        additional_facts=additional_facts,
        intent=intent,
    )

    return intent_result, answer

def main() -> None:
    question = input(
        "\n사용자 질문을 입력하세요: "
    ).strip()

    if not question:
        raise ValueError(
            "사용자 질문을 입력해야 합니다."
        )

    # 실제 FastAPI에서는 Spring 요청 데이터가 들어옴
    # 콘솔 테스트에서는 필요할 때 직접 임시값 설정
    family_data: dict[str, Any] | None = None
    product_data: dict[str, Any] | None = None

    family_data = {
    "family_id": 1,
    "name": "박준영",
    "relationship_type": "자녀",
    "recipient_is_minor": False,
    "has_previous_gifts": False,
    "previous_gift_amount": 20000000,
    "previous_gift_date": "",
    "previous_gift_same_donor": False,
    "previously_used_deduction": 0,
    }

    intent_result, answer = process_question(
        question=question,
        family_data=family_data,
        product_data=product_data,
    )

    print("\n" + "=" * 100)
    print("질문 분류 결과")
    print("=" * 100)
    print(
        json.dumps(
            intent_result.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n" + "=" * 100)
    print("최종 답변")
    print("=" * 100)
    print(answer)


if __name__ == "__main__":
    main()
