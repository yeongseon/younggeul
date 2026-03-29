# CLI Reference

Younggeul provides a single entry-point CLI powered by [Click](https://click.palletsprojects.com/).

## Entry Point

```bash
younggeul [OPTIONS] COMMAND [ARGS]...
# or
python -m younggeul_app_kr_seoul_apartment.cli [OPTIONS] COMMAND [ARGS]...
```

## Global Options

| Option | Description |
|--------|-------------|
| `--output json` | Output format (currently `json` or default text) |
| `--version` | Show version and exit |
| `--help` | Show help message |

---

## Commands

### `ingest`

Run the Bronze → Silver → Gold data pipeline using fixture data.

```bash
younggeul ingest [--output-dir PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir` | `./output/pipeline` | Directory to write pipeline output |

**Example:**

```bash
younggeul ingest --output-dir ./output/pipeline
```

---

### `snapshot`

Snapshot management subcommand group.

#### `snapshot publish`

Create an immutable, SHA-256-verified dataset snapshot.

```bash
younggeul snapshot publish [--data-dir PATH] [--snapshot-dir PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--data-dir` | `./output/pipeline` | Pipeline output directory to snapshot |
| `--snapshot-dir` | `./output/snapshots` | Target directory for snapshots |

#### `snapshot list`

List all available snapshots.

```bash
younggeul snapshot list [--snapshot-dir PATH]
```

---

### `baseline`

Generate a statistical baseline forecast from the latest snapshot.

```bash
younggeul baseline [--snapshot-dir PATH] [--output-dir PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--snapshot-dir` | `./output/snapshots` | Snapshot directory to read from |
| `--output-dir` | `./output/baseline` | Directory to write baseline output |

---

### `simulate`

Run a multi-agent LangGraph simulation.

```bash
younggeul simulate --query TEXT [--max-rounds INT] [--output-dir PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--query` | *(required)* | Natural-language market query (Korean supported) |
| `--max-rounds` | `3` | Maximum simulation rounds |
| `--output-dir` | `./output/simulation` | Directory to write report and state |

**Example:**

```bash
younggeul simulate \
  --query "서울 강남구 아파트 시장 전망" \
  --max-rounds 2 \
  --output-dir ./output/simulation
```

---

### `report`

Display a rendered simulation report in the terminal.

```bash
younggeul report --report-file PATH
```

| Option | Default | Description |
|--------|---------|-------------|
| `--report-file` | *(required)* | Path to the `.md` report file |

**Example:**

```bash
younggeul report --report-file ./output/simulation/simulation_report_*.md
```

---

### `eval`

Run the pytest-based evaluation suite against canonical eval scenarios.

```bash
younggeul eval [--output-dir PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir` | `./eval_results` | Directory to write eval results |

See [Evaluation](evaluation.md) for details on eval cases and categories.
