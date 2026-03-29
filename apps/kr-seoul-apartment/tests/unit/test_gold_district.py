from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from younggeul_app_kr_seoul_apartment.transforms.gold_district import (
    PYEONG_CONVERSION,
    _find_interest_rate,
    _find_net_migration,
    _group_transactions,
    aggregate_district_monthly,
)
from younggeul_core.state.silver import SilverAptTransaction, SilverInterestRate, SilverMigration

_FIXED_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _make_silver_apt(**overrides: Any) -> SilverAptTransaction:
    payload: dict[str, Any] = {
        "transaction_id": "tx-1",
        "deal_amount": 820_000_000,
        "deal_date": date(2025, 7, 15),
        "build_year": 2016,
        "dong_code": "1168010300",
        "dong_name": "역삼동",
        "gu_code": "11680",
        "gu_name": "강남구",
        "apt_name": "래미안",
        "floor": 12,
        "area_exclusive_m2": Decimal("84.99"),
        "source_id": "molit",
        "ingest_timestamp": _FIXED_NOW,
    }
    payload.update(overrides)
    return SilverAptTransaction(**payload)


def _make_silver_rate(**overrides: Any) -> SilverInterestRate:
    payload: dict[str, Any] = {
        "rate_date": date(2025, 7, 1),
        "rate_type": "base_rate",
        "rate_value": Decimal("3.50"),
        "source_id": "bok",
        "ingest_timestamp": _FIXED_NOW,
    }
    payload.update(overrides)
    return SilverInterestRate(**payload)


def _make_silver_migration(**overrides: Any) -> SilverMigration:
    payload: dict[str, Any] = {
        "period": "2025-07",
        "region_code": "11",
        "region_name": "서울특별시",
        "in_count": 150000,
        "out_count": 140000,
        "net_count": 10000,
        "source_id": "kostat",
        "ingest_timestamp": _FIXED_NOW,
    }
    payload.update(overrides)
    return SilverMigration(**payload)


class TestGroupTransactions:
    def test_empty_input_returns_empty_dict(self) -> None:
        assert _group_transactions([]) == {}

    def test_single_transaction_grouped_by_gu_and_period(self) -> None:
        tx = _make_silver_apt()
        grouped = _group_transactions([tx])
        assert set(grouped.keys()) == {("11680", "2025-07")}
        assert grouped[("11680", "2025-07")] == [tx]

    def test_cancelled_transaction_is_excluded(self) -> None:
        tx = _make_silver_apt(is_cancelled=True)
        assert _group_transactions([tx]) == {}

    def test_all_cancelled_transactions_returns_empty_dict(self) -> None:
        tx1 = _make_silver_apt(transaction_id="tx-1", is_cancelled=True)
        tx2 = _make_silver_apt(transaction_id="tx-2", is_cancelled=True)
        assert _group_transactions([tx1, tx2]) == {}

    def test_mixed_cancelled_and_non_cancelled_keeps_only_non_cancelled(self) -> None:
        kept = _make_silver_apt(transaction_id="tx-1", is_cancelled=False)
        dropped = _make_silver_apt(transaction_id="tx-2", is_cancelled=True)
        grouped = _group_transactions([kept, dropped])
        assert grouped == {("11680", "2025-07"): [kept]}

    def test_same_gu_and_month_are_grouped_together(self) -> None:
        tx1 = _make_silver_apt(transaction_id="tx-1", deal_date=date(2025, 7, 1))
        tx2 = _make_silver_apt(transaction_id="tx-2", deal_date=date(2025, 7, 31))
        grouped = _group_transactions([tx1, tx2])
        assert len(grouped) == 1
        assert grouped[("11680", "2025-07")] == [tx1, tx2]

    def test_different_gu_codes_create_different_groups(self) -> None:
        tx1 = _make_silver_apt(transaction_id="tx-1", gu_code="11680", gu_name="강남구")
        tx2 = _make_silver_apt(transaction_id="tx-2", gu_code="11710", gu_name="송파구")
        grouped = _group_transactions([tx1, tx2])
        assert set(grouped.keys()) == {("11680", "2025-07"), ("11710", "2025-07")}

    def test_different_months_create_different_groups(self) -> None:
        tx1 = _make_silver_apt(transaction_id="tx-1", deal_date=date(2025, 7, 10))
        tx2 = _make_silver_apt(transaction_id="tx-2", deal_date=date(2025, 8, 10))
        grouped = _group_transactions([tx1, tx2])
        assert set(grouped.keys()) == {("11680", "2025-07"), ("11680", "2025-08")}

    def test_period_uses_yyyy_mm_format(self) -> None:
        tx = _make_silver_apt(deal_date=date(2025, 1, 5))
        grouped = _group_transactions([tx])
        assert ("11680", "2025-01") in grouped


