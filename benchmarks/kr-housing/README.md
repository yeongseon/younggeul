# KR Housing Benchmark Scenarios

`BenchmarkScenario` defines a frozen, YAML-friendly contract for evaluating younggeul outputs on Korea housing tasks. It captures dataset snapshot identity, evaluation window, district targets, expected directions, and assertion groups for contract, behavioral, and robustness checks.

## YAML examples

### 1) Simple directional accuracy benchmark (강남구)

```yaml
name: gangnam-directional-v0.1
description: Directional accuracy check for 강남구
dataset_snapshot_id: a3f4b5c6d7e8f90123456789abcdef0123456789abcdef0123456789abcdef
target_gus:
  - "11680" # 강남구
target_period_start: "2024-01"
target_period_end: "2024-06"
expected_directions:
  "11680": up
contract_assertions:
  - field: direction
    operator: eq
    expected: up
behavioral_assertions:
  - description: Maintain directional signal quality
    metric: directional_accuracy
    operator: gte
    threshold: 0.75
tags: [v0.1, gangnam]
```

### 2) Interest rate shock robustness benchmark

```yaml
name: seoul-interest-rate-shock-robustness
description: Stability test under rate shock perturbation
dataset_snapshot_id: b3f4b5c6d7e8f90123456789abcdef0123456789abcdef0123456789abcdef
target_gus: ["11680", "11650", "11710"]
target_period_start: "2024-01"
target_period_end: "2024-09"
behavioral_assertions:
  - description: Keep citation grounding above minimum under shocks
    metric: citation_coverage
    operator: gte
    threshold: 0.60
robustness_assertions:
  - description: Directional output should not drift too much after shock
    perturbation_type: shock_injection
    max_deviation: 0.15
tags: [v0.1, interest_rate_shock, robustness]
```

### 3) Multi-district volume prediction benchmark

```yaml
name: seoul-multi-gu-volume-v0.1
description: Volume + direction contract for multiple districts
dataset_snapshot_id: c3f4b5c6d7e8f90123456789abcdef0123456789abcdef0123456789abcdef
target_gus:
  - "11680" # 강남구
  - "11650" # 서초구
  - "11710" # 송파구
  - "11740" # 강동구
target_period_start: "2023-10"
target_period_end: "2024-06"
expected_directions:
  "11680": up
  "11650": up
  "11710": flat
  "11740": down
contract_assertions:
  - field: volume
    operator: gte
    expected: 1000
    tolerance: 50.0
  - field: direction
    operator: in
    expected: [up, flat]
behavioral_assertions:
  - description: Hit directional quality threshold across target districts
    metric: directional_accuracy
    operator: gte
    threshold: 0.70
tags: [v0.1, multi_district, volume]
```

## Run tests

```bash
PYTHONPATH=benchmarks/kr-housing/src:core/src python3 -m pytest benchmarks/kr-housing/tests/ -v
```
