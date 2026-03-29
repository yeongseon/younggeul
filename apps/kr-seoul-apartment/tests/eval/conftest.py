from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

EVAL_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "eval_cases"


def load_eval_case(filename: str) -> dict[str, Any]:
    """Load a single eval case YAML file."""
    path = EVAL_CASES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_eval_cases() -> list[dict[str, Any]]:
    """Load all eval case YAML files from eval_cases/."""
    cases = []
    for path in sorted(EVAL_CASES_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            cases.append(yaml.safe_load(f))
    return cases


def eval_case_ids() -> list[str]:
    """Return scenario IDs for parametrize."""
    return [case["scenario_id"] for case in load_all_eval_cases()]


@pytest.fixture(params=load_all_eval_cases(), ids=lambda c: c["scenario_id"])
def eval_case(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parametrized fixture that yields each eval case."""
    result: dict[str, Any] = request.param
    return result
