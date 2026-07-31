BLOCKED_INTENTS = {
    "other",            #기타 다른 질문 -> reject 해당 질문은 대답해 드릴 수가 없어요
    "jailbreak",        #탈옥 관련 프롬프트, 문자 인코딩 디코딩 관련 질문
}

RAG_INTENTS = {
    "concept",          #용어, 제도 설명
    "family",           #등록된 가족에 대한 증여세 계산
    "assessment",       #과세 여부 판단 및 간이 세액 계산
    "procedure",        #신고, 납부 절차
    "product"           #등록된 상품에 대한 설명
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
    "relationship_type",
    "recipient_age",
    "recipient_is_minor",
    "has_previous_gifts",
    "previous_gift_amount",
    "previous_gift_date",
    "previous_gift_same_donor",
    "previously_used_deduction",
}