class TestFindInterestRate:
    def test_none_rates_returns_none(self) -> None:
        assert _find_interest_rate(None, "2025-07") is None

    def test_empty_rates_returns_none(self) -> None:
        assert _find_interest_rate([], "2025-07") is None

    def test_no_matching_period_returns_none(self) -> None:
        rates = [_make_silver_rate(rate_date=date(2025, 8, 1))]
        assert _find_interest_rate(rates, "2025-07") is None

    def test_single_matching_period_returns_rate_value(self) -> None:
        rates = [_make_silver_rate(rate_date=date(2025, 7, 1), rate_value=Decimal("3.25"))]
        assert _find_interest_rate(rates, "2025-07") == Decimal("3.25")

    def test_multiple_matching_periods_latest_date_wins(self) -> None:
        rates = [
            _make_silver_rate(rate_date=date(2025, 7, 1), rate_value=Decimal("3.25")),
            _make_silver_rate(rate_date=date(2025, 7, 15), rate_value=Decimal("3.00")),
            _make_silver_rate(rate_date=date(2025, 7, 31), rate_value=Decimal("2.75")),
        ]
        assert _find_interest_rate(rates, "2025-07") == Decimal("2.75")

    def test_ignores_other_month_even_if_later_date(self) -> None:
        rates = [
            _make_silver_rate(rate_date=date(2025, 7, 1), rate_value=Decimal("3.25")),
            _make_silver_rate(rate_date=date(2025, 8, 15), rate_value=Decimal("1.00")),
        ]
        assert _find_interest_rate(rates, "2025-07") == Decimal("3.25")

    def test_returns_decimal_type(self) -> None:
        rates = [_make_silver_rate(rate_value=Decimal("3.50"))]
        value = _find_interest_rate(rates, "2025-07")
        assert isinstance(value, Decimal)


class TestFindNetMigration:
    def test_none_migrations_returns_none(self) -> None:
        assert _find_net_migration(None, "11680", "2025-07") is None

    def test_empty_migrations_returns_none(self) -> None:
        assert _find_net_migration([], "11680", "2025-07") is None

    def test_matching_period_and_city_prefix_returns_net_count(self) -> None:
        migrations = [_make_silver_migration(period="2025-07", region_code="11", net_count=11111)]
        assert _find_net_migration(migrations, "11680", "2025-07") == 11111

    def test_non_matching_period_returns_none(self) -> None:
        migrations = [_make_silver_migration(period="2025-08", region_code="11", net_count=11111)]
        assert _find_net_migration(migrations, "11680", "2025-07") is None

    def test_non_matching_region_code_returns_none(self) -> None:
        migrations = [_make_silver_migration(period="2025-07", region_code="26", net_count=11111)]
        assert _find_net_migration(migrations, "11680", "2025-07") is None

    def test_other_city_prefix_matches_when_gu_prefix_matches(self) -> None:
        migrations = [_make_silver_migration(period="2025-07", region_code="26", net_count=22222)]
        assert _find_net_migration(migrations, "26110", "2025-07") == 22222

    def test_returns_first_matching_migration_entry(self) -> None:
        migrations = [
            _make_silver_migration(period="2025-07", region_code="11", net_count=10000),
            _make_silver_migration(period="2025-07", region_code="11", net_count=99999),
        ]
        assert _find_net_migration(migrations, "11680", "2025-07") == 10000


