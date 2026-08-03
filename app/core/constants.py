BLOCKED_INTENTS = {
    "other",            #기타 다른 질문 -> reject 해당 질문은 대답해 드릴 수가 없어요
    "jailbreak",        #탈옥 관련 프롬프트, 문자 인코딩 디코딩 관련 질문
}

RAG_INTENTS = {
    "concept",          #용어, 제도 설명
    "family",           #등록된 가족에 대한 증여세 계산
    "assessment",       #과세 여부 판단 및 간이 세액 계산
    "procedure",        #신고, 납부 절차
    "product",          #등록된 상품에 대한 설명
    "other_gift",       #위 유형에 포함되지 않는 증여세 관련 질문
}

CALCULATION_INTENTS = {
    "family",
    "assessment",
}

DEFAULT_FACTS = {
    "residency": "국내 거주자",
    "use_latest_tax_rate": True,
}

FAMILY_FACT_KEYS = {
    "gift_amount",
    "relationship_type",
    "recipient_age",
    "recipient_is_minor",
    "has_previous_gifts",
    "previous_gift_amount",
    "previous_gift_date",
    "previous_gift_same_donor",
    "previously_used_deduction",
    "deduction_renewal_date",
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

    # 나이·미성년 여부
    "자녀의 나이": "recipient_age",
    "수증자의 나이": "recipient_age",
    "나이": "recipient_age",
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
