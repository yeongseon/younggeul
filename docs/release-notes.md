# Release Notes

## v0.1.0

*Initial release — Seoul apartment simulation, evidence-gated reporting*

### Data Plane

- **Bronze → Silver → Gold pipeline** with connectors for MOLIT (apartment transactions), BOK (interest rates), and KOSTAT (migration data)
- **Pydantic v2 models** for all Silver and Gold layers with strict validation
- **Immutable snapshot system** — SHA-256 content-addressed dataset snapshots with manifest verification
- **Trend enrichment** — YoY and MoM calculations on Gold aggregates
- **Baseline forecaster** — deterministic statistical forecast from Gold metrics

### Simulation Plane

- **LangGraph-based multi-agent simulation** with configurable round count
- **Five participant agents**: buyer, investor, tenant, landlord, broker (v0.1: deterministic stubs)
- **Event store** and **evidence store** for traceability through the simulation
- **SimulationGraphState** TypedDict with append-only reducers

### Evidence-Gated Reporting

- **Citation gate** — reports fail to publish if any claim lacks a citation
- **100% coverage requirement** — all claims must be backed by Gold metric evidence
- **EvidenceRecord** schema with source URL, kind, value, and unit
- **RenderedReport** output in both Markdown and structured JSON

### Evaluation

- **pytest-based eval framework** with `@pytest.mark.eval` marker
- **3 canonical scenarios**: `gangnam_2round_bull`, `seocho_0round_baseline`, `gangnam_5round_stress`
- **YAML eval case fixtures** for reproducible scenario definitions
- **Nightly CI workflow** running full eval suite

### Observability

- **OpenTelemetry tracing** on all simulation nodes
- **CodeQL security scanning** in CI

### CLI

- **Click-based CLI** with 6 commands: `ingest`, `snapshot` (publish/list), `baseline`, `simulate`, `report`, `eval`
- Entry point: `younggeul`

### Demo

- **End-to-end demo script** (`scripts/demo.sh` / `make demo`) using fixture data — no API key required

---

!!! note "Scope"
    v0.1 covers **Seoul apartments only**. Features deferred to future releases include Web UI, LiteLLM OTEL integration, and Grafana dashboards.
