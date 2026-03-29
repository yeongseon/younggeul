from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from younggeul_core.state.bronze import BronzeInterestRate, BronzeMigration
from younggeul_core.state.silver import SilverInterestRate, SilverMigration

_PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def parse_decimal_2dp(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_count(raw: str | None) -> int | None:
    if raw is None:
        return None
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def build_period(year: str | None, month: str | None) -> str | None:
    if year is None or month is None:
        return None
    year_clean = year.strip()
    month_clean = month.strip()
    if not year_clean or not month_clean:
        return None
    period = f"{year_clean}-{month_clean.zfill(2)}"
    if _PERIOD_PATTERN.fullmatch(period) is None:
        return None
    return period


def normalize_interest_rate(bronze: BronzeInterestRate) -> SilverInterestRate | None:
    rate_date = parse_date(bronze.date)
    if rate_date is None:
        return None

    rate_type = bronze.rate_type
    if rate_type is None or not rate_type.strip():
        return None

    rate_value = parse_decimal_2dp(bronze.rate_value)
    if rate_value is None:
        return None

    return SilverInterestRate(
        rate_date=rate_date,
        rate_type=rate_type,
        rate_value=rate_value,
        source_id=bronze.source_id,
        ingest_timestamp=bronze.ingest_timestamp,
    )


def normalize_migration(bronze: BronzeMigration) -> SilverMigration | None:
    period = build_period(bronze.year, bronze.month)
    if period is None:
        return None

    region_code = bronze.region_code
    if region_code is None or not region_code.strip():
        return None

    region_name = bronze.region_name
    if region_name is None or not region_name.strip():
        return None

    in_count = parse_count(bronze.in_count)
    out_count = parse_count(bronze.out_count)
    net_count = parse_count(bronze.net_count)
    if in_count is None or out_count is None or net_count is None:
        return None

    return SilverMigration(
        period=period,
        region_code=region_code,
        region_name=region_name,
        in_count=in_count,
        out_count=out_count,
        net_count=net_count,
        source_id=bronze.source_id,
        ingest_timestamp=bronze.ingest_timestamp,
    )


def normalize_interest_rate_batch(records: list[BronzeInterestRate]) -> list[SilverInterestRate]:
    normalized: list[SilverInterestRate] = []
    for record in records:
        silver = normalize_interest_rate(record)
        if silver is not None:
            normalized.append(silver)
    return normalized


def normalize_migration_batch(records: list[BronzeMigration]) -> list[SilverMigration]:
    normalized: list[SilverMigration] = []
    for record in records:
        silver = normalize_migration(record)
        if silver is not None:
            normalized.append(silver)
    return normalized
