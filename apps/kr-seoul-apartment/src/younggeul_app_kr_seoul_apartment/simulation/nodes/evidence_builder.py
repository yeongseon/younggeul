from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..evidence.store import EvidenceRecord, EvidenceStore
from ..graph_state import SimulationGraphState


def make_evidence_builder_node(evidence_store: EvidenceStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        run_id = run_meta.run_id
        round_no = state.get("round_no", 0)
        world = state.get("world") or {}
        participants = state.get("participants") or {}
        last_outcome = state.get("last_outcome")
        event_refs = state.get("event_refs") or []
        now = datetime.now(timezone.utc)

        evidence_ids: list[str] = []

        sim_eid = str(uuid4())
        evidence_store.add(
            EvidenceRecord(
                evidence_id=sim_eid,
                kind="simulation_fact",
                subject_type="simulation",
                subject_id=run_id,
                round_no=round_no,
                payload={
                    "total_rounds": round_no,
                    "total_segments": len(world),
                    "total_participants": len(participants),
                    "completion_reason": (
                        "max_rounds"
                        if last_outcome is None or last_outcome.market_actions_resolved > 0
                        else "market_frozen"
                    ),
                },
                source_event_ids=list(event_refs[-1:]),
                created_at=now,
            )
        )
        evidence_ids.append(sim_eid)

        for gu_code, segment in sorted(world.items()):
            seg_eid = str(uuid4())
            evidence_store.add(
                EvidenceRecord(
                    evidence_id=seg_eid,
                    kind="segment_fact",
                    subject_type="segment",
                    subject_id=gu_code,
                    round_no=round_no,
                    payload={
                        "gu_code": gu_code,
                        "gu_name": segment.gu_name,
                        "final_median_price": segment.current_median_price,
                        "final_volume": segment.current_volume,
                        "final_trend": segment.price_trend,
                        "final_sentiment": segment.sentiment_index,
                    },
                    source_event_ids=[],
                    created_at=now,
                )
            )
            evidence_ids.append(seg_eid)

        role_data: dict[str, dict[str, Any]] = {}
        for participant in participants.values():
            role = participant.role
            if role not in role_data:
                role_data[role] = {"count": 0, "total_capital": 0, "total_holdings": 0}
            role_data[role]["count"] += 1
            role_data[role]["total_capital"] += participant.capital
            role_data[role]["total_holdings"] += participant.holdings

        for role_key, data in sorted(role_data.items()):
            part_eid = str(uuid4())
            evidence_store.add(
                EvidenceRecord(
                    evidence_id=part_eid,
                    kind="participant_fact",
                    subject_type="participant_role",
                    subject_id=role_key,
                    round_no=round_no,
                    payload={
                        "role": role_key,
                        **data,
                    },
                    source_event_ids=[],
                    created_at=now,
                )
            )
            evidence_ids.append(part_eid)

        if last_outcome is not None:
            outcome_eid = str(uuid4())
            evidence_store.add(
                EvidenceRecord(
                    evidence_id=outcome_eid,
                    kind="round_fact",
                    subject_type="round",
                    subject_id=f"round-{last_outcome.round_no}",
                    round_no=last_outcome.round_no,
                    payload={
                        "round_no": last_outcome.round_no,
                        "market_actions_resolved": last_outcome.market_actions_resolved,
                        "cleared_volume": last_outcome.cleared_volume,
                        "price_changes": last_outcome.price_changes,
                    },
                    source_event_ids=[],
                    created_at=now,
                )
            )
            evidence_ids.append(outcome_eid)

        return {"evidence_refs": evidence_ids}

    return node
