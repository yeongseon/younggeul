from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median

from younggeul_core.state.gold import GoldDistrictMonthlyMetrics
from younggeul_core.state.silver import SilverAptTransaction, SilverInterestRate, SilverMigration

PYEONG_CONVERSION = Decimal("3.3058")


def _group_transactions(
    transactions: list[SilverAptTransaction],
) -> dict[tuple[str, str], list[SilverAptTransaction]]:
    grouped: defaultdict[tuple[str, str], list[SilverAptTransaction]] = defaultdict(list)
    for transaction in transactions:
        if transaction.is_cancelled:
            continue
        period = transaction.deal_date.strftime("%Y-%m")
        grouped[(transaction.gu_code, period)].append(transaction)
    return dict(grouped)


def _find_interest_rate(rates: list[SilverInterestRate] | None, period: str) -> Decimal | None:
    if not rates:
        return None

    candidates = [rate for rate in rates if rate.rate_date.strftime("%Y-%m") == period]
    if not candidates:
        return None

    latest = max(candidates, key=lambda rate: rate.rate_date)
    return latest.rate_value


def _find_net_migration(
    migrations: list[SilverMigration] | None,
    gu_code: str,
    period: str,
) -> int | None:
    if not migrations:
        return None

    city_code = gu_code[:2]
    for migration in migrations:
        if migration.period != period:
            continue
        if migration.region_code == city_code:
            return migration.net_count
    return None


def aggregate_district_monthly(
    transactions: list[SilverAptTransaction],
    interest_rates: list[SilverInterestRate] | None = None,
    migrations: list[SilverMigration] | None = None,
) -> list[GoldDistrictMonthlyMetrics]:
    grouped = _group_transactions(transactions)
    if not grouped:
        return []

    metrics: list[GoldDistrictMonthlyMetrics] = []
    for (gu_code, period), group in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        deal_amounts = [transaction.deal_amount for transaction in group]
        total_area_m2 = sum((transaction.area_exclusive_m2 for transaction in group), Decimal("0"))
        total_area_pyeong = total_area_m2 / PYEONG_CONVERSION
        if total_area_pyeong == 0:
            price_per_pyeong_avg = 0
        else:
            price_per_pyeong_avg = int(sum(deal_amounts) / total_area_pyeong)

        avg_area_m2 = total_area_m2 / Decimal(len(group)) if group else None

        metrics.append(
            GoldDistrictMonthlyMetrics(
                gu_code=gu_code,
                gu_name=group[0].gu_name,
                period=period,
                sale_count=len(group),
                avg_price=sum(deal_amounts) // len(deal_amounts),
                median_price=int(median(deal_amounts)),
                min_price=min(deal_amounts),
                max_price=max(deal_amounts),
                price_per_pyeong_avg=price_per_pyeong_avg,
                yoy_price_change=None,
                mom_price_change=None,
                yoy_volume_change=None,
                mom_volume_change=None,
                avg_area_m2=avg_area_m2,
                base_interest_rate=_find_interest_rate(interest_rates, period),
                net_migration=_find_net_migration(migrations, gu_code, period),
                dataset_snapshot_id=None,
            )
        )

    return metrics
