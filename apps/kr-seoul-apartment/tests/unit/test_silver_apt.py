from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from younggeul_app_kr_seoul_apartment.canonical import SEOUL_GU_CODES
from younggeul_app_kr_seoul_apartment.transforms.silver_apt import (
    compute_quality_score,
    derive_gu_code,
    derive_gu_name,
    generate_transaction_id,
    is_cancelled,
    normalize_apt_transaction,
    normalize_batch,
    parse_deal_amount,
    parse_deal_date,
    parse_decimal,
    parse_int,
)
from younggeul_core.state.bronze import BronzeAptTransaction
from younggeul_core.state.silver import SilverAptTransaction

_FIXED_NOW = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)


def _base_bronze_data() -> dict[str, Any]:
    return {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "molit.apartment.transactions",
        "raw_response_hash": "abc" * 21 + "a",
        "deal_amount": "82,000",
        "build_year": "2016",
        "deal_year": "2025",
        "deal_month": "7",
        "deal_day": "15",
        "dong": "역삼동",
        "apt_name": "래미안",
        "floor": "12",
        "area_exclusive": "84.99",
        "jibun": "123-45",
        "road_name": "테헤란로",
        "serial_number": "2025-001",
        "cancel_deal_type": None,
        "cancel_deal_day": None,
        "req_gbn": "중개거래",
        "sgg_code": "11680",
        "umd_code": "10300",
    }


def _make_bronze(**overrides: Any) -> BronzeAptTransaction:
    payload = _base_bronze_data()
    payload.update(overrides)
    return BronzeAptTransaction(**payload)


