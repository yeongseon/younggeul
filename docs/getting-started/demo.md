# Demo

The Younggeul demo script runs a complete end-to-end pipeline in a single command, using fixture data.

## Running the Demo

=== "make"

    ```bash
    make demo
    ```

=== "bash"

    ```bash
    bash scripts/demo.sh
    ```

## What the Demo Does

The demo executes six steps in sequence:

| Step | Command | Description |
|------|---------|-------------|
| 1 | `younggeul ingest` | Run Bronze→Silver→Gold ETL with fixture data |
| 2 | `younggeul snapshot publish` | Create an immutable SHA-256 snapshot |
| 3 | `younggeul snapshot list` | List available snapshots |
| 4 | `younggeul baseline` | Generate a statistical baseline forecast |
| 5 | `younggeul simulate` | Run 2-round multi-agent simulation |
| 6 | `younggeul report` | Render the generated report |

## Expected Output

After running the demo you will have:

```
output/
├── pipeline/          # Bronze, Silver, Gold data files
├── snapshots/         # Immutable snapshot with manifest.json
├── baseline/          # Baseline forecast JSON
└── simulation/        # Simulation report (.md) and state (.json)
```

The terminal will print a structured Markdown report with:

- Market summary paragraph
- Agent decision table (buyer, investor, tenant, landlord, broker)
- Evidence citations for each claim

## Customization

Override the output directory via the `DEMO_DIR` environment variable:

```bash
DEMO_DIR=/tmp/my-demo bash scripts/demo.sh
```

!!! tip
    The demo uses fixture data bundled in `apps/kr-seoul-apartment/`. No API key or network access is required.
