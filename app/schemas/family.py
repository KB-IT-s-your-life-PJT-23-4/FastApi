from datetime import date

from pydantic import BaseModel, Field

class FamilyData(BaseModel):
    family_id: int
    name: str
    relationship_type: str
    gift_amount: int | None = Field(
        default=None,
        ge=0,
    )
    recipient_is_minor: bool | None = None
    has_previous_gifts: bool | None = None
    previous_gift_amount: int | None = Field(
        default=None,
        ge=0,
    )
    previous_gift_date: date | None = None
    previous_gift_same_donor: bool | None = None
    previously_used_deduction: int = Field(
        default=0,
        ge=0,
    )
    deduction_renewal_date: date | None = None
