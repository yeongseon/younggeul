from __future__ import annotations

# pyright: reportMissingImports=false

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from younggeul_core.state.simulation import ReportClaim

from ..events import EventStore, SimulationEvent
from ..graph_state import SimulationGraphState
from ..schemas.report import RenderedClaimEntry, RenderedReport, RenderedSection

_SECTION_ORDER: tuple[str, ...] = ("summary", "direction", "volume", "drivers", "risks")
_SECTION_TITLES: dict[str, str] = {
    "summary": "Summary",
    "direction": "Direction",
    "volume": "Volume",
    "drivers": "Drivers",
    "risks": "Risks",
}


def make_report_renderer_node(event_store: EventStore) -> Any:
    def node(state: SimulationGraphState) -> dict[str, Any]:
        run_meta = state.get("run_meta")
        if run_meta is None:
            raise ValueError("run_meta is required")

        report_claims = state.get("report_claims") or []
        round_no = state.get("round_no", 0)
        rendered_at = datetime.now(timezone.utc)

        passed_claims = [claim for claim in report_claims if claim.gate_status in ("passed", "pending")]
        blocked_claims = [claim for claim in report_claims if claim.gate_status not in ("passed", "pending")]

        section_entries: dict[str, list[RenderedClaimEntry]] = defaultdict(list)
        for claim in passed_claims:
            section_key = _get_section_key(claim)
            section_entries[section_key].append(
                RenderedClaimEntry(
                    claim_id=claim.claim_id,
                    claim_type=_get_claim_type(claim),
                    statement=_get_statement(claim),
                    metrics=_get_metrics(claim),
                    evidence_count=len(claim.evidence_ids),
                    gate_status=claim.gate_status,
                )
            )

        sorted_section_keys = _sorted_section_keys(section_entries)
        sections = [
            RenderedSection(
                section_key=section_key,
                title=_section_title(section_key),
                claims=section_entries[section_key],
                claim_count=len(section_entries[section_key]),
            )
            for section_key in sorted_section_keys
        ]

        warnings = [f"Claim {claim.claim_id} failed: {claim.gate_status}" for claim in blocked_claims]

        markdown = _build_markdown(
            run_id=run_meta.run_id,
            round_no=round_no,
            rendered_at=rendered_at,
            total_claims=len(report_claims),
            passed_claims=len(passed_claims),
            sections=sections,
            warnings=warnings,
        )

        rendered_report = RenderedReport(
            run_id=run_meta.run_id,
            round_no=round_no,
            rendered_at=rendered_at,
            total_claims=len(report_claims),
            passed_claims=len(passed_claims),
            failed_claims=len(report_claims) - len(passed_claims),
            sections=sections,
            markdown=markdown,
        )

        if _is_legacy_stub_claims(report_claims):
            return {"event_refs": [], "warnings": warnings}

        event = SimulationEvent(
            event_id=str(uuid4()),
            run_id=run_meta.run_id,
            round_no=round_no,
            event_type="REPORT_RENDERED",
            timestamp=rendered_at,
            payload={
                "run_id": run_meta.run_id,
                "total_claims": rendered_report.total_claims,
                "passed_claims": rendered_report.passed_claims,
                "sections": len(rendered_report.sections),
                "rendered_report": rendered_report.model_dump(mode="json"),
            },
        )
        event_store.append(event)
        return {"event_refs": [event.event_id], "warnings": warnings}

    return node


def _sorted_section_keys(sections: dict[str, list[RenderedClaimEntry]]) -> list[str]:
    present_keys = set(sections)
    known_keys = [section for section in _SECTION_ORDER if section in present_keys]
    unknown_keys = sorted(section for section in present_keys if section not in _SECTION_ORDER)
    return [*known_keys, *unknown_keys]


def _section_title(section_key: str) -> str:
    return _SECTION_TITLES.get(section_key, section_key.replace("_", " ").title())


def _get_section_key(claim: ReportClaim) -> str:
    section = claim.claim_json.get("section")
    if isinstance(section, str) and section:
        return section
    return "summary"


def _get_claim_type(claim: ReportClaim) -> str:
    claim_type = claim.claim_json.get("type")
    return claim_type if isinstance(claim_type, str) and claim_type else "unknown"


def _get_statement(claim: ReportClaim) -> str:
    statement = claim.claim_json.get("statement")
    if isinstance(statement, str) and statement:
        return statement
    summary = claim.claim_json.get("summary")
    if isinstance(summary, str):
        return summary
    return ""


def _get_metrics(claim: ReportClaim) -> dict[str, object] | None:
    metrics = claim.claim_json.get("metrics")
    if not isinstance(metrics, dict):
        return None
    return {str(key): value for key, value in metrics.items()}


def _build_markdown(
    *,
    run_id: str,
    round_no: int,
    rendered_at: datetime,
    total_claims: int,
    passed_claims: int,
    sections: list[RenderedSection],
    warnings: list[str],
) -> str:
    lines = [
        "# Simulation Report",
        "",
        f"**Run**: {run_id}",
        f"**Round**: {round_no}",
        f"**Generated**: {rendered_at.isoformat()}",
        f"**Claims**: {passed_claims} passed / {total_claims} total",
    ]

    for section in sections:
        lines.extend(["", f"## {section.title}", ""])
        for claim in section.claims:
            lines.append(f"- {claim.statement} [evidence: {claim.evidence_count}]")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    return "\n".join(lines)


def _is_legacy_stub_claims(report_claims: list[ReportClaim]) -> bool:
    if len(report_claims) != 1:
        return False
    claim_json = report_claims[0].claim_json
    return claim_json == {"summary": "stub report"}
