from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from app.data.gift_tax_rules import (
    GIFT_DEDUCTION_TABLE,
    GIFT_TAX_RATE_TABLE,
)
from app.services.fact_normalization_service import validate_estimate_facts

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class GiftTaxEstimate:
    gift_amount: int
    previous_gift_amount: int
    total_gift_amount: int
    deduction_limit: int
    previously_used_deduction: int
    applied_deduction: int
    taxable_base: int
    tax_rate_percent: int
    progressive_deduction: int
    estimated_calculated_tax: int
    is_estimate: bool = True

    def to_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def apply_gift_tax_rate(
    taxable_base: int,
) -> tuple[int, int, int]:
    """과세표준에 해당하는 세율, 누진공제액, 산출세액을 반환한다."""
    if taxable_base <= 0:
        logger.info(
            "gift_tax.rate_selected taxable_base=%d "
            "tax_rate_percent=0 progressive_deduction=0 "
            "calculated_tax=0",
            taxable_base,
        )
        return 0, 0, 0

    for bracket in GIFT_TAX_RATE_TABLE:
        upper_limit = bracket["upper_limit"]
        if upper_limit is None or taxable_base <= upper_limit:
            rate = Decimal(str(bracket["rate"]))
            rate_percent = int(rate * 100)
            progressive_deduction = int(
                bracket["progressive_deduction"]
            )
            calculated_tax = int(
                Decimal(taxable_base) * rate
                - progressive_deduction
            )
            calculated_tax = max(calculated_tax, 0)
            logger.info(
                "gift_tax.rate_selected taxable_base=%d "
                "tax_rate_percent=%d progressive_deduction=%d "
                "calculated_tax=%d",
                taxable_base,
                rate_percent,
                progressive_deduction,
                calculated_tax,
            )
            return (
                rate_percent,
                progressive_deduction,
                calculated_tax,
            )

    raise RuntimeError("적용 가능한 증여세율 구간이 없습니다.")


def create_tax_estimate_from_facts(
    facts: dict[str, Any],
) -> GiftTaxEstimate | None:
    """정규화가 끝난 facts로 서버 간이 계산 결과를 만든다."""
    if validate_estimate_facts(facts):
        return None

    gift_amount = facts.get("gift_amount")
    relationship_type = facts.get("relationship_type")
    previous_gift_amount = facts.get("previous_gift_amount", 0)
    previously_used_deduction = facts.get(
        "previously_used_deduction",
        0,
    )

    integer_values = (
        gift_amount,
        previous_gift_amount,
        previously_used_deduction,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in integer_values
    ):
        return None
    if not isinstance(relationship_type, str):
        return None

    return calculate_simple_gift_tax(
        gift_amount=gift_amount,
        relationship_type=relationship_type,
        previous_gift_amount=previous_gift_amount,
        previously_used_deduction=previously_used_deduction,
    )


def calculate_simple_gift_tax(
    *,
    gift_amount: int,
    relationship_type: str,
    previous_gift_amount: int = 0,
    previously_used_deduction: int = 0,
) -> GiftTaxEstimate:
    """현재 프로젝트 기준에 따른 증여세 간이 산출세액을 계산한다."""
    for field_name, value in {
        "gift_amount": gift_amount,
        "previous_gift_amount": previous_gift_amount,
        "previously_used_deduction": previously_used_deduction,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field_name}은 원 단위 정수여야 합니다.")
        if value < 0:
            raise ValueError(f"{field_name}은 0원 이상이어야 합니다.")

    logger.info(
        "gift_tax.calculation_started relationship_type=%s "
        "gift_amount=%d previous_gift_amount=%d "
        "previously_used_deduction=%d",
        relationship_type,
        gift_amount,
        previous_gift_amount,
        previously_used_deduction,
    )

    deduction_limit = GIFT_DEDUCTION_TABLE.get(relationship_type, 0)
    total_gift_amount = gift_amount + previous_gift_amount
    applied_deduction = min(total_gift_amount, deduction_limit)
    logger.info(
        "gift_tax.deduction_applied deduction_limit=%d "
        "previously_used_deduction=%d applied_deduction=%d",
        deduction_limit,
        previously_used_deduction,
        applied_deduction,
    )
    taxable_base = max(
        total_gift_amount - applied_deduction,
        0,
    )
    logger.info(
        "gift_tax.taxable_base_calculated total_gift_amount=%d "
        "applied_deduction=%d taxable_base=%d",
        total_gift_amount,
        applied_deduction,
        taxable_base,
    )
    (
        tax_rate_percent,
        progressive_deduction,
        calculated_tax,
    ) = apply_gift_tax_rate(taxable_base)

    estimate = GiftTaxEstimate(
        gift_amount=gift_amount,
        previous_gift_amount=previous_gift_amount,
        total_gift_amount=total_gift_amount,
        deduction_limit=deduction_limit,
        previously_used_deduction=previously_used_deduction,
        applied_deduction=applied_deduction,
        taxable_base=taxable_base,
        tax_rate_percent=tax_rate_percent,
        progressive_deduction=progressive_deduction,
        estimated_calculated_tax=calculated_tax,
    )
    logger.info(
        "gift_tax.calculation_completed taxable_base=%d "
        "tax_rate_percent=%d progressive_deduction=%d "
        "estimated_calculated_tax=%d",
        estimate.taxable_base,
        estimate.tax_rate_percent,
        estimate.progressive_deduction,
        estimate.estimated_calculated_tax,
    )
    return estimate
