# app/data/gift_tax_rules.py

from __future__ import annotations

from typing import Any


GIFT_TAX_RATE_TABLE: list[dict[str, Any]] = [
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


GIFT_DEDUCTION_TABLE: dict[str, int] = {
    "spouse": 600_000_000,
    "parent_to_adult_child": 50_000_000,
    "parent_to_minor_child": 20_000_000,
    "child_to_parent": 50_000_000,
    "other_relative": 10_000_000,
    "other": 0,
}