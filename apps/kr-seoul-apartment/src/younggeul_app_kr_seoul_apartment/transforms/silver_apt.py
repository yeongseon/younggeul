from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from younggeul_core.connectors.hashing import sha256_payload
from younggeul_core.state.bronze import BronzeAptTransaction
from younggeul_core.state.silver import SilverAptTransaction, SilverDataQualityScore

SEOUL_GU_CODES: dict[str, str] = {
    "11110": "종로구",
    "11140": "중구",
    "11170": "용산구",
    "11200": "성동구",
    "11215": "광진구",
    "11230": "동대문구",
    "11260": "중랑구",
    "11290": "성북구",
    "11305": "강북구",
    "11320": "도봉구",
    "11350": "노원구",
    "11380": "은평구",
    "11410": "서대문구",
    "11440": "마포구",
    "11470": "양천구",
    "11500": "강서구",
    "11530": "구로구",
    "11545": "금천구",
    "11560": "영등포구",
    "11590": "동작구",
    "11620": "관악구",
    "11650": "서초구",
    "11680": "강남구",
    "11710": "송파구",
    "11740": "강동구",
}


def parse_deal_amount(raw: str | None) -> int | None:
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
    if sgg_code in SEOUL_GU_CODES:
        return sgg_code
    return None


def derive_gu_name(gu_code: str | None) -> str | None:
    if gu_code is None:
        return None
    return SEOUL_GU_CODES.get(gu_code)


def is_cancelled(cancel_deal_type: str | None) -> bool:
    if cancel_deal_type is None:
        return False
    return bool(cancel_deal_type.strip())


def generate_transaction_id(bronze: BronzeAptTransaction) -> str:
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
    return sha256_payload(payload)


def compute_quality_score(bronze: BronzeAptTransaction, silver_fields: dict[str, object]) -> SilverDataQualityScore:
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
    normalized: list[SilverAptTransaction] = []
    for record in records:
        silver = normalize_apt_transaction(record)
        if silver is not None:
            normalized.append(silver)
    return normalized
