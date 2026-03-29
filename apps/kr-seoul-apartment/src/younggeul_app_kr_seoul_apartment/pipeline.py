from __future__ import annotations

from dataclasses import dataclass

from younggeul_core.state.bronze import BronzeAptTransaction, BronzeInterestRate, BronzeMigration
from younggeul_core.state.gold import GoldDistrictMonthlyMetrics
from younggeul_core.state.silver import SilverAptTransaction, SilverInterestRate, SilverMigration

from younggeul_app_kr_seoul_apartment.transforms.gold_district import aggregate_district_monthly
from younggeul_app_kr_seoul_apartment.transforms.gold_enrichment import enrich_district_monthly_trends
from younggeul_app_kr_seoul_apartment.transforms.silver_apt import normalize_batch as normalize_apt_batch
from younggeul_app_kr_seoul_apartment.transforms.silver_macro import (
    normalize_interest_rate_batch,
    normalize_migration_batch,
)


@dataclass(frozen=True)
class BronzeInput:
    """Raw Bronze records from all connectors."""

    apt_transactions: list[BronzeAptTransaction]
    interest_rates: list[BronzeInterestRate]
    migrations: list[BronzeMigration]


@dataclass(frozen=True)
class SilverOutput:
    """Normalized Silver records."""

    apt_transactions: list[SilverAptTransaction]
    interest_rates: list[SilverInterestRate]
    migrations: list[SilverMigration]


@dataclass(frozen=True)
class PipelineResult:
    """Full pipeline output: Silver + Gold layers."""

    silver: SilverOutput
    gold: list[GoldDistrictMonthlyMetrics]


def run_pipeline(bronze: BronzeInput) -> PipelineResult:
    """Execute the full Bronze → Silver → Gold data pipeline.

    All transforms are deterministic (ADR-004). No LLMs, no side effects.
    """
    # Silver layer
    silver_apt = normalize_apt_batch(bronze.apt_transactions)
    silver_rates = normalize_interest_rate_batch(bronze.interest_rates)
    silver_migrations = normalize_migration_batch(bronze.migrations)

    silver = SilverOutput(
        apt_transactions=silver_apt,
        interest_rates=silver_rates,
        migrations=silver_migrations,
    )

    # Gold layer
    gold = aggregate_district_monthly(
        transactions=silver_apt,
        interest_rates=silver_rates,
        migrations=silver_migrations,
    )
    gold = enrich_district_monthly_trends(gold)

    return PipelineResult(silver=silver, gold=gold)
