# ADR-010: Run live ingest from the GitHub Actions data pipeline workflow

## Status
Accepted

## Date
2026-04-20

## Context

The repository already exposes a production-shaped `younggeul ingest` CLI, but `.github/workflows/data-pipeline.yml` was still a placeholder workflow:

- `workflow_dispatch` inputs did not match the real CLI contract (`molit_apt_trade`, `start_month`, `end_month`).
- The workflow only exported `DATA_GO_KR_API_KEY`, while the live ingest path validates `KPUBDATA_DATAGO_API_KEY`, `KPUBDATA_BOK_API_KEY`, and `KPUBDATA_KOSIS_API_KEY`.
- The main run step was an `echo "TODO"`, so scheduled runs never fetched live data.
- Artifact upload pointed at `data/bronze/**/manifest.json`, which is not where `younggeul ingest` writes output.

That gap meant we had a documented live-ingest path in ADR-007 and ADR-008, but no repository-native automation that actually exercised it on a schedule.

## Decision

The `Data Pipeline` GitHub Actions workflow now runs the real `younggeul ingest` command and adapts its inputs to the existing CLI rather than changing the CLI surface.

### 1. Workflow inputs mirror the CLI shape

`workflow_dispatch` now exposes:

- `source` as `fixture|live` (default `live`),
- `gus` as a CSV of 5-digit MOLIT sigungu codes,
- `months` as a CSV of `YYYYMM` values,
- `output_dir` as the ingest destination directory.

This keeps the workflow aligned with `younggeul ingest --source --gus --months --output-dir` and avoids the previous mismatch between workflow UX and CLI validation.

### 2. Scheduled runs use conservative live defaults

The Sunday 06:00 UTC cron is preserved, but it now resolves to:

- `--source live`
- `--gus 11680` (Gangnam-gu)
- `--months <last completed UTC month>`
- `--output-dir output/pipeline`

Gangnam (`11680`) is the default because it is already the most common live-ingest example in the repo, has active transaction volume, and gives us one stable district slice for a smoke-style scheduled ingest. Using the last completed month avoids querying an in-progress calendar month where MOLIT publication lag or partial upstream availability would create avoidable empty runs.

### 3. Empty manual `months` falls back to the last completed month

Manual triggers may leave `months` empty. In that case the workflow computes the previous UTC calendar month in `YYYYMM` format before invoking the CLI. Non-empty `months` values are passed through unchanged so operators can request YoY/MoM windows explicitly.

### 4. Live mode validates all required secrets up front

Before the ingest command runs, the workflow fails fast if any of these secrets are missing:

- `KPUBDATA_DATAGO_API_KEY`
- `KPUBDATA_BOK_API_KEY`
- `KPUBDATA_KOSIS_API_KEY`

This matches the live client factory and avoids a slower failure deep inside the Python process.

### 5. Artifacts follow the CLI output directory

The workflow uploads `output/pipeline/**/*.jsonl` plus any `manifest.json` produced under the selected output directory, with `if-no-files-found: warn`. A warning is preferable to `ignore` because missing JSONL output is a workflow health signal, not something to suppress silently.

## Manual trigger examples

### 1. Default live smoke run

Leave the defaults as-is in `workflow_dispatch` to ingest Gangnam for the last completed UTC month:

- `source=live`
- `gus=11680`
- `months=`
- `output_dir=output/pipeline`

### 2. Multi-month YoY run for one district

- `source=live`
- `gus=11680`
- `months=202403,202503`
- `output_dir=output/pipeline`

### 3. Multi-district run

- `source=live`
- `gus=11680,11440`
- `months=202502,202503`
- `output_dir=output/pipeline`

### 4. Fixture-mode workflow smoke test

- `source=fixture`
- `gus=11680`
- `months=`
- `output_dir=output/pipeline`

The workflow still passes `--gus` and `--months` in fixture mode, but the CLI ignores those live-only options because validation only applies when `--source=live`.

## Secret requirements

Repository Actions secrets must include:

- `KPUBDATA_DATAGO_API_KEY` for data.go.kr / MOLIT RTMS
- `KPUBDATA_BOK_API_KEY` for BOK ECOS
- `KPUBDATA_KOSIS_API_KEY` for KOSIS migration data

The older `DATA_GO_KR_API_KEY` secret may remain in the repository for backward compatibility, but this workflow no longer depends on it.

## Failure modes

### Missing keys

The workflow exits before calling Python and surfaces explicit GitHub Actions errors for each missing `KPUBDATA_*` secret.

### kpubdata or upstream API limits

Live ingest depends on external public APIs behind `kpubdata`. Transient provider throttling, quota exhaustion, or upstream envelope changes can fail the run even when the workflow wiring is correct.

### MOLIT release lag

The most recent calendar month is not always fully published when the cron fires. Defaulting to the last completed month reduces this risk, but delayed MOLIT publication can still produce sparse or empty trade slices for very recent periods.

### Partial output generation

If ingest fails before JSONL output is written, artifact upload emits a warning instead of silently succeeding. That makes broken runs easier to diagnose from the Actions UI.

## Consequences

**Pros.**

- The scheduled workflow now exercises the same live ingest path documented in ADR-007 and ADR-008.
- Manual dispatch parameters map directly to the public CLI, reducing operator confusion.
- Fail-fast secret validation makes misconfiguration visible before a long-running job spends time installing dependencies.

**Cons.**

- Scheduled automation is now exposed to upstream API availability, throttling, and publication lag.
- The default cron run only covers one district (`11680`), so it is a health check rather than comprehensive Seoul coverage.

## Related

- [ADR-007: Live Ingest via kpubdata](007-kpubdata-live-ingest.md)
- [ADR-008: Activate KOSTAT Migration in Live Ingest at 시도 Granularity](008-kostat-live-activation.md)
- `.github/workflows/data-pipeline.yml`
