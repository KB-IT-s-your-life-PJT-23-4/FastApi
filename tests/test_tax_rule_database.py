from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.repositories.tax_rule_repository import TaxRuleRepository
from app.schemas.tax_rule import GiftTaxBracket
from app.services.gift_tax_service import calculate_simple_gift_tax
from app.services.tax_rule_service import (
    TaxRuleService,
    UnsupportedTaxRuleRelationError,
    map_deduction_relation,
)


class FakeCursor:
    def __init__(self, *, one=None, all_rows=None) -> None:
        self.one = one
        self.all_rows = all_rows or []
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params) -> None:
        self.query = query
        self.params = params

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.all_rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def close(self) -> None:
        self.closed = True


def test_repository_loads_effective_deduction_limit() -> None:
    cursor = FakeCursor(one={"deduction_limit": 50_000_000})
    connection = FakeConnection(cursor)
    repository = TaxRuleRepository(lambda: connection)

    result = repository.find_deduction_limit(
        effective_date=date(2026, 8, 21),
        relation="LINEAL_DESCENDANT",
        is_minor=False,
    )

    assert result == 50_000_000
    assert "effective_from <= %s" in cursor.query
    assert "effective_to > %s" in cursor.query
    assert cursor.params == (
        "LINEAL_DESCENDANT",
        0,
        date(2026, 8, 21),
        date(2026, 8, 21),
    )
    assert connection.closed is True


def test_repository_loads_latest_active_bracket_version() -> None:
    cursor = FakeCursor(all_rows=[{
        "lower_bound": 0,
        "upper_bound": 100_000_000,
        "tax_rate": Decimal("0.1000"),
        "progressive_deduction": 0,
    }])
    repository = TaxRuleRepository(
        lambda: FakeConnection(cursor)
    )

    brackets = repository.find_tax_brackets(
        effective_date=date(2026, 8, 21)
    )

    assert "MAX(effective_from)" in cursor.query
    assert brackets == [
        GiftTaxBracket(
            lower_bound=0,
            upper_bound=100_000_000,
            tax_rate=Decimal("0.1000"),
            progressive_deduction=0,
        )
    ]


def test_tax_rule_service_maps_child_and_uses_gift_date() -> None:
    repository = SimpleNamespace(
        find_deduction_limit=lambda **kwargs: 20_000_000,
        find_tax_brackets=lambda **kwargs: [
            GiftTaxBracket(
                lower_bound=0,
                upper_bound=None,
                tax_rate=Decimal("0.15"),
                progressive_deduction=0,
            )
        ],
    )

    rules = TaxRuleService(repository).load_rules(
        relationship_type="parent_to_minor_child",
        recipient_is_minor=True,
        gift_date="2025-03-01",
    )

    assert rules.effective_date == date(2025, 3, 1)
    assert rules.deduction_limit == 20_000_000
    assert rules.brackets[0].tax_rate == Decimal("0.15")


def test_calculation_uses_rules_loaded_from_database() -> None:
    estimate = calculate_simple_gift_tax(
        gift_amount=30_000_000,
        relationship_type="parent_to_minor_child",
        deduction_limit=20_000_000,
        tax_brackets=[
            GiftTaxBracket(
                lower_bound=0,
                upper_bound=None,
                tax_rate=Decimal("0.15"),
                progressive_deduction=0,
            )
        ],
    )

    assert estimate.deduction_limit == 20_000_000
    assert estimate.taxable_base == 10_000_000
    assert estimate.tax_rate_percent == 15
    assert estimate.estimated_calculated_tax == 1_500_000


def test_unsupported_relation_is_not_silently_mapped_to_other() -> None:
    with pytest.raises(UnsupportedTaxRuleRelationError):
        map_deduction_relation("spouse", False)
