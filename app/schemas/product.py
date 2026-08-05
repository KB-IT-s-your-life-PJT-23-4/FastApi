from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )


class ProductData(ProductSchema):
    """예금/적금 정보"""

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


class EtfProductData(ProductSchema):
    """ETF 정보"""

    product_name: str = Field(
        min_length=1,
        max_length=200,
    )

    tracking_index: str = Field(
        min_length=1,
        max_length=200,
        description="추종 지수",
    )

    annual_return_5y: Decimal = Field(
        max_digits=8,
        decimal_places=4,
        description="5년 연평균 수익률(%)",
    )