# Evidence-Gated Reporting

The reporting subsystem ensures every claim in a simulation report is backed by a verifiable evidence record from the data plane.

## Pipeline Overview

```
evidence_builder ──► report_writer ──► citation_gate ──► report_renderer
                                              │
                                     PASS ───┘──── FAIL
                                      │              │
                               RenderedReport    Error raised
                               published         (no report)
```

---

## EvidenceRecord

An `EvidenceRecord` links a simulation event to a specific Gold metric row:

```python
class EvidenceRecord(TypedDict):
    evidence_id: str           # UUID
    kind: EvidenceKind         # "price", "rate", "migration", "baseline"
    source_id: str             # Connector ID (e.g., "molit_apt_v1")
    source_url: str            # Canonical URL
    gu: str                    # District code
    year_month: str            # "YYYY-MM"
    value: float               # The cited metric value
    unit: str                  # "krw", "pct", "count"
```

### Evidence Kinds

| Kind | Description |
|------|-------------|
| `price` | Average or median transaction price from Gold |
| `rate` | BOK interest rate |
| `migration` | KOSTAT net migration count |
| `baseline` | Baseline forecast value |

---

## ReportClaim Lifecycle

```
PENDING ──► (citation_gate validates) ──► PASSED
                                    └──► FAILED
```

```python
class ReportClaim(TypedDict):
    claim_id: str
    text: str                  # Claim sentence in the report
    evidence_ids: list[str]    # Must match EvidenceRecord IDs
    status: Literal["pending", "passed", "failed"]
```

---

## Citation Gate

The citation gate iterates all `ReportClaim` objects and checks:

1. `evidence_ids` is non-empty
2. Each ID exists in the evidence store
3. The evidence kind is appropriate for the claim context

If **any** claim fails: `citation_gate_passed = False` and rendering is skipped (raises `CitationGateError`).

Coverage is calculated as:

```
coverage_pct = (passed_claims / total_claims) * 100
```

For v0.1, the threshold is **100%** — all claims must pass.

---

## RenderedReport

The final output is a `RenderedReport`:

```python
class RenderedReport(TypedDict):
    report_id: str
    simulation_id: str
    query: str
    markdown: str              # Human-readable Markdown report
    json_payload: dict         # Structured data with claims + evidence
    coverage_pct: float        # Citation coverage (100.0 for passing reports)
    generated_at: str          # ISO-8601 timestamp
```

The `markdown` field is what `younggeul report` renders to the terminal.

!!! note
    A report that fails the citation gate is never written to disk. This ensures all persisted reports have 100% citation coverage.
