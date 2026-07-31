from typing import Any

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

    # 수증자 나이
    recipient_age = parse_age(
        normalized.get("recipient_age")
    )

    # 미성년 여부
    recipient_is_minor = (
        normalize_boolean_value(
            normalized.get(
                "recipient_is_minor"
            )
        )
    )

    # 나이는 있지만 미성년 여부가 없다면
    # 간이 계산 기준으로 판단
    if (
        recipient_is_minor is None
        and recipient_age is not None
    ):
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