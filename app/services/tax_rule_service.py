from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.repositories.tax_rule_repository import TaxRuleRepository
from app.schemas.tax_rule import GiftTaxBracket, GiftTaxRules


logger = logging.getLogger("uvicorn.error")

LINEAL_DESCENDANT_RELATIONSHIPS = {
    "parent_to_adult_child": False,
    "parent_to_minor_child": True,
}
OTHER_RELATIONSHIPS = {
    "other_relative",
    "other",
}


class TaxRuleNotFoundError(RuntimeError):
    pass


class UnsupportedTaxRuleRelationError(ValueError):
    pass


class TaxRuleService:
    def __init__(
        self,
        repository: TaxRuleRepository,
    ) -> None:
        self.repository = repository

    def load_rules(
        self,
        *,
        relationship_type: str,
        recipient_is_minor: bool | None,
        gift_date: Any = None,
    ) -> GiftTaxRules:
        effective_date = parse_effective_date(gift_date)
        relation, is_minor = map_deduction_relation(
            relationship_type,
            recipient_is_minor,
        )
        deduction_limit = self.repository.find_deduction_limit(
            effective_date=effective_date,
            relation=relation,
            is_minor=is_minor,
        )
        if deduction_limit is None:
            raise TaxRuleNotFoundError(
                "적용 가능한 증여재산공제 규칙이 없습니다. "
                f"date={effective_date} relation={relation} "
                f"is_minor={is_minor}"
            )

        brackets = self.repository.find_tax_brackets(
            effective_date=effective_date
        )
        validate_tax_brackets(brackets)
        logger.info(
            "gift_tax.rules_loaded effective_date=%s relation=%s "
            "is_minor=%s deduction_limit=%d bracket_count=%d",
            effective_date,
            relation,
            is_minor,
            deduction_limit,
            len(brackets),
        )
        return GiftTaxRules(
            effective_date=effective_date,
            deduction_limit=deduction_limit,
            brackets=tuple(brackets),
        )


def parse_effective_date(value: Any) -> date:
    if value is None or str(value).strip() == "":
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(
            "gift_date는 YYYY-MM-DD 형식이어야 합니다."
        ) from exc


def map_deduction_relation(
    relationship_type: str,
    recipient_is_minor: bool | None,
) -> tuple[str, bool]:
    if relationship_type in LINEAL_DESCENDANT_RELATIONSHIPS:
        expected_minor = LINEAL_DESCENDANT_RELATIONSHIPS[
            relationship_type
        ]
        if (
            recipient_is_minor is not None
            and recipient_is_minor is not expected_minor
        ):
            raise ValueError(
                "relationship_type과 recipient_is_minor가 충돌합니다."
            )
        return "LINEAL_DESCENDANT", expected_minor

    if relationship_type in OTHER_RELATIONSHIPS:
        if recipient_is_minor:
            raise UnsupportedTaxRuleRelationError(
                "OTHER 관계의 미성년 공제 규칙은 테이블 제약상 "
                "등록할 수 없습니다."
            )
        return "OTHER", False

    raise UnsupportedTaxRuleRelationError(
        "gift_deduction_limit.relation이 LINEAL_DESCENDANT와 OTHER만 "
        f"지원하여 {relationship_type!r} 공제를 구분할 수 없습니다."
    )


def validate_tax_brackets(
    brackets: list[GiftTaxBracket],
) -> None:
    if not brackets:
        raise TaxRuleNotFoundError(
            "적용 가능한 증여세율 구간이 없습니다."
        )
    previous_lower_bound = -1
    for bracket in brackets:
        if bracket.lower_bound <= previous_lower_bound:
            raise TaxRuleNotFoundError(
                "증여세율 구간의 lower_bound가 중복되거나 "
                "정렬되지 않았습니다."
            )
        if not Decimal("0") <= bracket.tax_rate <= Decimal("1"):
            raise TaxRuleNotFoundError(
                "증여세율은 0 이상 1 이하여야 합니다."
            )
        previous_lower_bound = bracket.lower_bound
