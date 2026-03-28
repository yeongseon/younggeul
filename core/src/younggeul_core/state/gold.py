from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GoldDistrictMonthlyMetrics(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    gu_code: str
    gu_name: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    sale_count: int
    avg_price: int
    median_price: int
    min_price: int
    max_price: int
    price_per_pyeong_avg: int
    yoy_price_change: float | None = None
    mom_price_change: float | None = None
    yoy_volume_change: float | None = None
    mom_volume_change: float | None = None
    avg_area_m2: Decimal | None = None
    base_interest_rate: Decimal | None = Field(default=None, decimal_places=2)
    net_migration: int | None = None
    dataset_snapshot_id: str | None = None


class GoldComplexMonthlyMetrics(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    complex_id: str
    gu_code: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    sale_count: int
    avg_price: int
    median_price: int
    min_price: int
    max_price: int
    price_per_pyeong_avg: int


class BaselineForecast(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    gu_code: str
    gu_name: str
    target_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    direction: Literal["up", "down", "flat"]
    direction_confidence: float
    predicted_volume: int | None = None
    predicted_median_price: int | None = None
    model_name: str
    features_used: list[str] = Field(default_factory=list)

    @field_validator("direction_confidence")
    @classmethod
    def validate_direction_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("direction_confidence must be between 0.0 and 1.0")
        return value
