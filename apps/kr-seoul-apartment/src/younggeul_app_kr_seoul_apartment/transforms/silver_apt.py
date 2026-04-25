"""Silver normalization for apartment transaction Bronze records."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from younggeul_app_kr_seoul_apartment.canonical import SEOUL_GU_CODE_TO_NAME, SEOUL_GU_CODES
from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.state.bronze import BronzeAptTransaction
from younggeul_core.state.silver import SilverAptTransaction, SilverDataQualityScore


def parse_deal_amount(raw: str | None) -> int | None:
    """Parse 거래금액 text into KRW integer value.

    Args:
        raw: Raw deal amount string from Bronze data.

    Returns:
        Parsed amount in KRW, or ``None`` when parsing fails.
    """
    if raw is None:
        return None
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        amount_manwon = int(cleaned)
    except ValueError:
        return None
    return amount_manwon * 10_000


def parse_deal_date(year: str | None, month: str | None, day: str | None) -> date | None:
    """Parse year, month, and day strings into a date.

    Args:
        year: Raw year value.
        month: Raw month value.
        day: Raw day value.

    Returns:
        Parsed transaction date, or ``None`` if invalid.
    """
    y = parse_int(year)
    m = parse_int(month)
    d = parse_int(day)
    if y is None or m is None or d is None:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_int(raw: str | None) -> int | None:
    """Parse a stripped string into an integer.

    Args:
        raw: Raw numeric string.

    Returns:
        Parsed integer value, or ``None`` if invalid.
    """
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_decimal(raw: str | None) -> Decimal | None:
    """Parse a stripped string into a Decimal.

    Args:
        raw: Raw decimal string.

    Returns:
        Parsed decimal value, or ``None`` if invalid.
    """
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def derive_gu_code(sgg_code: str | None) -> str | None:
    """Resolve a Seoul 구 code from the provided sigungu code.

    Args:
        sgg_code: Raw sigungu code.

    Returns:
        Valid Seoul 구 code, or ``None`` when not supported.
    """
    if sgg_code in SEOUL_GU_CODES:
        return sgg_code
    return None


def derive_gu_name(gu_code: str | None) -> str | None:
    """Resolve a Seoul 구 name from a 구 code.

    Args:
        gu_code: Seoul 구 code.

    Returns:
        Matched 구 name, or ``None`` when unknown.
    """
    if gu_code is None:
        return None
    return SEOUL_GU_CODE_TO_NAME.get(gu_code)


def is_cancelled(cancel_deal_type: str | None) -> bool:
    """Determine whether a transaction is marked as canceled.

    Args:
        cancel_deal_type: Raw cancel marker from Bronze data.

    Returns:
        ``True`` when cancellation marker is present, otherwise ``False``.
    """
    if cancel_deal_type is None:
        return False
    return bool(cancel_deal_type.strip())


def generate_transaction_id(bronze: BronzeAptTransaction) -> str:
    """Generate a deterministic transaction identifier.

    Args:
        bronze: Source Bronze apartment transaction record.

    Returns:
        SHA-256 hash-based transaction identifier.
    """
    payload = [
        {
            "sgg_code": bronze.sgg_code,
            "deal_year": bronze.deal_year,
            "deal_month": bronze.deal_month,
            "deal_day": bronze.deal_day,
            "apt_name": bronze.apt_name,
            "floor": bronze.floor,
            "area_exclusive": bronze.area_exclusive,
            "serial_number": bronze.serial_number,
        }
    ]
    return str(sha256_payload(payload))


def compute_quality_score(bronze: BronzeAptTransaction, silver_fields: dict[str, object]) -> SilverDataQualityScore:
    """Compute Silver data quality scores for one transaction.

    Args:
        bronze: Source Bronze apartment transaction record.
        silver_fields: Parsed Silver field values used for scoring.

    Returns:
        Completeness, consistency, and overall quality score values.
    """
    _ = bronze

    completeness_fields = (
        "deal_amount",
        "deal_date",
        "gu_code",
        "apt_name",
        "floor",
        "area_exclusive_m2",
    )
    present_count = sum(1 for field in completeness_fields if silver_fields.get(field) is not None)
    completeness = (present_count / len(completeness_fields)) * 100.0

    consistency = 100.0
    floor = silver_fields.get("floor")
    area = silver_fields.get("area_exclusive_m2")
    build_year = silver_fields.get("build_year")
    deal_amount = silver_fields.get("deal_amount")

    if isinstance(floor, int):
        if floor < 1 or floor > 200:
            consistency -= 25.0
    else:
        consistency -= 25.0

    if isinstance(area, Decimal):
        if area < Decimal("1") or area > Decimal("1000"):
            consistency -= 25.0
    else:
        consistency -= 25.0

    if isinstance(build_year, int):
        if build_year < 1900 or build_year > 2030:
            consistency -= 25.0
    else:
        consistency -= 25.0

    if isinstance(deal_amount, int):
        if deal_amount <= 0:
            consistency -= 25.0
    else:
        consistency -= 25.0

    if consistency < 0.0:
        consistency = 0.0

    overall = (completeness + consistency) / 2.0
    return SilverDataQualityScore(
        completeness=completeness,
        consistency=consistency,
        overall=overall,
    )


def _parse_cancel_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if len(cleaned) != 8 or not cleaned.isdigit():
        return None
    return parse_deal_date(cleaned[0:4], cleaned[4:6], cleaned[6:8])


def normalize_apt_transaction(bronze: BronzeAptTransaction) -> SilverAptTransaction | None:
    """Normalize one Bronze apartment transaction into Silver shape.

    Args:
        bronze: Source Bronze apartment transaction record.

    Returns:
        Normalized Silver apartment transaction, or ``None`` if invalid.
    """
    gu_code = derive_gu_code(bronze.sgg_code)
    if gu_code is None:
        return None

    gu_name = derive_gu_name(gu_code)
    if gu_name is None:
        return None

    deal_amount = parse_deal_amount(bronze.deal_amount)
    deal_date = parse_deal_date(bronze.deal_year, bronze.deal_month, bronze.deal_day)
    build_year = parse_int(bronze.build_year)
    floor = parse_int(bronze.floor)
    area_exclusive_m2 = parse_decimal(bronze.area_exclusive)
    if area_exclusive_m2 is not None:
        area_exclusive_m2 = area_exclusive_m2.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if deal_amount is None or deal_date is None or build_year is None or floor is None or area_exclusive_m2 is None:
        return None

    dong_code = ""
    if bronze.sgg_code is not None and bronze.umd_code is not None:
        dong_code = f"{bronze.sgg_code}{bronze.umd_code}"

    apt_name = bronze.apt_name or ""
    silver_fields: dict[str, object] = {
        "deal_amount": deal_amount,
        "deal_date": deal_date,
        "gu_code": gu_code,
        "apt_name": apt_name,
        "floor": floor,
        "area_exclusive_m2": area_exclusive_m2,
        "build_year": build_year,
    }
    quality_score = compute_quality_score(bronze, silver_fields)

    return SilverAptTransaction(
        transaction_id=generate_transaction_id(bronze),
        deal_amount=deal_amount,
        deal_date=deal_date,
        build_year=build_year,
        dong_code=dong_code,
        dong_name=bronze.dong or "",
        gu_code=gu_code,
        gu_name=gu_name,
        apt_name=apt_name,
        floor=floor,
        area_exclusive_m2=area_exclusive_m2,
        jibun=bronze.jibun,
        road_name=bronze.road_name,
        is_cancelled=is_cancelled(bronze.cancel_deal_type),
        cancel_date=_parse_cancel_date(bronze.cancel_deal_day),
        deal_type=bronze.req_gbn,
        source_id=bronze.source_id,
        ingest_timestamp=bronze.ingest_timestamp,
        quality_score=quality_score,
    )


def normalize_batch(records: list[BronzeAptTransaction]) -> list[SilverAptTransaction]:
    """Normalize a batch of Bronze apartment transactions.

    Args:
        records: Bronze apartment transaction records.

    Returns:
        Successfully normalized Silver apartment transactions.
    """
    normalized: list[SilverAptTransaction] = []
    for record in records:
        silver = normalize_apt_transaction(record)
        if silver is not None:
            normalized.append(silver)
    return normalized
