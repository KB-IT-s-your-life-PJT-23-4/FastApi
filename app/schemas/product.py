from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# =========================================================
# Enum
# =========================================================

class ProductType(str, Enum):
    DEPOSIT = "DEPOSIT"
    SAVINGS = "SAVINGS"
    ETF = "ETF"
    INSURANCE = "INSURANCE"


class SavingsCategory(str, Enum):
    FIXED_INSTALLMENT = "FIXED_INSTALLMENT"
    FREE_INSTALLMENT = "FREE_INSTALLMENT"


class InterestRateType(str, Enum):
    FIXED = "FIXED"
    REFER_TIER = "REFER_TIER"


class EtfCategory(str, Enum):
    DOMESTIC_INDEX = "DOMESTIC_INDEX"
    FOREIGN_INDEX = "FOREIGN_INDEX"
    BOND_MIXED = "BOND_MIXED"


class EtfAssetType(str, Enum):
    STOCK = "STOCK"
    BOND = "BOND"
    ETF = "ETF"
    FUTURES = "FUTURES"
    CASH = "CASH"


class InsurancePaymentType(str, Enum):
    LUMP_SUM = "LUMP_SUM"
    INSTALLMENT = "INSTALLMENT"


# =========================================================
# 공통 BaseModel
# =========================================================

class ProductSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
    )

# =========================================================
# 금리 구간
# interest_rate
# =========================================================

class InterestRateData(ProductSchema):
    tier_id: int | None = None

    product_category: SavingsCategory | None = None

    min_month: int | None = Field(
        ge=1,
        description="금리가 적용되기 시작하는 최소 가입 기간",
    )

    max_month: int | None = Field(
        default=None,
        ge=1,
        description="금리가 적용되는 최대 가입 기간, 제한이 없으면 null",
    )

    interest_rate: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=5,
        decimal_places=2,
        description="연 이자율(%)",
    )

    rete_type: InterestRateType = InterestRateType.FIXED

    reference_tier_id: int | None = Field(
        default=None,
        description="REFER_TIER인 경우 참조하는 금리 구간 ID",
    )

    base_date: date

    @model_validator(mode='after')
    def validate_rate_reference(self) -> InterestRateData:
        if(
            self.rate_type == InterestRateType.FIXED
            and self.interest_rate is None
        ):
            raise ValueError(
                "rate_type이 FIXED이면 interest_rate가 필요합니다."
            )

        if (
            self.rate_type == InterestRateType.REFER_TIER
            and self.reference_tier_id is None
        ):
            raise ValueError(
                "rate_type이 REFER_TIER이면"
                "reference_tier_id가 필요합니다."
            )

        if (
            self.max_month is not None
            and self.max_month < self.min_month
        ):
            raise ValueError(
                "max_month는 min_month보다 작을 수 없습니다."
            )

        return self

# =========================================================
# ETF
# =========================================================

class EtfHoldingData(ProductSchema):
    etf_holding_id: int | None = None

    holding_rank: int = Field(
        ge=1,
        description="구성종목 순위",
    )

    holding_name: str = Field(
        min_length=1,
        max_length=200,
    )

    holding_code: str | None = Field(
        default=None,
        max_length=50,
    )    

    weight: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("100"),
        max_digits=8,
        decimal_places=4,
        description="ETF 내 구성 비중(%)"
    )

    base_date: date

class EtfDetailData(ProductSchema):
    etf_id: int | None = None

    etf_name: str = Field(
        min_length=1,
        max_length=100,
    )

    stock_code: str = Field(
        min_length=1,
        max_length=20,
    )

    etf_category: EtfCategory

    benchmark_name: str = Field(
        min_length=1,
        max_length=200,
    )
    product_detail_url: str = Field(
        min_length=1,
        max_length=500,
    )

    stock_ratio: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
        max_digits=5,
        decimal_places=2,
        description="주식 비중(%)",
    )
    bond_ratio: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
        max_digits=5,
        decimal_places=2,
        description="채권 비중(%)",
    )

    annualized_volatility_5y: Decimal = Field(
        ge=Decimal("0"),
        max_digits=7,
        decimal_places=4,
        description="최근 5년 연환산 변동성(%)",
    )

    annual_return_5y: Decimal = Field(
        max_digits=7,
        decimal_places=4,
        description="최근 5년 연평균 수익률(%)",
    )

    performance_base_date: date

    holdings: list[EtfHoldingData] = Field(
        default_factory=list,
        description="기준일 기준 ETF 구성 종목",
    )

    @model_validator(mode="after")
    def validate_asset_ratios(self) -> EtfDetailData:
        if (
            self.stock_ratio is not None
            and self.bond_ratio is not None
            and self.stock_ratio + self.bond_ratio
            > Decimal("100")
        ):
            raise ValueError(
                "주식 비중과 채권 비중의 합은 "
                "100%를 초과할 수 없습니다."
            )

        return self


# =========================================================
# 적금
# =========================================================

class SavingsDetailData(ProductSchema):
    saving_id: int | None = None

    product_category: SavingsCategory

    min_monthly: int = Field(
        ge=0,
        description="최소 월 납입금액",
    )
    max_monthly: int | None = Field(
        default=None,
        ge=0,
        description="최대 월 납입금액. 제한이 없으면 null",
    )

    interest_rates: list[InterestRateData] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_monthly_limit(self) -> SavingsDetailData:
        if (
            self.max_monthly is not None
            and self.max_monthly < self.min_monthly
        ):
            raise ValueError(
                "max_monthly는 min_monthly보다 "
                "작을 수 없습니다."
            )

        for rate in self.interest_rates:
            if (
                rate.product_category is not None
                and rate.product_category
                != self.product_category
            ):
                raise ValueError(
                    "적금 상품 구분과 금리 구간의 "
                    "product_category가 일치하지 않습니다."
                )

        return self

# =========================================================
# 상품 공통 정보
# kb_product
# =========================================================

class ProductBaseData(ProductSchema):
    product_id: int
    product_name: str = Field(
        min_length=1,
        max_length=200,
    )
    description: str = Field(
        min_length=1,
    )


# =========================================================
# 상품 유형별 최종 스키마
# =========================================================

class DepositProductData(ProductBaseData):
    product_type: Literal[ProductType.DEPOSIT]

    interest_rates: list[InterestRateData] = Field(
        default_factory=list,
    )

class SavingsProductData(ProductBaseData):
    product_type: Literal[ProductType.SAVINGS]

    savings: list[SavingsDetailData] = Field(
        default_factory=list,
        description=(
            "정액적립식·자유적립식 등 적금 상품 세부 구분"
        ),
    )

class EtfProductData(ProductBaseData):
    product_type: Literal[ProductType.ETF]

    etf: EtfDetailData

ProductData = Annotated[
    (
        DepositProductData
        | SavingsProductData
        | EtfProductData
    ),
    Field(discriminator="product_type"),
]