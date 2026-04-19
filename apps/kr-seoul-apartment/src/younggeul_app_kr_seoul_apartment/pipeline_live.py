"""Live ingest pipeline: fetches one Seoul gu × one month from real APIs via kpubdata.

v0.1 scope (option C — see docs/adr/007):
- MOLIT apartment trades and BOK base rate are fetched live.
- KOSTAT population migration is **not emitted** in live mode. The kpubdata
  ``kosis.population_migration`` dataset only exposes ``T70``/``T80`` aggregate
  metrics while ``BronzeMigration`` requires per-region in/out/net counts;
  wiring those requires either a different KOSIS table or a Bronze schema
  change, which is tracked separately.
"""

from __future__ import annotations

from kpubdata import Client

from younggeul_core.connectors.rate_limit import RateLimiter

from younggeul_app_kr_seoul_apartment.connectors.bok import (
    BokInterestRateConnector,
    BokInterestRateRequest,
)
from younggeul_app_kr_seoul_apartment.connectors.molit import (
    MolitAptConnector,
    MolitAptRequest,
)
from younggeul_app_kr_seoul_apartment.pipeline import BronzeInput

_BOK_BASE_RATE_STAT_CODE = "722Y001"
_BOK_BASE_RATE_ITEM_CODE = "0101000"
_BOK_BASE_RATE_FREQUENCY = "M"
_BOK_BASE_RATE_SOURCE_ID = "bank_of_korea_base_rate"
_BOK_BASE_RATE_TYPE = "base_rate"

_DEFAULT_RATE_LIMIT_INTERVAL = 1.0


def _validate_lawd_code(lawd_code: str) -> None:
    if len(lawd_code) != 5 or not lawd_code.isdigit():
        msg = f"lawd_code must be 5 digits, got {lawd_code!r}"
        raise ValueError(msg)


def _validate_deal_ym(deal_ym: str) -> None:
    if len(deal_ym) != 6 or not deal_ym.isdigit():
        msg = f"deal_ym must be YYYYMM (6 digits), got {deal_ym!r}"
        raise ValueError(msg)


def run_live_ingest(
    *,
    client: Client,
    lawd_code: str,
    deal_ym: str,
    rate_limit_interval: float = _DEFAULT_RATE_LIMIT_INTERVAL,
) -> BronzeInput:
    """Fetch MOLIT and BOK data for one gu × one month and return a BronzeInput.

    KOSTAT migrations are omitted in live mode (see module docstring); the
    returned ``BronzeInput.migrations`` list is always empty.

    Args:
        client: Authenticated kpubdata client (built via ``client_factory.build_client``).
        lawd_code: 5-digit MOLIT sigungu code (e.g. ``"11680"`` for Gangnam-gu).
        deal_ym: Target month in ``YYYYMM`` format (e.g. ``"202503"``).
        rate_limit_interval: Minimum seconds between consecutive API calls per
            connector. Defaults to 1.0 to stay well within data.go.kr quotas.

    Returns:
        ``BronzeInput`` populated with apt transactions and interest rates,
        ready for ``run_pipeline``.

    Raises:
        ValueError: If ``lawd_code`` or ``deal_ym`` are malformed.
    """
    _validate_lawd_code(lawd_code)
    _validate_deal_ym(deal_ym)

    limiter = RateLimiter(min_interval=rate_limit_interval)

    apt_dataset = client.dataset("datago.apt_trade")
    rate_dataset = client.dataset("bok.base_rate")

    apt_connector = MolitAptConnector(client=apt_dataset, rate_limiter=limiter)
    bok_connector = BokInterestRateConnector(client=rate_dataset, rate_limiter=limiter)

    apt_result = apt_connector.fetch(MolitAptRequest(sigungu_code=lawd_code, year_month=deal_ym))
    rate_result = bok_connector.fetch(
        BokInterestRateRequest(
            stat_code=_BOK_BASE_RATE_STAT_CODE,
            item_code1=_BOK_BASE_RATE_ITEM_CODE,
            frequency=_BOK_BASE_RATE_FREQUENCY,
            start_date=deal_ym,
            end_date=deal_ym,
            rate_type=_BOK_BASE_RATE_TYPE,
            source_id=_BOK_BASE_RATE_SOURCE_ID,
        )
    )

    return BronzeInput(
        apt_transactions=apt_result.records,
        interest_rates=rate_result.records,
        migrations=[],
    )


__all__ = ["run_live_ingest"]
