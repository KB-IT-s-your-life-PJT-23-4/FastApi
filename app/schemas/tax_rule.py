from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class GiftTaxBracket:
    lower_bound: int
    upper_bound: int | None
    tax_rate: Decimal
    progressive_deduction: int


@dataclass(frozen=True)
class GiftTaxRules:
    effective_date: date
    deduction_limit: int
    brackets: tuple[GiftTaxBracket, ...]
