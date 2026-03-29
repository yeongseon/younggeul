# Evaluation

Younggeul uses a **pytest-based evaluation framework** to validate simulation quality, contract correctness, and behavioral properties.

## Running Evaluations

```bash
# Via CLI
younggeul eval --output-dir eval_results

# Via pytest directly
pytest -m eval -v
```

---

## Eval Case Fixtures

Eval cases are defined as **YAML fixtures** in `eval_cases/`:

```
eval_cases/
├── gangnam_2round_bull.yaml
├── seocho_0round_baseline.yaml
└── gangnam_5round_stress.yaml
```

Each fixture specifies:

```yaml
name: gangnam_2round_bull
query: "서울 강남구 아파트 상승 전망"
max_rounds: 2
expected:
  citation_gate: passed
  coverage_pct_min: 100
  report_contains: ["강남구", "상승"]
```

---

## Test Categories

| Marker | Description |
|--------|-------------|
| `smoke` | Basic import and CLI invocation checks |
| `contract` | Schema validation — Bronze/Silver/Gold/Evidence field contracts |
| `behavioral` | Simulation output properties (citation coverage, report structure) |
| `robustness` | Edge cases — empty input, zero rounds, missing data |

---

## Canonical Scenarios

| Scenario | Query | Rounds | Purpose |
|----------|-------|--------|---------|
| `gangnam_2round_bull` | 서울 강남구 아파트 상승 전망 | 2 | Standard bullish scenario |
| `seocho_0round_baseline` | 서울 서초구 아파트 기준선 | 0 | Baseline-only, no simulation rounds |
| `gangnam_5round_stress` | 서울 강남구 아파트 하락 스트레스 | 5 | Stress test — maximum rounds |

---

## Nightly Evaluation

A GitHub Actions workflow runs the full eval suite nightly against the `main` branch. Results are stored as workflow artifacts.

See `.github/workflows/` for the CI configuration.

---

## Adding New Eval Cases

1. Create a YAML file in `eval_cases/` following the fixture schema above.
2. Add a corresponding test in `apps/kr-seoul-apartment/tests/eval/` using the `@pytest.mark.eval` marker.
3. Run `pytest -m eval -v` to verify the new case passes.

!!! tip
    Use the `gangnam_2round_bull.yaml` fixture as a template for new scenarios.
