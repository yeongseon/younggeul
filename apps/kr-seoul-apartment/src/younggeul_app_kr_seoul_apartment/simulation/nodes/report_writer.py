# pyright: reportMissingImports=false

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from younggeul_core.state.simulation import ReportClaim

from ..evidence.store import EvidenceRecord, EvidenceStore
from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState


def _sorted_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    return sorted(
        records,
        key=lambda record: (
            record.round_no,
            record.subject_type,
            record.subject_id,
            record.kind,
            record.evidence_id,
        ),
    )


def _merge_evidence_ids(*record_groups: list[EvidenceRecord]) -> list[str]:
    merged = {record.evidence_id for group in record_groups for record in group}
    return sorted(merged)


def _claim_json(
    *,
    claim_type: str,
    section: str,
    subject: str,
    statement: str,
    metrics: Mapping[str, object] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": claim_type,
        "section": section,
        "subject": subject,
        "statement": statement,
        "metrics": None if metrics is None else dict(metrics),
    }
    return payload


def make_report_writer_node(evidence_store: EvidenceStore, event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        round_no = state.get("round_no", 0)
        world = state.get("world") or {}
        participants = state.get("participants") or {}
        scenario = state.get("scenario")

        simulation_facts = _sorted_records(evidence_store.get_by_kind("simulation_fact"))
        segment_facts = _sorted_records(evidence_store.get_by_kind("segment_fact"))
        participant_facts = _sorted_records(evidence_store.get_by_kind("participant_fact"))
        round_facts = _sorted_records(evidence_store.get_by_kind("round_fact"))

        report_claims: list[ReportClaim] = []

        for gu_code, segment in sorted(world.items()):
            by_subject = _sorted_records(evidence_store.get_by_subject("segment", gu_code))
            by_kind = [record for record in segment_facts if record.subject_id == gu_code]
            evidence_ids = _merge_evidence_ids(by_subject, by_kind)

            direction_statement = (
                f"{segment.gu_name}({gu_code}) price direction is {segment.price_trend} at round {round_no}."
            )
            direction_metrics = {
                "median_price": segment.current_median_price,
                "volume": segment.current_volume,
                "round_no": round_no,
            }
            report_claims.append(
                ReportClaim(
                    claim_id=str(uuid4()),
                    claim_json=_claim_json(
                        claim_type="direction",
                        section="direction",
                        subject=gu_code,
                        statement=direction_statement,
                        metrics=direction_metrics,
                    ),
                    evidence_ids=evidence_ids,
                    gate_status="pending",
                    repair_count=0,
                )
            )

            volume_statement = (
                f"{segment.gu_name}({gu_code}) trading volume is {segment.current_volume} "
                f"with median price {segment.current_median_price} at round {round_no}."
            )
            volume_metrics = {
                "volume": segment.current_volume,
                "median_price": segment.current_median_price,
                "round_no": round_no,
            }
            report_claims.append(
                ReportClaim(
                    claim_id=str(uuid4()),
                    claim_json=_claim_json(
                        claim_type="volume",
                        section="volume",
                        subject=gu_code,
                        statement=volume_statement,
                        metrics=volume_metrics,
                    ),
                    evidence_ids=evidence_ids,
                    gate_status="pending",
                    repair_count=0,
                )
            )

        role_summary: dict[str, dict[str, int]] = {}
        for participant in participants.values():
            role_str: str = participant.role
            if role_str not in role_summary:
                role_summary[role_str] = {"count": 0, "total_capital": 0, "total_holdings": 0}
            role_summary[role_str]["count"] += 1
            role_summary[role_str]["total_capital"] += participant.capital
            role_summary[role_str]["total_holdings"] += participant.holdings

        for role_key, summary in sorted(role_summary.items()):
            by_subject = _sorted_records(evidence_store.get_by_subject("participant_role", role_key))
            by_kind = [record for record in participant_facts if record.subject_id == role_key]
            evidence_ids = _merge_evidence_ids(by_subject, by_kind)

            statement = (
                f"Role {role_key} has {summary['count']} participants, total capital {summary['total_capital']}, "
                f"and holdings {summary['total_holdings']} at round {round_no}."
            )
            metrics = {
                "count": summary["count"],
                "total_capital": summary["total_capital"],
                "total_holdings": summary["total_holdings"],
                "round_no": round_no,
            }
            report_claims.append(
                ReportClaim(
                    claim_id=str(uuid4()),
                    claim_json=_claim_json(
                        claim_type="participant_summary",
                        section="drivers",
                        subject=f"role:{role_key}",
                        statement=statement,
                        metrics=metrics,
                    ),
                    evidence_ids=evidence_ids,
                    gate_status="pending",
                    repair_count=0,
                )
            )

        shocks = [] if scenario is None else sorted(scenario.shocks, key=lambda shock: shock.description)
        shock_descriptions = [
            f"{shock.shock_type}({shock.magnitude:+.2f}) on {','.join(sorted(shock.target_segments)) or 'all'}"
            for shock in shocks
        ]
        governance_actions = state.get("governance_actions") or {}
        risk_statement = (
            "Active shocks: " + "; ".join(shock_descriptions) if shock_descriptions else "No active shocks in scenario."
        )
        risk_statement = f"{risk_statement} Governance actions proposed: {len(governance_actions)}."
        risk_metrics = {
            "shock_count": len(shocks),
            "governance_actions": len(governance_actions),
            "round_no": round_no,
        }
        risk_evidence_ids = _merge_evidence_ids(simulation_facts, round_facts)
        report_claims.append(
            ReportClaim(
                claim_id=str(uuid4()),
                claim_json=_claim_json(
                    claim_type="risk_factors",
                    section="risks",
                    subject="simulation",
                    statement=risk_statement,
                    metrics=risk_metrics,
                ),
                evidence_ids=risk_evidence_ids,
                gate_status="pending",
                repair_count=0,
            )
        )

        simulation_evidence_ids = _merge_evidence_ids(
            simulation_facts,
            _sorted_records(evidence_store.get_by_subject("simulation", run_meta.run_id)),
        )
        overview_statement = (
            f"Simulation {run_meta.run_id} completed {round_no} rounds across {len(world)} segments "
            f"with {len(participants)} participants."
        )
        overview_metrics = {
            "round_no": round_no,
            "segment_count": len(world),
            "participant_count": len(participants),
        }
        report_claims.append(
            ReportClaim(
                claim_id=str(uuid4()),
                claim_json=_claim_json(
                    claim_type="simulation_overview",
                    section="summary",
                    subject="simulation",
                    statement=overview_statement,
                    metrics=overview_metrics,
                ),
                evidence_ids=simulation_evidence_ids,
                gate_status="pending",
                repair_count=0,
            )
        )

        claim_ids = [claim.claim_id for claim in report_claims]
        event_id = str(uuid4())
        event_store.append(
            SimulationEvent(
                event_id=event_id,
                run_id=run_meta.run_id,
                round_no=round_no,
                event_type="REPORT_WRITTEN",
                timestamp=datetime.now(timezone.utc),
                payload={"claim_ids": claim_ids},
            )
        )

        return {"report_claims": report_claims, "event_refs": [event_id]}

    return node
