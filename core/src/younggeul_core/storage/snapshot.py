import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class SnapshotTableEntry(BaseModel):
    table_name: str
    table_hash: str
    record_count: int = Field(ge=0)
    schema_version: str
    source_uri: str | None = None
    file_format: Literal["parquet", "csv", "jsonl"] = "parquet"

    model_config = ConfigDict(frozen=True)

    @field_validator("table_hash")
    @classmethod
    def validate_table_hash(cls, value: str) -> str:
        if not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("table_hash must be a 64-character lowercase hex SHA-256 string")
        return value


class SnapshotManifest(BaseModel):
    dataset_snapshot_id: str
    created_at: datetime
    description: str | None = None
    table_entries: list[SnapshotTableEntry]
    source_ids: list[str] = Field(default_factory=list)
    ingestion_started_at: datetime | None = None
    ingestion_completed_at: datetime | None = None

    model_config = ConfigDict(frozen=True)

    @field_validator("dataset_snapshot_id")
    @classmethod
    def validate_dataset_snapshot_id(cls, value: str) -> str:
        if not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("dataset_snapshot_id must be a 64-character lowercase hex SHA-256 string")
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def table_hashes(self) -> dict[str, str]:
        return {entry.table_name: entry.table_hash for entry in self.table_entries}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def record_counts(self) -> dict[str, int]:
        return {entry.table_name: entry.record_count for entry in self.table_entries}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_records(self) -> int:
        return sum(entry.record_count for entry in self.table_entries)

    def validate_integrity(self) -> bool:
        computed_id = self.compute_snapshot_id(self.table_hashes)
        return computed_id == self.dataset_snapshot_id

    def get_table(self, name: str) -> SnapshotTableEntry | None:
        for entry in self.table_entries:
            if entry.table_name == name:
                return entry
        return None

    @classmethod
    def compute_snapshot_id(cls, table_hashes: dict[str, str]) -> str:
        items = sorted(table_hashes.items(), key=lambda item: item[0])
        joined = "".join(f"{table_name}:{table_hash}" for table_name, table_hash in items)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
