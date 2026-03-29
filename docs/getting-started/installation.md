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

To ingest real MOLIT/BOK/KOSTAT data, you need a [PublicDataReader](https://github.com/WooilJeong/PublicDataReader) API key from [data.go.kr](https://www.data.go.kr).

Set the key via environment variable before running `younggeul ingest`:

```bash
export PUBLIC_DATA_API_KEY="your-api-key-here"
younggeul ingest --output-dir ./output/pipeline
```

!!! note
    All tutorial examples use fixture data; no API key is required.