class TestAggregateDistrictMonthly:
    def test_empty_transactions_returns_empty_list(self) -> None:
        assert aggregate_district_monthly([]) == []

    def test_all_cancelled_transactions_returns_empty_list(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", is_cancelled=True),
            _make_silver_apt(transaction_id="tx-2", is_cancelled=True),
        ]
        assert aggregate_district_monthly(txs) == []

    def test_single_transaction_returns_one_gold_record(self) -> None:
        tx = _make_silver_apt()
        result = aggregate_district_monthly([tx])
        assert len(result) == 1
        item = result[0]
        assert item.gu_code == "11680"
        assert item.gu_name == "강남구"
        assert item.period == "2025-07"
        assert item.sale_count == 1
        assert item.avg_price == 820_000_000
        assert item.median_price == 820_000_000
        assert item.min_price == 820_000_000
        assert item.max_price == 820_000_000

    def test_same_amounts_result_in_equal_avg_median_min_max(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_amount=900_000_000),
            _make_silver_apt(transaction_id="tx-2", deal_amount=900_000_000),
            _make_silver_apt(transaction_id="tx-3", deal_amount=900_000_000),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.avg_price == 900_000_000
        assert item.median_price == 900_000_000
        assert item.min_price == 900_000_000
        assert item.max_price == 900_000_000

    def test_multiple_transactions_same_group_aggregate_values(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_amount=900_000_000, area_exclusive_m2=Decimal("84.99")),
            _make_silver_apt(transaction_id="tx-2", deal_amount=600_000_000, area_exclusive_m2=Decimal("59.99")),
            _make_silver_apt(transaction_id="tx-3", deal_amount=1_200_000_000, area_exclusive_m2=Decimal("114.50")),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.sale_count == 3
        assert item.avg_price == (900_000_000 + 600_000_000 + 1_200_000_000) // 3
        assert item.median_price == 900_000_000
        assert item.min_price == 600_000_000
        assert item.max_price == 1_200_000_000

    def test_even_count_median_cast_to_int(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_amount=100),
            _make_silver_apt(transaction_id="tx-2", deal_amount=101),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.median_price == int((100 + 101) / 2)

    def test_cancelled_transactions_are_filtered_from_aggregation(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_amount=800_000_000),
            _make_silver_apt(transaction_id="tx-2", deal_amount=1_000_000_000, is_cancelled=True),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.sale_count == 1
        assert item.avg_price == 800_000_000

    def test_multiple_gu_codes_produce_separate_records(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", gu_code="11710", gu_name="송파구"),
            _make_silver_apt(transaction_id="tx-2", gu_code="11680", gu_name="강남구"),
        ]
        result = aggregate_district_monthly(txs)
        assert len(result) == 2
        assert [item.gu_code for item in result] == ["11680", "11710"]

    def test_multiple_months_produce_separate_records(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_date=date(2025, 8, 1)),
            _make_silver_apt(transaction_id="tx-2", deal_date=date(2025, 7, 1)),
        ]
        result = aggregate_district_monthly(txs)
        assert len(result) == 2
        assert [item.period for item in result] == ["2025-07", "2025-08"]

    def test_sort_order_is_gu_code_then_period(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", gu_code="11710", gu_name="송파구", deal_date=date(2025, 8, 2)),
            _make_silver_apt(transaction_id="tx-2", gu_code="11680", gu_name="강남구", deal_date=date(2025, 8, 1)),
            _make_silver_apt(transaction_id="tx-3", gu_code="11680", gu_name="강남구", deal_date=date(2025, 7, 1)),
        ]
        result = aggregate_district_monthly(txs)
        assert [(item.gu_code, item.period) for item in result] == [
            ("11680", "2025-07"),
            ("11680", "2025-08"),
            ("11710", "2025-08"),
        ]

    def test_price_per_pyeong_avg_is_computed_from_group_totals(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", deal_amount=500_000_000, area_exclusive_m2=Decimal("50.00")),
            _make_silver_apt(transaction_id="tx-2", deal_amount=700_000_000, area_exclusive_m2=Decimal("70.00")),
        ]
        item = aggregate_district_monthly(txs)[0]
        expected = int((500_000_000 + 700_000_000) / (Decimal("120.00") / PYEONG_CONVERSION))
        assert item.price_per_pyeong_avg == expected

    def test_zero_total_area_sets_price_per_pyeong_to_zero(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", area_exclusive_m2=Decimal("0.00")),
            _make_silver_apt(transaction_id="tx-2", area_exclusive_m2=Decimal("0.00")),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.price_per_pyeong_avg == 0

    def test_avg_area_m2_is_decimal_average(self) -> None:
        txs = [
            _make_silver_apt(transaction_id="tx-1", area_exclusive_m2=Decimal("80.00")),
            _make_silver_apt(transaction_id="tx-2", area_exclusive_m2=Decimal("100.00")),
        ]
        item = aggregate_district_monthly(txs)[0]
        assert item.avg_area_m2 == Decimal("90.00")

    def test_avg_area_m2_with_single_transaction(self) -> None:
        tx = _make_silver_apt(area_exclusive_m2=Decimal("84.99"))
        item = aggregate_district_monthly([tx])[0]
        assert item.avg_area_m2 == Decimal("84.99")

    def test_interest_rate_found_for_period(self) -> None:
        tx = _make_silver_apt(deal_date=date(2025, 7, 15))
        rates = [_make_silver_rate(rate_date=date(2025, 7, 1), rate_value=Decimal("3.25"))]
        item = aggregate_district_monthly([tx], interest_rates=rates)[0]
        assert item.base_interest_rate == Decimal("3.25")

    def test_interest_rate_not_found_sets_none(self) -> None:
        tx = _make_silver_apt(deal_date=date(2025, 7, 15))
        rates = [_make_silver_rate(rate_date=date(2025, 8, 1), rate_value=Decimal("3.25"))]
        item = aggregate_district_monthly([tx], interest_rates=rates)[0]
        assert item.base_interest_rate is None

    def test_interest_rate_uses_latest_when_multiple_same_period(self) -> None:
        tx = _make_silver_apt(deal_date=date(2025, 7, 15))
        rates = [
            _make_silver_rate(rate_date=date(2025, 7, 1), rate_value=Decimal("3.25")),
            _make_silver_rate(rate_date=date(2025, 7, 31), rate_value=Decimal("2.75")),
        ]
        item = aggregate_district_monthly([tx], interest_rates=rates)[0]
        assert item.base_interest_rate == Decimal("2.75")

    def test_migration_found_for_seoul_city_level_region_code(self) -> None:
        tx = _make_silver_apt(gu_code="11680", deal_date=date(2025, 7, 15))
        migrations = [_make_silver_migration(period="2025-07", region_code="11", net_count=12345)]
        item = aggregate_district_monthly([tx], migrations=migrations)[0]
        assert item.net_migration == 12345

    def test_migration_not_found_sets_none(self) -> None:
        tx = _make_silver_apt(gu_code="11680", deal_date=date(2025, 7, 15))
        migrations = [_make_silver_migration(period="2025-08", region_code="11", net_count=12345)]
        item = aggregate_district_monthly([tx], migrations=migrations)[0]
        assert item.net_migration is None

    def test_migration_gu_level_region_code_does_not_match_city_prefix_rule(self) -> None:
        tx = _make_silver_apt(gu_code="11680", deal_date=date(2025, 7, 15))
        migrations = [_make_silver_migration(period="2025-07", region_code="11680", net_count=12345)]
        item = aggregate_district_monthly([tx], migrations=migrations)[0]
        assert item.net_migration is None

    def test_optional_change_fields_and_snapshot_id_are_none(self) -> None:
        tx = _make_silver_apt()
        item = aggregate_district_monthly([tx])[0]
        assert item.yoy_price_change is None
        assert item.mom_price_change is None
        assert item.yoy_volume_change is None
        assert item.mom_volume_change is None
        assert item.dataset_snapshot_id is None
