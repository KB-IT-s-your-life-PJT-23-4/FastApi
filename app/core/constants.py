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