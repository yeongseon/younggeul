# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false

from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmark_schema import BenchmarkScenario


VALID_SCENARIO_DATA = {
    "name": "gangnam-directional-v0.1",
    "description": "Directional contract benchmark for Gangnam-gu",
    "dataset_snapshot_id": "a" * 64,
    "target_gus": ["11680"],
    "target_period_start": "2024-01",
    "target_period_end": "2024-06",
    "expected_directions": {"11680": "up"},
    "contract_assertions": [
        {
            "field": "direction",
            "operator": "eq",
            "expected": "up",
        }
    ],
    "behavioral_assertions": [
        {
            "description": "Directional accuracy should stay high",
            "metric": "directional_accuracy",
            "operator": "gte",
            "threshold": 0.75,
        }
    ],
    "robustness_assertions": [
        {
            "description": "Model should be stable under moderate noise",
            "perturbation_type": "noise",
            "max_deviation": 0.1,
        }
    ],
    "tags": ["v0.1", "gangnam"],
}


def test_benchmark_scenario_valid_round_trip() -> None:
    scenario = BenchmarkScenario.model_validate(VALID_SCENARIO_DATA)
    reloaded = BenchmarkScenario.model_validate(scenario.model_dump())

    assert reloaded == scenario
    assert reloaded.expected_directions["11680"] == "up"


def test_from_yaml_str_valid() -> None:
    yaml_str = """
name: gangnam-yaml
dataset_snapshot_id: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
target_gus: ["11680", "11650"]
target_period_start: "2024-01"
target_period_end: "2024-03"
expected_directions:
  "11680": up
  "11650": flat
tags: [v0.1, yaml]
"""
    scenario = BenchmarkScenario.from_yaml_str(yaml_str)

    assert scenario.name == "gangnam-yaml"
    assert scenario.expected_directions["11650"] == "flat"


def test_from_yaml_str_invalid_yaml_raises_clear_error() -> None:
    bad_yaml = "name: [unterminated"

    with pytest.raises(ValueError, match="Invalid YAML"):
        BenchmarkScenario.from_yaml_str(bad_yaml)


@pytest.mark.parametrize(
    "snapshot_id",
    [
        "short",
        "g" * 64,
    ],
)
def test_dataset_snapshot_id_must_be_64_char_hex(snapshot_id: str) -> None:
    payload = {**VALID_SCENARIO_DATA, "dataset_snapshot_id": snapshot_id}

    with pytest.raises(ValidationError, match="dataset_snapshot_id"):
        BenchmarkScenario.model_validate(payload)


def test_all_assertion_types_are_parsed() -> None:
    scenario = BenchmarkScenario.model_validate(VALID_SCENARIO_DATA)

    assert len(scenario.contract_assertions) == 1
    assert len(scenario.behavioral_assertions) == 1
    assert len(scenario.robustness_assertions) == 1


def test_contract_assertion_operator_validation() -> None:
    payload = {
        **VALID_SCENARIO_DATA,
        "contract_assertions": [
            {
                "field": "direction",
                "operator": "contains",
                "expected": "up",
            }
        ],
    }

    with pytest.raises(ValidationError, match="contract_assertions"):
        BenchmarkScenario.model_validate(payload)


def test_behavioral_assertion_threshold_is_float() -> None:
    payload = {
        **VALID_SCENARIO_DATA,
        "behavioral_assertions": [
            {
                "description": "Allow coercion to float",
                "metric": "citation_coverage",
                "operator": "gte",
                "threshold": 1,
            }
        ],
    }
    scenario = BenchmarkScenario.model_validate(payload)

    assert isinstance(scenario.behavioral_assertions[0].threshold, float)


@pytest.mark.parametrize("perturbation_type", ["noise", "missing_data", "time_shift", "shock_injection"])
def test_robustness_assertion_perturbation_types(perturbation_type: str) -> None:
    payload = {
        **VALID_SCENARIO_DATA,
        "robustness_assertions": [
            {
                "description": "Test perturbation",
                "perturbation_type": perturbation_type,
                "max_deviation": 0.2,
            }
        ],
    }
    scenario = BenchmarkScenario.model_validate(payload)

    assert scenario.robustness_assertions[0].perturbation_type == perturbation_type


def test_from_yaml_with_temp_file(tmp_path: Path) -> None:
    yaml_path = tmp_path / "scenario.yaml"
    _ = yaml_path.write_text(
        """
name: temp-file-case
dataset_snapshot_id: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
target_gus:
  - "11710"
target_period_start: "2024-05"
target_period_end: "2024-07"
""",
        encoding="utf-8",
    )

    scenario = BenchmarkScenario.from_yaml(yaml_path)
    assert scenario.name == "temp-file-case"


def test_empty_assertions_lists_default() -> None:
    minimal = {
        "name": "minimal",
        "dataset_snapshot_id": "d" * 64,
        "target_gus": ["11440"],
        "target_period_start": "2024-01",
        "target_period_end": "2024-01",
    }
    scenario = BenchmarkScenario.model_validate(minimal)

    assert scenario.contract_assertions == []
    assert scenario.behavioral_assertions == []
    assert scenario.robustness_assertions == []


def test_tags_field_round_trip() -> None:
    payload = {**VALID_SCENARIO_DATA, "tags": ["v0.1", "interest_rate_shock", "gangnam"]}
    scenario = BenchmarkScenario.model_validate(payload)

    assert scenario.tags == ["v0.1", "interest_rate_shock", "gangnam"]
