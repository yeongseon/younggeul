EVIDENCE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    dataset_snapshot_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN ('int', 'float', 'str', 'date', 'bool')),
    gu_code TEXT,
    period TEXT,
    created_at TEXT NOT NULL
);
"""

CLAIMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS claim_records (
    claim_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    claim_json TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    gate_status TEXT NOT NULL DEFAULT 'pending' CHECK (gate_status IN ('pending', 'passed', 'failed', 'repaired')),
    gate_checked_at TEXT,
    repair_count INTEGER NOT NULL DEFAULT 0 CHECK (repair_count <= 2),
    repair_notes TEXT,
    created_at TEXT NOT NULL
);
"""

GATE_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS gate_results (
    claim_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
    checked_evidence_ids TEXT NOT NULL,
    mismatches TEXT NOT NULL DEFAULT '[]',
    checked_at TEXT NOT NULL
);
"""
