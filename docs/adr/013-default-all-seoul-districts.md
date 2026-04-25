# ADR-013: Default Seoul ingest entrypoints to all 25 districts

## Status
Accepted

## Date
2026-04-25

## Context

Several Seoul ingest entrypoints still defaulted to Gangnam-only (`11680`) even though the apartment pipeline, simulation coverage, and live ingest CLI already support all 25 Seoul gu.

- `transforms/silver_apt.py` and `simulation/domain/gu_resolver.py` each carried their own inline Seoul district maps.
- `.github/workflows/data-pipeline.yml` and `scripts/demo_live.sh` defaulted to Gangnam, which under-exercised multi-gu behavior.
- `younggeul ingest --source fixture` ignored `--gus` and `--months`, so scheduled fixture runs could not mirror broader coverage defaults.

That drift made the default operator path narrower than the actual product scope and duplicated region definitions across the codebase.

## Decision

Younggeul now standardizes Seoul district coverage around one canonical region module and defaults ingest entrypoints to all 25 Seoul gu.

### 1. Canonical Seoul district definitions live in app code

`younggeul_app_kr_seoul_apartment.canonical.regions` is now the single source of truth for:

- `SEOUL_GU_CODES`
- `SEOUL_GU_CODE_TO_NAME`
- `SEOUL_GU_NAME_TO_CODE`

`silver_apt.py` and `gu_resolver.py` import these constants instead of maintaining inline duplicates.

### 2. Fixture ingest mirrors multi-gu operator defaults

`younggeul ingest --source fixture` now honors:

- `--gu` or `--gus`
- `--month` or `--months`

When explicit fixture gu/month inputs are supplied, the CLI synthesizes deterministic Bronze apartment rows for each requested gu × month combination while keeping the zero-argument fixture invocation unchanged.

### 3. Workflow and demo defaults expand to all 25 Seoul gu

The GitHub Actions data pipeline and `scripts/demo_live.sh` now default to the full 25-gu CSV.

- Explicit `gus`/`GUS` still wins.
- Explicit single-gu `gu`/`GU` still works unchanged.
- Scheduled GitHub Actions runs remain on `source=fixture` because MOLIT blocks GitHub-hosted runner IPs.

## Consequences

**Pros.**

- Operator defaults now reflect actual Seoul-wide product scope.
- One canonical region map reduces drift risk.
- Scheduled fixture runs exercise broader Seoul coverage without requiring live MOLIT access.

**Cons.**

- Default live demo invocations fan out across more gu and can consume more upstream quota unless narrowed explicitly.
- Documentation and workflow examples must stay aligned with the broader default.

## Related

- [ADR-007: Live Ingest via kpubdata](007-kpubdata-live-ingest.md)
- [ADR-010: Run live ingest from the GitHub Actions data pipeline workflow](010-data-pipeline-live-workflow.md)
- Issue [#263](https://github.com/kpubdata-lab/younggeul/issues/263)
