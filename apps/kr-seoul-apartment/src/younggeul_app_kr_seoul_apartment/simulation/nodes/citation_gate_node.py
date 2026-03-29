# pyright: reportMissingImports=false

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from younggeul_core.state.simulation import ReportClaim

from ..evidence.store import EvidenceRecord, EvidenceStore
from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState


def _matches_subject(
    *,
    subject: str,
    run_id: str,
    world_keys: set[str],
    evidence_records: list[EvidenceRecord],
) -> bool:
    if subject == "simulation":
        return any(record.subject_type == "simulation" and record.subject_id == run_id for record in evidence_records)
    if subject.startswith("role:"):
        role_name = subject.split(":", 1)[1]
        return any(
            record.subject_type == "participant_role" and record.subject_id == role_name for record in evidence_records
        )
    if subject in world_keys:
        return any(record.subject_type == "segment" and record.subject_id == subject for record in evidence_records)
    return any(record.subject_id == subject for record in evidence_records)


def make_citation_gate_node(evidence_store: EvidenceStore, event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        round_no = state.get("round_no", 0)
        world = state.get("world") or {}
        report_claims = state.get("report_claims", [])

        warnings: list[str] = []
        validated_claims: list[ReportClaim] = []
        failed_claim_ids: list[str] = []
        passed = 0

        for claim in report_claims:
            failure_reason: str | None = None
            evidence_ids = list(claim.evidence_ids)

            if not evidence_ids:
                failure_reason = "missing evidence_ids"

            resolved_records: list[EvidenceRecord] = []
            if failure_reason is None:
                for evidence_id in evidence_ids:
                    record = evidence_store.get(evidence_id)
                    if record is None:
                        failure_reason = f"missing evidence record: {evidence_id}"
                        break
                    resolved_records.append(record)

            if failure_reason is None:
                subject_raw = claim.claim_json.get("subject")
                if isinstance(subject_raw, str) and subject_raw:
                    if not _matches_subject(
                        subject=subject_raw,
                        run_id=run_meta.run_id,
                        world_keys=set(world),
                        evidence_records=resolved_records,
                    ):
                        failure_reason = "subject mismatch with evidence"

            if failure_reason is None and resolved_records:
                if not any(record.round_no == round_no for record in resolved_records):
                    failure_reason = f"no evidence for round_no={round_no}"

            gate_status: Literal["passed", "failed"] = "failed" if failure_reason is not None else "passed"
            validated_claims.append(
                ReportClaim(
                    claim_id=claim.claim_id,
                    claim_json=claim.claim_json,
                    evidence_ids=evidence_ids,
                    gate_status=gate_status,
                    repair_count=0,
                )
            )

            if failure_reason is None:
                passed += 1
            else:
                failed_claim_ids.append(claim.claim_id)
                warnings.append(f"claim_id={claim.claim_id}: {failure_reason}")

        failed = len(failed_claim_ids)
        event_id = str(uuid4())
        event_store.append(
            SimulationEvent(
                event_id=event_id,
                run_id=run_meta.run_id,
                round_no=round_no,
                event_type="CITATION_GATE",
                timestamp=datetime.now(timezone.utc),
                payload={
                    "total_claims": len(validated_claims),
                    "passed": passed,
                    "failed": failed,
                    "failed_claim_ids": failed_claim_ids,
                },
            )
        )

        return {"warnings": warnings, "event_refs": [event_id]}

    return node
