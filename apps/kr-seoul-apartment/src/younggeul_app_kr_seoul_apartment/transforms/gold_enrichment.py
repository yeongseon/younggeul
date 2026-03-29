from __future__ import annotations

from younggeul_core.state.gold import GoldDistrictMonthlyMetrics


def _prev_month(period: str) -> str:
    year_str, month_str = period.split("-")
    year = int(year_str)
    month = int(month_str)

    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _prev_year(period: str) -> str:
    year_str, month_str = period.split("-")
    year = int(year_str)
    return f"{year - 1:04d}-{month_str}"


def _pct_change(current: int | float, prior: int | float) -> float | None:
    if prior == 0:
        return None
    return (current - prior) / prior * 100.0


def enrich_district_monthly_trends(
    metrics: list[GoldDistrictMonthlyMetrics],
) -> list[GoldDistrictMonthlyMetrics]:
    """Compute MoM and YoY price/volume changes for Gold metrics.

    Requires metrics sorted by (gu_code, period). Returns new list with
    trend fields populated where prior period data exists.
    """
    sorted_metrics = sorted(metrics, key=lambda metric: (metric.gu_code, metric.period))
    lookup = {(metric.gu_code, metric.period): metric for metric in sorted_metrics}

    enriched: list[GoldDistrictMonthlyMetrics] = []
    for metric in sorted_metrics:
        mom_key = (metric.gu_code, _prev_month(metric.period))
        yoy_key = (metric.gu_code, _prev_year(metric.period))

        mom_metric = lookup.get(mom_key)
        yoy_metric = lookup.get(yoy_key)

        mom_price_change = _pct_change(metric.avg_price, mom_metric.avg_price) if mom_metric is not None else None
        yoy_price_change = _pct_change(metric.avg_price, yoy_metric.avg_price) if yoy_metric is not None else None
        mom_volume_change = _pct_change(metric.sale_count, mom_metric.sale_count) if mom_metric is not None else None
        yoy_volume_change = _pct_change(metric.sale_count, yoy_metric.sale_count) if yoy_metric is not None else None

        enriched.append(
            metric.model_copy(
                update={
                    "mom_price_change": mom_price_change,
                    "yoy_price_change": yoy_price_change,
                    "mom_volume_change": mom_volume_change,
                    "yoy_volume_change": yoy_volume_change,
                }
            )
        )

    return enriched
