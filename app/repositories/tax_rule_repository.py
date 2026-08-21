from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.schemas.tax_rule import GiftTaxBracket


class DatabaseConnection(Protocol):
    def cursor(self): ...

    def close(self) -> None: ...


class TaxRuleRepository:
    def __init__(
        self,
        connection_factory: Callable[[], DatabaseConnection],
    ) -> None:
        self.connection_factory = connection_factory

    def find_deduction_limit(
        self,
        *,
        effective_date: date,
        relation: str,
        is_minor: bool,
    ) -> int | None:
        query = """
            SELECT deduction_limit
            FROM gift_deduction_limit
            WHERE relation = %s
              AND is_minor = %s
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to > %s)
            ORDER BY effective_from DESC, deduction_limit_id DESC
            LIMIT 1
        """
        row = self._fetch_one(
            query,
            (
                relation,
                int(is_minor),
                effective_date,
                effective_date,
            ),
        )
        if row is None:
            return None
        return int(row["deduction_limit"])

    def find_tax_brackets(
        self,
        *,
        effective_date: date,
    ) -> list[GiftTaxBracket]:
        query = """
            SELECT
                lower_bound,
                upper_bound,
                tax_rate,
                progressive_deduction
            FROM gift_tax_bracket
            WHERE effective_from = (
                SELECT MAX(effective_from)
                FROM gift_tax_bracket
                WHERE effective_from <= %s
                  AND (effective_to IS NULL OR effective_to > %s)
            )
              AND effective_from <= %s
              AND (effective_to IS NULL OR effective_to > %s)
            ORDER BY lower_bound ASC
        """
        rows = self._fetch_all(
            query,
            (
                effective_date,
                effective_date,
                effective_date,
                effective_date,
            ),
        )
        return [
            GiftTaxBracket(
                lower_bound=int(row["lower_bound"]),
                upper_bound=(
                    int(row["upper_bound"])
                    if row["upper_bound"] is not None
                    else None
                ),
                tax_rate=Decimal(str(row["tax_rate"])),
                progressive_deduction=int(
                    row["progressive_deduction"]
                ),
            )
            for row in rows
        ]

    def _fetch_one(
        self,
        query: str,
        params: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        finally:
            connection.close()

    def _fetch_all(
        self,
        query: str,
        params: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        connection = self.connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())
        finally:
            connection.close()
