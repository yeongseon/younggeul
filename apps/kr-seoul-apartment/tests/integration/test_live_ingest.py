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
from younggeul_app_kr_seoul_apartment.pipeline_live import run_live_ingest

GANGNAM_LAWD_CODE = "11680"
TARGET_DEAL_YM = "202503"


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
    assert bronze.migrations == []

    result = run_pipeline(bronze)

    assert len(result.gold) >= 1
    gold = result.gold[0]
    assert gold.gu_code.startswith(GANGNAM_LAWD_CODE[:2])
    assert gold.period == f"{TARGET_DEAL_YM[:4]}-{TARGET_DEAL_YM[4:]}"
    assert gold.median_price > 0
