from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SilverDataQualityScore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    completeness: float
    consistency: float
    overall: float

    @field_validator("completeness", "consistency", "overall")
    @classmethod
    def validate_score_range(cls, value: float) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError("score must be between 0.0 and 100.0")
        return value


class SilverAptTransaction(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    transaction_id: str
    deal_amount: int
    deal_date: date
    build_year: int
    dong_code: str
    dong_name: str
    gu_code: str
    gu_name: str
    apt_name: str
    floor: int
    area_exclusive_m2: Decimal = Field(decimal_places=2)
    jibun: str | None = None
    road_name: str | None = None
    is_cancelled: bool = False
    cancel_date: date | None = None
    deal_type: str | None = None
    source_id: str
    ingest_timestamp: datetime
    quality_score: SilverDataQualityScore | None = None


class SilverInterestRate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    rate_date: date
    rate_type: str
    rate_value: Decimal = Field(decimal_places=2)
    source_id: str
    ingest_timestamp: datetime


class SilverMigration(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    region_code: str
    region_name: str
    in_count: int
    out_count: int
    net_count: int
    source_id: str
    ingest_timestamp: datetime


class SilverComplexBridge(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    complex_id: str
    dong_code: str
    jibun: str | None = None
    road_name: str | None = None
    apt_name: str
    build_year: int | None = None
    matched_at: datetime
    match_method: Literal["exact_code", "jibun_match", "road_name_match"]
