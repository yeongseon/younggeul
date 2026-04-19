# Installation

## Prerequisites

- **Python 3.12+** — Younggeul uses modern typing features.
- **[uv](https://github.com/astral-sh/uv)** (recommended) or `pip`.
- **Git** to clone the repository.

## Clone & Install

=== "uv (recommended)"

    ```bash
    git clone https://github.com/yeongseon/younggeul.git
    cd younggeul
    uv pip install -e ".[dev,kr-seoul-apartment]"
    ```

=== "pip"

    ```bash
    git clone https://github.com/yeongseon/younggeul.git
    cd younggeul
    pip install -e ".[dev,kr-seoul-apartment]"
    ```

## Verify Installation

```bash
younggeul --version
```

Expected output:

```
younggeul, version 0.1.0
```

## Optional: MkDocs for Documentation

To build or serve the documentation locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

## Real Data Ingestion (Optional)

By default, `younggeul ingest` uses **fixture data** bundled with the package — no API key needed.

To ingest real MOLIT/BOK/KOSTAT data, register at [data.go.kr](https://www.data.go.kr), [한국은행 ECOS](https://ecos.bok.or.kr), and [KOSIS](https://kosis.kr) and export the three API keys consumed by the [kpubdata](https://pypi.org/project/kpubdata/) client:

```bash
export KPUBDATA_DATAGO_API_KEY="your-data.go.kr-key"
export KPUBDATA_BOK_API_KEY="your-bok-ecos-key"
export KPUBDATA_KOSIS_API_KEY="your-kosis-key"

younggeul ingest --source live --gu 11680 --month 202503 --output-dir ./output/live
```

`--gu` is a 5-digit MOLIT sigungu code (e.g. `11680` = 강남구) and `--month` is `YYYYMM`. v0.1 covers one gu × one month per invocation. See [ADR-007](../adr/007-kpubdata-live-ingest.md) for the design and current scope.

!!! note
    All tutorial examples use fixture data; no API key is required.