class TestParseDealAmount:
    def test_none_returns_none(self) -> None:
        assert parse_deal_amount(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_deal_amount("") is None

    def test_comma_amount_82000(self) -> None:
        assert parse_deal_amount("82,000") == 820_000_000

    def test_comma_amount_50000(self) -> None:
        assert parse_deal_amount("50,000") == 500_000_000

    def test_no_comma_amount(self) -> None:
        assert parse_deal_amount("82000") == 820_000_000

    def test_invalid_returns_none(self) -> None:
        assert parse_deal_amount("abc") is None


class TestParseDealDate:
    def test_valid_date(self) -> None:
        assert parse_deal_date("2025", "7", "15") == date(2025, 7, 15)

    def test_none_year_returns_none(self) -> None:
        assert parse_deal_date(None, "7", "15") is None

    def test_none_month_returns_none(self) -> None:
        assert parse_deal_date("2025", None, "15") is None

    def test_none_day_returns_none(self) -> None:
        assert parse_deal_date("2025", "7", None) is None

    def test_invalid_day_returns_none(self) -> None:
        assert parse_deal_date("2025", "7", "32") is None


class TestParseInt:
    def test_valid_parse(self) -> None:
        assert parse_int("12") == 12

    def test_none_returns_none(self) -> None:
        assert parse_int(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_int("") is None

    def test_invalid_returns_none(self) -> None:
        assert parse_int("xx") is None


class TestParseDecimal:
    def test_valid_parse(self) -> None:
        assert parse_decimal("84.99") == Decimal("84.99")

    def test_none_returns_none(self) -> None:
        assert parse_decimal(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_decimal("") is None

    def test_invalid_returns_none(self) -> None:
        assert parse_decimal("xx") is None


class TestDeriveGuCode:
    def test_valid_seoul_code_returns_code(self) -> None:
        assert derive_gu_code("11680") == "11680"

    def test_all_canonical_codes_round_trip(self) -> None:
        for code in SEOUL_GU_CODES:
            assert derive_gu_code(code) == code

    def test_non_seoul_code_returns_none(self) -> None:
        assert derive_gu_code("41135") is None

    def test_none_returns_none(self) -> None:
        assert derive_gu_code(None) is None


class TestDeriveGuName:
    def test_valid_lookup_returns_name(self) -> None:
        assert derive_gu_name("11680") == "강남구"

    def test_all_canonical_codes_resolve_names(self) -> None:
        for code in SEOUL_GU_CODES:
            assert derive_gu_name(code) is not None

    def test_unknown_returns_none(self) -> None:
        assert derive_gu_name("99999") is None


class TestIsCancelled:
    def test_none_is_false(self) -> None:
        assert is_cancelled(None) is False

    def test_empty_is_false(self) -> None:
        assert is_cancelled("") is False

    def test_o_is_true(self) -> None:
        assert is_cancelled("O") is True

    def test_whitespace_is_false(self) -> None:
        assert is_cancelled("   ") is False


class TestGenerateTransactionId:
    def test_deterministic_for_same_record(self) -> None:
        bronze = _make_bronze()
        assert generate_transaction_id(bronze) == generate_transaction_id(bronze)

    def test_different_input_changes_id(self) -> None:
        bronze1 = _make_bronze(serial_number="2025-001")
        bronze2 = _make_bronze(serial_number="2025-002")
        assert generate_transaction_id(bronze1) != generate_transaction_id(bronze2)


class TestComputeQualityScore:
    def test_all_fields_present_high_score(self) -> None:
        bronze = _make_bronze()
        fields: dict[str, object] = {
            "deal_amount": 820_000_000,
            "deal_date": date(2025, 7, 15),
            "gu_code": "11680",
            "apt_name": "래미안",
            "floor": 12,
            "area_exclusive_m2": Decimal("84.99"),
            "build_year": 2016,
        }
        score = compute_quality_score(bronze, fields)
        assert score.completeness == 100.0
        assert score.consistency == 100.0
        assert score.overall == 100.0

    def test_missing_fields_lower_completeness(self) -> None:
        bronze = _make_bronze()
        fields: dict[str, object] = {
            "deal_amount": 820_000_000,
            "deal_date": date(2025, 7, 15),
            "gu_code": "11680",
            "apt_name": None,
            "floor": 12,
            "area_exclusive_m2": Decimal("84.99"),
            "build_year": 2016,
        }
        score = compute_quality_score(bronze, fields)
        assert score.completeness < 100.0
        assert score.consistency == 100.0

    def test_invalid_ranges_lower_consistency(self) -> None:
        bronze = _make_bronze()
        fields: dict[str, object] = {
            "deal_amount": -1,
            "deal_date": date(2025, 7, 15),
            "gu_code": "11680",
            "apt_name": "래미안",
            "floor": 0,
            "area_exclusive_m2": Decimal("1001"),
            "build_year": 1800,
        }
        score = compute_quality_score(bronze, fields)
        assert score.completeness == 100.0
        assert score.consistency == 0.0
        assert score.overall == 50.0


class TestNormalizeAptTransaction:
    def test_full_happy_path_maps_all_fields(self) -> None:
        bronze = _make_bronze()
        silver = normalize_apt_transaction(bronze)

        assert isinstance(silver, SilverAptTransaction)
        assert silver.transaction_id == generate_transaction_id(bronze)
        assert silver.deal_amount == 820_000_000
        assert silver.deal_date == date(2025, 7, 15)
        assert silver.build_year == 2016
        assert silver.dong_code == "1168010300"
        assert silver.dong_name == "역삼동"
        assert silver.gu_code == "11680"
        assert silver.gu_name == "강남구"
        assert silver.apt_name == "래미안"
        assert silver.floor == 12
        assert silver.area_exclusive_m2 == Decimal("84.99")
        assert silver.jibun == "123-45"
        assert silver.road_name == "테헤란로"
        assert silver.is_cancelled is False
        assert silver.cancel_date is None
        assert silver.deal_type == "중개거래"
        assert silver.source_id == "molit.apartment.transactions"
        assert silver.ingest_timestamp == _FIXED_NOW
        assert silver.quality_score is not None
        assert silver.quality_score.overall == 100.0

    def test_non_seoul_filtered_out(self) -> None:
        bronze = _make_bronze(sgg_code="41135")
        assert normalize_apt_transaction(bronze) is None

    def test_cancelled_transaction_flag_true(self) -> None:
        bronze = _make_bronze(cancel_deal_type="O", cancel_deal_day="20250720")
        silver = normalize_apt_transaction(bronze)
        assert silver is not None
        assert silver.is_cancelled is True
        assert silver.cancel_date == date(2025, 7, 20)

    def test_missing_optional_fields_handled(self) -> None:
        bronze = _make_bronze(jibun=None, road_name=None, dong=None, umd_code=None, req_gbn=None)
        silver = normalize_apt_transaction(bronze)
        assert silver is not None
        assert silver.jibun is None
        assert silver.road_name is None
        assert silver.dong_name == ""
        assert silver.dong_code == ""
        assert silver.deal_type is None

    def test_unparseable_build_year_skipped(self) -> None:
        bronze = _make_bronze(build_year="abc")
        assert normalize_apt_transaction(bronze) is None

    def test_unparseable_floor_skipped(self) -> None:
        bronze = _make_bronze(floor="abc")
        assert normalize_apt_transaction(bronze) is None

    def test_unparseable_deal_amount_skipped(self) -> None:
        bronze = _make_bronze(deal_amount="abc")
        assert normalize_apt_transaction(bronze) is None

    def test_unparseable_deal_date_skipped(self) -> None:
        bronze = _make_bronze(deal_day="32")
        assert normalize_apt_transaction(bronze) is None


class TestNormalizeBatch:
    def test_filters_out_non_seoul_and_keeps_seoul(self) -> None:
        seoul = _make_bronze(sgg_code="11680")
        non_seoul = _make_bronze(sgg_code="41135")
        rows = normalize_batch([seoul, non_seoul])
        assert len(rows) == 1
        assert rows[0].gu_code == "11680"

    def test_skips_invalid_required_parse_fields(self) -> None:
        valid = _make_bronze()
        invalid = _make_bronze(build_year="bad")
        rows = normalize_batch([valid, invalid])
        assert len(rows) == 1
        assert rows[0].build_year == 2016
