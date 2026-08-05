from __future__ import annotations

from typing import Any

from app.core.constants import (
    CALCULATION_INTENTS,
    FAMILY_FACT_KEYS
)
from app.data.gift_tax_rules import (
    GIFT_DEDUCTION_TABLE,
    GIFT_TAX_RATE_TABLE
)
from app.prompts.context import(
    build_calculation_error_context,
    build_calculation_failure_context,
    build_family_context,
    build_families_context,
    build_gift_tax_calculation_context,
    build_gift_tax_rule_context,
    build_product_context,
    combine_contexts
)
from app.schemas.product import ProductData, EtfProductData
from app.services.fact_normalization_service import (
    normalize_calculation_facts,
    validate_estimate_facts,
)
from app.services.gift_tax_service import create_tax_estimate_from_facts

class ContextService:
    """
    LLM에 전달할 Context 문자열을 생성하고 조립하는 서비스.

    역할:
    - 가족 데이터 Context 생성
    - 상품 데이터 Context 생성
    - RAG Context와 결합
    - 계산 가능 여부 확인
    - 증여세율 및 공제 규칙 Context 추가
    """

    def extract_family_facts(
        self,
        family_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        가족 데이터 중 증여 계산에 필요한 필드만 추출한다.
        """
        if not family_data:
            return {}

        return {
            key: value
            for key, value in family_data.items()
            if key in FAMILY_FACT_KEYS
        }


    def build_family_context(
        self,
        family_data: dict[str, Any] | None,
    ) -> str:
        """
        가족 데이터를 LLM용 문자열 Context로 변환한다.
        """
        if not family_data:
            return ""

        return build_family_context(
            family_data
        )

    def build_families_context(
        self,
        families_data: list[dict[str, Any]] | None,
    ) -> str:
        """등록 가족 목록을 이름 선택 규칙과 함께 LLM Context로 변환한다."""
        return build_families_context(
            families_data
        )

    def build_product_context(
        self,
        product_data: ProductData | dict[str, Any] | None,
    ) -> str:
        """
        단일 상품 데이터를 LLM용 문자열 Context로 변환한다.
        """
        if product_data is None:
            return ""

        if hasattr(product_data, "model_dump"):
            product_dict = product_data.model_dump(
                mode="json"
            )
        else:
            product_dict = product_data

        return build_product_context(
            product_dict
        )

    def build_products_context(
        self,
        products: list[ProductData] | None,
    ) -> str:
        """
        여러 상품을 하나의 상품 Context로 조립한다.
        """
        if not products:
            return ""

        contexts: list[str] = []

        for index, product in enumerate(
            products,
            start=1,
        ):
            product_dict = product.model_dump(
                mode="json"
            )

            context = build_product_context(
                product_dict
            )

            if not context.strip():
                continue

            contexts.append(
                f"""
===== 선택 상품 {index} =====

{context}
""".strip()
            )

        return self.combine(*contexts)

    def build_etf_products_context(
        self,
        etf_products: list[EtfProductData] | None,
    ) -> str:
        """
        여러 ETF 상품을 하나의 Context로 조립한다.
        """
        if not etf_products:
            return ""

        contexts: list[str] = []

        for index, etf_product in enumerate(etf_products, start=1):
            etf_dict = etf_product.model_dump(mode="json")

            context = build_product_context(etf_dict)

            if not context.strip():
                continue

            contexts.append(
                f"""
    ===== 선택 ETF {index} =====

    {context}
    """.strip()
            )

        return self.combine(*contexts)

    def combine(
        self,
        *contexts: str | None,
    ) -> str:
        """
        비어 있지 않은 Context만 결합한다.
        """
        filtered_contexts = [
            context.strip()
            for context in contexts
            if context and context.strip()
        ]

        if not filtered_contexts:
            return ""

        return combine_contexts(
            *filtered_contexts
        )

    def build_base_context(
        self,
        *,
        family_data: dict[str, Any] | None = None,
        product_data: ProductData | None = None,
        products: list[ProductData] | None = None,
        rag_context: str = "",
    ) -> str:
        """
        가족, 상품, RAG Context를 하나로 결합한다.

        product_data와 products가 동시에 넘어오면
        products를 우선 사용한다.
        """
        family_context = self.build_family_context(
            family_data
        )

        if products:
            product_context = self.build_products_context(
                products
            )
        else:
            product_context = self.build_product_context(
                product_data
            )

        return self.combine(
            family_context,
            product_context,
            rag_context,
        )

    def build_final_context(
        self,
        *,
        base_context: str,
        facts: dict[str, Any],
        question: str,
        intent: str,
        requires_calculation: bool,
    ) -> tuple[str, dict[str, Any]]:
        """
        계산 필요 여부에 따라 세법 규칙 또는 계산 실패 안내를 추가한다.

        반환값:
        - 최종 Context
        - 정규화된 facts
        """
        normalized_facts = {
            **facts
        }

        gift_tax_rule_context = ""
        gift_tax_calculation_context = ""
        calculation_notice = ""

        should_calculate = (
            intent in CALCULATION_INTENTS
            and requires_calculation
        )

        if should_calculate:
            normalized_facts = (
                normalize_calculation_facts(
                    normalized_facts,
                    question=question,
                )
            )

            missing_facts = validate_estimate_facts(
                normalized_facts
            )

            if missing_facts:
                calculation_notice = (
                    build_calculation_failure_context(
                        missing_facts
                    )
                )
            else:
                gift_tax_rule_context = (
                    build_gift_tax_rule_context(
                        rate_table=GIFT_TAX_RATE_TABLE,
                        deduction_table=(
                            GIFT_DEDUCTION_TABLE
                        ),
                        relationship_type=(
                            normalized_facts.get(
                                "relationship_type"
                            )
                        ),
                    )
                )
                try:
                    estimate = create_tax_estimate_from_facts(
                        normalized_facts
                    )
                except (TypeError, ValueError, RuntimeError):
                    estimate = None
                if estimate is None:
                    calculation_notice = build_calculation_error_context()
                else:
                    calculation = estimate.to_dict()
                    normalized_facts["tax_calculation"] = calculation
                    gift_tax_calculation_context = (
                        build_gift_tax_calculation_context(calculation)
                    )

        final_context = self.combine(
            base_context,
            gift_tax_rule_context,
            gift_tax_calculation_context,
            calculation_notice,
        )

        return (
            final_context,
            normalized_facts,
        )
