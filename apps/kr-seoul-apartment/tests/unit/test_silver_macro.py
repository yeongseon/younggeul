from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from younggeul_app_kr_seoul_apartment.transforms.silver_macro import (
    build_period,
    normalize_interest_rate,
    normalize_interest_rate_batch,
    normalize_migration,
    normalize_migration_batch,
    parse_count,
    parse_date,
    parse_decimal_2dp,
)
from younggeul_core.state.bronze import BronzeInterestRate, BronzeMigration
from younggeul_core.state.silver import SilverInterestRate, SilverMigration

_FIXED_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _base_rate_data() -> dict[str, Any]:
    return {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "bank_of_korea_base_rate",
        "raw_response_hash": "abc" * 21 + "a",
        "date": "2024-01-15",
        "rate_type": "base_rate",
        "rate_value": "3.50",
        "unit": "%",
    }


def _make_bronze_rate(**overrides: Any) -> BronzeInterestRate:
    payload = _base_rate_data()
    payload.update(overrides)
    return BronzeInterestRate(**payload)


def _base_migration_data() -> dict[str, Any]:
    return {
        "ingest_timestamp": _FIXED_NOW,
        "source_id": "kostat_population_migration",
        "raw_response_hash": "abc" * 21 + "a",
        "year": "2023",
        "month": "01",
        "region_code": "11",
        "region_name": "서울특별시",
        "in_count": "150000",
        "out_count": "140000",
        "net_count": "10000",
    }


def _make_bronze_migration(**overrides: Any) -> BronzeMigration:
    payload = _base_migration_data()
    payload.update(overrides)
    return BronzeMigration(**payload)


