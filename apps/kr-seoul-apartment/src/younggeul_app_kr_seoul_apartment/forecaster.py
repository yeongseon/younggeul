from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from younggeul_core.state.gold import BaselineForecast, GoldDistrictMonthlyMetrics
from younggeul_core.state.simulation import SnapshotRef


def _next_period(period: str) -> str:
    year_str, month_str = period.split("-")
    year = int(year_str)
    month = int(month_str)

    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def forecast_baseline(metrics: list[GoldDistrictMonthlyMetrics]) -> list[BaselineForecast]:
    if not metrics:
        return []

    grouped: dict[str, list[GoldDistrictMonthlyMetrics]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.gu_code].append(metric)

    forecasts: list[BaselineForecast] = []
    for gu_code in sorted(grouped):
        rows = sorted(grouped[gu_code], key=lambda metric: metric.period)
        latest = rows[-1]

        mom_price = latest.mom_price_change if latest.mom_price_change is not None else 0.0
        mom_volume = latest.mom_volume_change if latest.mom_volume_change is not None else 0.0

        ma3_values = [row.avg_price for row in rows[-3:]]
        ma3 = sum(ma3_values) / len(ma3_values)
        ma3_signal = ((latest.avg_price - ma3) / ma3) * 100.0 if ma3 > 0 else 0.0

        score = 0.6 * mom_price + 0.3 * ma3_signal + 0.1 * mom_volume
        direction: Literal["up", "down", "flat"]
        if score > 1.0:
            direction = "up"
        elif score < -1.0:
            direction = "down"
        else:
            direction = "flat"

        row_count = len(rows)
        if row_count >= 12:
            confidence = 0.8
        elif row_count >= 6:
            confidence = 0.6
        elif row_count >= 3:
            confidence = 0.4
        else:
            confidence = 0.2

        if latest.mom_price_change is not None:
            predicted_median_price = int(latest.median_price * (1 + latest.mom_price_change / 100))
        else:
            predicted_median_price = latest.median_price

        if latest.mom_volume_change is not None:
            predicted_volume = int(latest.sale_count * (1 + latest.mom_volume_change / 100))
        else:
            predicted_volume = latest.sale_count
        predicted_volume = max(0, predicted_volume)

        feature_candidates = [
            "mom_price_change",
            "yoy_price_change",
            "mom_volume_change",
            "yoy_volume_change",
            "base_interest_rate",
            "net_migration",
        ]
        features_used = [name for name in feature_candidates if getattr(latest, name) is not None]

        forecasts.append(
            BaselineForecast(
                gu_code=latest.gu_code,
                gu_name=latest.gu_name,
                target_period=_next_period(latest.period),
                direction=direction,
                direction_confidence=confidence,
                predicted_volume=predicted_volume,
                predicted_median_price=predicted_median_price,
                model_name="momentum_v1",
                features_used=features_used,
            )
        )

    return forecasts


def generate_baseline_report(
    snapshot_ref: SnapshotRef,
    forecasts: list[BaselineForecast],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"baseline_report_{snapshot_ref.dataset_snapshot_id[:12]}.json"

    direction_counts = {
        "up": sum(1 for forecast in forecasts if forecast.direction == "up"),
        "down": sum(1 for forecast in forecasts if forecast.direction == "down"),
        "flat": sum(1 for forecast in forecasts if forecast.direction == "flat"),
    }
    avg_confidence = (
        round(
            sum(forecast.direction_confidence for forecast in forecasts) / len(forecasts),
            2,
        )
        if forecasts
        else 0.0
    )

    payload = {
        "report_type": "baseline_forecast",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": {
            "dataset_snapshot_id": snapshot_ref.dataset_snapshot_id,
            "created_at": snapshot_ref.created_at.isoformat(),
            "table_count": snapshot_ref.table_count,
        },
        "summary": {
            "total_districts": len(forecasts),
            "direction_counts": direction_counts,
            "avg_confidence": avg_confidence,
        },
        "forecasts": [forecast.model_dump() for forecast in forecasts],
    }

    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return report_path
