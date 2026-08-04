import re
from decimal import Decimal
from typing import Any
from app.core.constants import FACT_KEY_ALIASES

UNKNOWN_VALUES = {
    "",
    "모름",
    "알 수 없음",
    "확인 안 됨",
    "미확인",
    "unknown",
    "none",
    "null",
    "undefined",
}

def normalize_calculation_facts(
        facts: dict[str, Any],
        question: str = "",
) -> dict[str, Any]:
    normalized = normalize_fact_keys(
            facts
        )
    
    # 증여금액 변환: "6000만원" → 60000000
    gift_amount = parse_korean_amount(
        normalized.get("gift_amount")
    )
    if gift_amount is None:
        gift_amount = extract_korean_amount_from_text(
            question
        )
    normalized["gift_amount"] = gift_amount

    # 수증자 나이
    recipient_age = parse_age(
        normalized.get("recipient_age")
    )
    if recipient_age is None:
        recipient_age = extract_age_from_text(question)

    # 미성년 여부
    recipient_is_minor = (
        normalize_boolean_value(
            normalized.get(
                "recipient_is_minor"
            )
        )
    )

    # 숫자로 확인된 나이가 있으면 확인형 답변보다 우선한다.
    if recipient_age is not None:
        recipient_is_minor = (
            recipient_age < 19
        )

    normalized[
        "recipient_age"
    ] = recipient_age

    normalized[
        "recipient_is_minor"
    ] = recipient_is_minor

    # 관계값 변환
    raw_relationship = normalized.get(
        "relationship_type"
    )

    relationship_type = infer_relationship_from_question(
        question,
        raw_relationship=raw_relationship,
        recipient_is_minor=recipient_is_minor,
    )

    if relationship_type is None:
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

    if isinstance(value, bool):
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

    number = Decimal(match.group(1))
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


def extract_korean_amount_from_text(
    text: str,
) -> int | None:
    normalized = str(text or "").replace(
        ",",
        "",
    ).replace(
        " ",
        "",
    )
    match = re.search(
        r"\d+(?:\.\d+)?(?:억원|억|천만원|만원|원)",
        normalized,
    )
    if not match:
        return None
    return parse_korean_amount(match.group())

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

def parse_age(
    value: Any,
) -> int | None:
    if value is None:
        return None

    if isinstance(value, int):
        return value

    match = re.search(
        r"\d+",
        str(value),
    )

    if not match:
        return None

    return int(match.group())


def extract_age_from_text(text: str) -> int | None:
    match = re.search(
        r"(?<!\d)(\d{1,3})\s*세(?!\d)",
        str(text or ""),
    )
    if not match:
        return None
    age = int(match.group(1))
    if 0 <= age <= 150:
        return age
    return None


def extract_calculation_facts_from_question(
    question: str,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    gift_amount = extract_korean_amount_from_text(question)
    recipient_age = extract_age_from_text(question)

    if gift_amount is not None:
        facts["gift_amount"] = gift_amount

    if recipient_age is not None:
        facts["recipient_age"] = recipient_age
        facts["recipient_is_minor"] = recipient_age < 19
    elif "미성년" in question:
        facts["recipient_is_minor"] = True
    elif "성년" in question or "성인" in question:
        facts["recipient_is_minor"] = False

    relationship_type = infer_relationship_from_question(
        question,
        recipient_is_minor=facts.get("recipient_is_minor"),
    )
    if relationship_type is not None:
        facts["relationship_type"] = relationship_type

    return facts


def infer_relationship_from_question(
    question: str,
    *,
    raw_relationship: Any = None,
    recipient_is_minor: bool | None = None,
) -> str | None:
    text = str(question or "").replace(" ", "")
    raw_text = str(raw_relationship or "").strip()
    child_words = ("자녀", "아들", "딸")
    parent_words = ("부모", "아버지", "어머니")

    has_child = any(word in text for word in child_words)
    has_parent = any(word in text for word in parent_words)

    parent_is_donor = any(
        pattern in text
        for pattern in (
            "부모가자녀에게",
            "부모가아들에게",
            "부모가딸에게",
            "아버지가자녀에게",
            "어머니가자녀에게",
        )
    )
    child_is_donor = any(
        pattern in text
        for pattern in (
            "자녀가부모에게",
            "아들이부모에게",
            "딸이부모에게",
        )
    )

    if parent_is_donor or (
        has_child
        and raw_text in parent_words
        and not child_is_donor
    ):
        return (
            "parent_to_minor_child"
            if recipient_is_minor
            else "parent_to_adult_child"
        )

    if child_is_donor or (
        has_parent
        and raw_text in child_words
        and not parent_is_donor
    ):
        return "child_to_parent"

    return None

def normalize_relationship_type(
    value: Any,
    recipient_is_minor: bool | None = None,
) -> str | None:
    text = str(value).strip()

    if text in {
        "spouse",
        "parent_to_adult_child",
        "parent_to_minor_child",
        "child_to_parent",
        "other_relative",
        "other",
    }:
        return text

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

def is_unknown_value(
    value: Any,
) -> bool:
    """
    입력값이 비어 있거나 확인되지 않은 값인지 판정한다.

    주의:
    - 0은 정상적인 값이므로 unknown으로 판단하지 않는다.
    - False도 정상적인 값이므로 unknown으로 판단하지 않는다.
    """
    if value is None:
        return True

    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in UNKNOWN_VALUES

    return False