class TestParseDate:
    def test_valid_date_returns_date(self) -> None:
        assert parse_date("2024-01-15") == date(2024, 1, 15)

    def test_valid_month_start_date_returns_date(self) -> None:
        assert parse_date("2024-01-01") == date(2024, 1, 1)

    def test_none_returns_none(self) -> None:
        assert parse_date(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_date("") is None

    def test_invalid_format_returns_none(self) -> None:
        assert parse_date("2024/01/15") is None

    def test_invalid_date_returns_none(self) -> None:
        assert parse_date("2024-02-30") is None


class TestParseDecimal2dp:
    def test_valid_decimal_returns_decimal(self) -> None:
        assert parse_decimal_2dp("3.50") == Decimal("3.50")

    def test_quantizes_more_than_two_decimal_places(self) -> None:
        assert parse_decimal_2dp("3.456") == Decimal("3.46")

    def test_none_returns_none(self) -> None:
        assert parse_decimal_2dp(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_decimal_2dp("") is None

    def test_whitespace_returns_none(self) -> None:
        assert parse_decimal_2dp("   ") is None

    def test_invalid_decimal_returns_none(self) -> None:
        assert parse_decimal_2dp("abc") is None


class TestParseCount:
    def test_plain_integer_string(self) -> None:
        assert parse_count("150000") == 150000

    def test_comma_separated_integer_string(self) -> None:
        assert parse_count("150,000") == 150000

    def test_leading_trailing_whitespace(self) -> None:
        assert parse_count("  1,234  ") == 1234

    def test_negative_count_is_supported(self) -> None:
        assert parse_count("-100") == -100

    def test_none_returns_none(self) -> None:
        assert parse_count(None) is None

    def test_invalid_returns_none(self) -> None:
        assert parse_count("1.5") is None


class TestBuildPeriod:
    def test_valid_year_month_returns_period(self) -> None:
        assert build_period("2023", "01") == "2023-01"

    def test_single_digit_month_is_zero_padded(self) -> None:
        assert build_period("2023", "1") == "2023-01"

    def test_none_year_returns_none(self) -> None:
        assert build_period(None, "01") is None

    def test_none_month_returns_none(self) -> None:
        assert build_period("2023", None) is None

    def test_empty_year_returns_none(self) -> None:
        assert build_period("", "01") is None

    def test_month_zero_returns_none(self) -> None:
        assert build_period("2023", "00") is None

    def test_month_thirteen_returns_none(self) -> None:
        assert build_period("2023", "13") is None

    def test_non_numeric_year_returns_none(self) -> None:
        assert build_period("20a3", "01") is None

    def test_three_digit_month_returns_none(self) -> None:
        assert build_period("2023", "001") is None


class TestNormalizeInterestRate:
    def test_happy_path_maps_required_fields(self) -> None:
        bronze = _make_bronze_rate()
        silver = normalize_interest_rate(bronze)

        assert isinstance(silver, SilverInterestRate)
        assert silver.rate_date == date(2024, 1, 15)
        assert silver.rate_type == "base_rate"
        assert silver.rate_value == Decimal("3.50")
        assert silver.source_id == "bank_of_korea_base_rate"
        assert silver.ingest_timestamp == _FIXED_NOW

    def test_invalid_date_skips_record(self) -> None:
        bronze = _make_bronze_rate(date="2024-02-30")
        assert normalize_interest_rate(bronze) is None

    def test_none_date_skips_record(self) -> None:
        bronze = _make_bronze_rate(date=None)
        assert normalize_interest_rate(bronze) is None

    def test_none_rate_type_skips_record(self) -> None:
        bronze = _make_bronze_rate(rate_type=None)
        assert normalize_interest_rate(bronze) is None

    def test_empty_rate_type_skips_record(self) -> None:
        bronze = _make_bronze_rate(rate_type="")
        assert normalize_interest_rate(bronze) is None

    def test_none_rate_value_skips_record(self) -> None:
        bronze = _make_bronze_rate(rate_value=None)
        assert normalize_interest_rate(bronze) is None

    def test_invalid_rate_value_skips_record(self) -> None:
        bronze = _make_bronze_rate(rate_value="abc")
        assert normalize_interest_rate(bronze) is None

    def test_rate_value_quantized_to_two_decimals(self) -> None:
        bronze = _make_bronze_rate(rate_value="3.456")
        silver = normalize_interest_rate(bronze)
        assert silver is not None
        assert silver.rate_value == Decimal("3.46")

    def test_unit_field_is_not_mapped(self) -> None:
        bronze = _make_bronze_rate(unit="basis points")
        silver = normalize_interest_rate(bronze)
        assert silver is not None
        assert not hasattr(silver, "unit")


class TestNormalizeMigration:
    def test_happy_path_maps_required_fields(self) -> None:
        bronze = _make_bronze_migration()
        silver = normalize_migration(bronze)

        assert isinstance(silver, SilverMigration)
        assert silver.period == "2023-01"
        assert silver.region_code == "11"
        assert silver.region_name == "서울특별시"
        assert silver.in_count == 150000
        assert silver.out_count == 140000
        assert silver.net_count == 10000
        assert silver.source_id == "kostat_population_migration"
        assert silver.ingest_timestamp == _FIXED_NOW

    def test_single_digit_month_becomes_zero_padded(self) -> None:
        bronze = _make_bronze_migration(month="1")
        silver = normalize_migration(bronze)
        assert silver is not None
        assert silver.period == "2023-01"

    def test_none_year_skips_record(self) -> None:
        bronze = _make_bronze_migration(year=None)
        assert normalize_migration(bronze) is None

    def test_invalid_month_skips_record(self) -> None:
        bronze = _make_bronze_migration(month="13")
        assert normalize_migration(bronze) is None

    def test_none_region_code_skips_record(self) -> None:
        bronze = _make_bronze_migration(region_code=None)
        assert normalize_migration(bronze) is None

    def test_empty_region_name_skips_record(self) -> None:
        bronze = _make_bronze_migration(region_name="")
        assert normalize_migration(bronze) is None

    def test_invalid_in_count_skips_record(self) -> None:
        bronze = _make_bronze_migration(in_count="1.2")
        assert normalize_migration(bronze) is None

    def test_invalid_out_count_skips_record(self) -> None:
        bronze = _make_bronze_migration(out_count="abc")
        assert normalize_migration(bronze) is None

    def test_invalid_net_count_skips_record(self) -> None:
        bronze = _make_bronze_migration(net_count="-")
        assert normalize_migration(bronze) is None


class TestNormalizeInterestRateBatch:
    def test_filters_out_invalid_records(self) -> None:
        valid = _make_bronze_rate()
        invalid = _make_bronze_rate(rate_value="bad")
        rows = normalize_interest_rate_batch([valid, invalid])
        assert len(rows) == 1
        assert rows[0].rate_type == "base_rate"

    def test_empty_input_returns_empty_list(self) -> None:
        assert normalize_interest_rate_batch([]) == []


class TestNormalizeMigrationBatch:
    def test_filters_out_invalid_records(self) -> None:
        valid = _make_bronze_migration()
        invalid = _make_bronze_migration(month="15")
        rows = normalize_migration_batch([valid, invalid])
        assert len(rows) == 1
        assert rows[0].region_code == "11"

    def test_empty_input_returns_empty_list(self) -> None:
        assert normalize_migration_batch([]) == []
