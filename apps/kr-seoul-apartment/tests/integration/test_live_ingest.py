"""Live integration test for the kpubdata-backed ingest pipeline.

Hits real MOLIT and BOK endpoints. Skipped automatically unless all
``KPUBDATA_*_API_KEY`` environment variables are present, and excluded from
``make test`` via the ``live`` pytest marker. Run explicitly with::

    pytest -m live apps/kr-seoul-apartment/tests/integration/test_live_ingest.py
"""

from __future__ import annotations

import os

import pytest

from younggeul_app_kr_seoul_apartment.connectors.client_factory import (
    REQUIRED_PROVIDERS,
    build_client,
)
from younggeul_app_kr_seoul_apartment.pipeline import run_pipeline
from younggeul_app_kr_seoul_apartment.pipeline_live import (
    run_live_ingest,
    run_live_ingest_months,
)

GANGNAM_LAWD_CODE = "11680"
TARGET_DEAL_YM = "202503"
PRIOR_DEAL_YM = "202403"
PRIOR_MONTH_DEAL_YM = "202502"


def _env_keys_present() -> bool:
    for provider in REQUIRED_PROVIDERS:
        token = provider.upper()
        if not (os.environ.get(f"KPUBDATA_{token}_API_KEY") or os.environ.get(f"{token}_API_KEY")):
            return False
    return True


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not _env_keys_present(),
        reason="KPUBDATA_* API keys not set; skipping live integration test",
    ),
]


def test_live_ingest_gangnam_202503_produces_gold_output() -> None:
    client = build_client()

    bronze = run_live_ingest(
        client=client,
        lawd_code=GANGNAM_LAWD_CODE,
        deal_ym=TARGET_DEAL_YM,
    )

    assert len(bronze.apt_transactions) > 0
    assert len(bronze.interest_rates) == 1
    assert len(bronze.migrations) > 0
    seoul_codes = {m.region_code for m in bronze.migrations}
    assert GANGNAM_LAWD_CODE[:2] in seoul_codes

    result = run_pipeline(bronze)

    assert len(result.gold) >= 1
    gold = result.gold[0]
    assert gold.gu_code.startswith(GANGNAM_LAWD_CODE[:2])
    assert gold.period == f"{TARGET_DEAL_YM[:4]}-{TARGET_DEAL_YM[4:]}"
    assert gold.median_price > 0
    assert gold.net_migration is not None


def test_live_ingest_months_yoy_change_is_populated() -> None:
    client = build_client()

    bronze = run_live_ingest_months(
        client=client,
        lawd_code=GANGNAM_LAWD_CODE,
        deal_yms=[PRIOR_DEAL_YM, TARGET_DEAL_YM],
    )

    assert len(bronze.apt_transactions) > 0
    assert len(bronze.interest_rates) >= 2

    result = run_pipeline(bronze)

    by_period = {gold.period: gold for gold in result.gold}
    target_period = f"{TARGET_DEAL_YM[:4]}-{TARGET_DEAL_YM[4:]}"
    prior_period = f"{PRIOR_DEAL_YM[:4]}-{PRIOR_DEAL_YM[4:]}"
    assert target_period in by_period
    assert prior_period in by_period
    assert by_period[target_period].yoy_price_change is not None
    assert by_period[target_period].yoy_volume_change is not None


def test_live_ingest_consecutive_months_populates_mom_change() -> None:
    client = build_client()

    bronze = run_live_ingest_months(
        client=client,
        lawd_code=GANGNAM_LAWD_CODE,
        deal_yms=[PRIOR_MONTH_DEAL_YM, TARGET_DEAL_YM],
    )

    result = run_pipeline(bronze)

    by_period = {gold.period: gold for gold in result.gold}
    target_period = f"{TARGET_DEAL_YM[:4]}-{TARGET_DEAL_YM[4:]}"
    assert target_period in by_period
    assert by_period[target_period].mom_price_change is not None
    assert by_period[target_period].mom_volume_change is not None
