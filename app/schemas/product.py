from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class ProductData(ProductSchema):
    """AI 상담 요청 전용 간소화 상품 정보"""

    product_name: str = Field(
        min_length=1,
        max_length=200,
    )

    interest_rate: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        description="연 이자율(%)",
    )

    preferential_condition: str | None = Field(
        default=None,
        description="우대조건 설명 (여러 개면 콤마로 연결된 텍스트)",
    )