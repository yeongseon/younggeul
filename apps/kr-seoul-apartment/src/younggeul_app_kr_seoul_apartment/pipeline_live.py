"""Live ingest pipeline: fetches Seoul gu × month(s) from real APIs via kpubdata.

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

    Thin wrapper over :func:`run_live_ingest_months` for the single-month case.
    See that function for full semantics.
    """
    return run_live_ingest_months(
        client=client,
        lawd_code=lawd_code,
        deal_yms=[deal_ym],
        rate_limit_interval=rate_limit_interval,
    )


def run_live_ingest_months(
    *,
    client: Client,
    lawd_code: str,
    deal_yms: list[str],
    rate_limit_interval: float = _DEFAULT_RATE_LIMIT_INTERVAL,
) -> BronzeInput:
    """Fetch MOLIT and BOK data for one gu × N months and return a BronzeInput.

    Thin wrapper over :func:`run_live_ingest_gus_months` for the single-gu case.
    See that function for full semantics.
    """
    return run_live_ingest_gus_months(
        client=client,
        lawd_codes=[lawd_code],
        deal_yms=deal_yms,
        rate_limit_interval=rate_limit_interval,
    )


def run_live_ingest_gus_months(
    *,
    client: Client,
    lawd_codes: list[str],
    deal_yms: list[str],
    rate_limit_interval: float = _DEFAULT_RATE_LIMIT_INTERVAL,
) -> BronzeInput:
    """Fetch MOLIT and BOK data for M gus × N months and return a BronzeInput.

    MOLIT is queried once per (gu, month) pair (the API does not accept ranges
    or multiple sigungu codes); BOK is queried once with
    ``start_date=min(deal_yms)`` and ``end_date=max(deal_yms)`` since the base
    rate is national. KOSTAT migrations are omitted in live mode (see module
    docstring).

    Args:
        client: Authenticated kpubdata client (via ``client_factory.build_client``).
        lawd_codes: One or more 5-digit MOLIT sigungu codes. Order is preserved
            in the output. Duplicates are rejected.
        deal_yms: One or more target months in ``YYYYMM`` format. Order is
            preserved. Duplicates are rejected.
        rate_limit_interval: Minimum seconds between consecutive API calls per
            connector. Defaults to 1.0 to stay well within data.go.kr quotas.

    Returns:
        ``BronzeInput`` with apt transactions across all (gu × month) pairs and
        interest rates spanning the full window. The aggregator groups by
        ``(gu_code, period)`` so each (gu, month) becomes its own Gold row,
        with YoY/MoM ratios populated where comparison anchors exist within
        the same gu.

    Raises:
        ValueError: If any code is malformed, lists are empty, or duplicates
            are present.
    """
    if not lawd_codes:
        raise ValueError("lawd_codes must not be empty")
    if len(set(lawd_codes)) != len(lawd_codes):
        raise ValueError(f"lawd_codes must not contain duplicates, got {lawd_codes!r}")
    for code in lawd_codes:
        _validate_lawd_code(code)
    if not deal_yms:
        raise ValueError("deal_yms must not be empty")
    if len(set(deal_yms)) != len(deal_yms):
        raise ValueError(f"deal_yms must not contain duplicates, got {deal_yms!r}")
    for ym in deal_yms:
        _validate_deal_ym(ym)

    limiter = RateLimiter(min_interval=rate_limit_interval)

    apt_dataset = client.dataset("datago.apt_trade")
    rate_dataset = client.dataset("bok.base_rate")

    apt_connector = MolitAptConnector(client=apt_dataset, rate_limiter=limiter)
    bok_connector = BokInterestRateConnector(client=rate_dataset, rate_limiter=limiter)

    apt_records = []
    for code in lawd_codes:
        for ym in deal_yms:
            apt_result = apt_connector.fetch(MolitAptRequest(sigungu_code=code, year_month=ym))
            apt_records.extend(apt_result.records)

    rate_result = bok_connector.fetch(
        BokInterestRateRequest(
            stat_code=_BOK_BASE_RATE_STAT_CODE,
            item_code1=_BOK_BASE_RATE_ITEM_CODE,
            frequency=_BOK_BASE_RATE_FREQUENCY,
            start_date=min(deal_yms),
            end_date=max(deal_yms),
            rate_type=_BOK_BASE_RATE_TYPE,
            source_id=_BOK_BASE_RATE_SOURCE_ID,
        )
    )

    return BronzeInput(
        apt_transactions=apt_records,
        interest_rates=rate_result.records,
        migrations=[],
    )


__all__ = ["run_live_ingest", "run_live_ingest_gus_months", "run_live_ingest_months"]
