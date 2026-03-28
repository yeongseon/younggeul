import re
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_YYYY_MM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ContractAssertion(BaseModel):
    field: str
    operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "not_in"]
    expected: str | int | float | bool | list[object]
    tolerance: float | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class BehavioralAssertion(BaseModel):
    description: str
    metric: str
    operator: Literal["gt", "lt", "gte", "lte", "eq"]
    threshold: float

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class RobustnessAssertion(BaseModel):
    description: str
    perturbation_type: Literal["noise", "missing_data", "time_shift", "shock_injection"]
    max_deviation: float

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class BenchmarkScenario(BaseModel):
    name: str
    description: str | None = None
    dataset_snapshot_id: str
    target_gus: list[str]
    target_period_start: str
    target_period_end: str
    expected_directions: dict[str, Literal["up", "down", "flat"]] = Field(default_factory=dict)
    contract_assertions: list[ContractAssertion] = Field(default_factory=list)
    behavioral_assertions: list[BehavioralAssertion] = Field(default_factory=list)
    robustness_assertions: list[RobustnessAssertion] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    @field_validator("dataset_snapshot_id")
    @classmethod
    def validate_dataset_snapshot_id(cls, value: str) -> str:
        if not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("dataset_snapshot_id must be a 64-character hex SHA-256 string")
        return value

    @field_validator("target_period_start", "target_period_end")
    @classmethod
    def validate_target_period_format(cls, value: str) -> str:
        if not _YYYY_MM_RE.fullmatch(value):
            raise ValueError("target_period fields must use YYYY-MM format")
        return value

    @model_validator(mode="after")
    def validate_target_period_order(self) -> "BenchmarkScenario":
        start = datetime.strptime(self.target_period_start, "%Y-%m")
        end = datetime.strptime(self.target_period_end, "%Y-%m")
        if end < start:
            raise ValueError("target_period_end must be greater than or equal to target_period_start")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BenchmarkScenario":
        yaml_path = Path(path)
        yaml_str = yaml_path.read_text(encoding="utf-8")
        return cls.from_yaml_str(yaml_str)

    @classmethod
    def from_yaml_str(cls, yaml_str: str) -> "BenchmarkScenario":
        try:
            parsed = cast(object, yaml.safe_load(yaml_str))
        except yaml.YAMLError as error:
            raise ValueError(f"Invalid YAML: {error}") from error

        if not isinstance(parsed, dict):
            raise ValueError("Benchmark scenario YAML must parse to a mapping/object")

        return cls.model_validate(parsed)
