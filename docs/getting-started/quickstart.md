# Quick Start

This guide walks you through a complete simulation run using **fixture data** — no API key required.

## Overview

A full Younggeul pipeline has five stages:

```
ingest → snapshot → baseline → simulate → report
```

## Step 1 — Ingest Data

Run the Bronze → Silver → Gold ETL pipeline against fixture data:

```bash
younggeul ingest --output-dir ./output/pipeline
```

Expected output:

```
[ingest] Running Bronze layer...  ✓
[ingest] Running Silver layer...  ✓
[ingest] Running Gold layer...    ✓
[ingest] Written to ./output/pipeline
```

## Step 2 — Publish a Snapshot

Create an immutable, SHA-256-verified snapshot from the pipeline output:

```bash
younggeul snapshot publish \
  --data-dir ./output/pipeline \
  --snapshot-dir ./output/snapshots
```

```
[snapshot] Published snapshot: snap_20260101_abc123
[snapshot] Manifest written to ./output/snapshots/snap_20260101_abc123/manifest.json
```

## Step 3 — Generate Baseline Forecast

Produce a statistical baseline forecast from the latest snapshot:

```bash
younggeul baseline \
  --snapshot-dir ./output/snapshots \
  --output-dir ./output/baseline
```

## Step 4 — Run Simulation

Launch a multi-agent simulation with a natural-language query:

```bash
younggeul simulate \
  --query "서울 강남구 아파트 시장 전망" \
  --max-rounds 2 \
  --output-dir ./output/simulation
```

```
[simulate] Loaded snapshot: snap_20260101_abc123
[simulate] Round 1/2 complete
[simulate] Round 2/2 complete
[simulate] Citation gate: PASSED (coverage 100%)
[simulate] Report written to ./output/simulation/simulation_report_*.md
```

## Step 5 — View the Report

Render the simulation report to the terminal:

```bash
younggeul report --report-file ./output/simulation/simulation_report_*.md
```

## Step 6 — Run Evaluation

Run the pytest-based evaluation suite against canonical scenarios:

```bash
younggeul eval --output-dir eval_results
```

## All-in-One (Demo Script)

The above steps are bundled in the demo script:

```bash
make demo
# or
bash scripts/demo.sh
```

See [Demo](demo.md) for details.
