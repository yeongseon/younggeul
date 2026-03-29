from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import validate_max_rounds, validate_model_id
from ..run_store import RunMeta, RunStore
from ..services import forecast_baseline_service, resolve_snapshot_service, run_simulation_background

router = APIRouter(prefix="/ui", tags=["pages"])


class _AppState(Protocol):
    templates: Jinja2Templates
    run_store: object
    executor: ThreadPoolExecutor


def _state(request: Request) -> _AppState:
    return cast(_AppState, request.app.state)


def _templates(request: Request) -> Jinja2Templates:
    return _state(request).templates


def _badge_class(status_name: str) -> str:
    mapping = {
        "pending": "badge-pending",
        "running": "badge-running",
        "completed": "badge-completed",
        "failed": "badge-failed",
    }
    return mapping.get(status_name, "badge-pending")


def _run_report(run_store: object, run_id: str) -> str | None:
    typed_run_store = cast("RunStoreLike", run_store)
    report_path = typed_run_store.base_dir / run_id / "report.md"
    if not report_path.exists():
        return None
    return report_path.read_text(encoding="utf-8")


def _run_context(run_store: object, run_id: str) -> dict[str, object]:
    typed_run_store = cast("RunStoreLike", run_store)
    run_meta = typed_run_store.get_run(run_id)
    if run_meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    report_text: str | None = None
    if run_meta.status == "completed":
        report_text = _run_report(typed_run_store, run_id)

    return {
        "run": run_meta,
        "badge_class": _badge_class(run_meta.status),
        "report_text": report_text,
        "is_polling": run_meta.status in {"pending", "running"},
    }


class RunStoreLike(Protocol):
    base_dir: Path

    def get_run(self, run_id: str) -> RunMeta | None: ...

    def list_runs(self) -> list[RunMeta]: ...

    def create_run(self, query: str) -> str: ...

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        error: str | None = None,
        report: str | None = None,
    ) -> None: ...


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    run_store = cast(RunStoreLike, _state(request).run_store)
    runs: list[RunMeta] = run_store.list_runs()
    context = {"request": request, "runs": runs}
    return _templates(request).TemplateResponse(request, "dashboard.html", context)


@router.get("/partials/runs", response_class=HTMLResponse)
async def run_list_partial(request: Request) -> HTMLResponse:
    run_store = cast(RunStoreLike, _state(request).run_store)
    runs: list[RunMeta] = run_store.list_runs()
    context = {"request": request, "runs": runs}
    return _templates(request).TemplateResponse(request, "partials/run_list.html", context)


@router.get("/simulate", response_class=HTMLResponse)
async def simulate_page(request: Request) -> HTMLResponse:
    return _templates(request).TemplateResponse(request, "simulate.html", {"request": request})


@router.post("/simulate", response_class=HTMLResponse)
async def simulate_start(request: Request) -> HTMLResponse:
    form_payload = _parse_form_payload(await request.body())
    query = form_payload.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query is required")

    max_rounds_raw = form_payload.get("max_rounds", "3")
    try:
        max_rounds = int(max_rounds_raw)
    except ValueError:
        max_rounds = 3
    model_id = form_payload.get("model_id", "stub") or "stub"

    try:
        validate_model_id(model_id)
        validate_max_rounds(max_rounds)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    run_store = cast(RunStoreLike, _state(request).run_store)
    executor = _state(request).executor

    run_id = run_store.create_run(query)
    try:
        _ = executor.submit(
            run_simulation_background,
            cast(RunStore, run_store),
            run_id,
            query,
            max_rounds,
            model_id,
        )
    except Exception as exc:
        run_store.update_status(run_id, "failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    context = {
        "request": request,
        "run_id": run_id,
        "run_url": f"/ui/simulate/{run_id}",
    }
    return _templates(request).TemplateResponse(request, "partials/simulate_result.html", context)


@router.get("/simulate/{run_id}", response_class=HTMLResponse)
async def run_detail_page(request: Request, run_id: str) -> HTMLResponse:
    run_store = cast(RunStoreLike, _state(request).run_store)
    context = {"request": request, **_run_context(run_store, run_id)}
    return _templates(request).TemplateResponse(request, "run_detail.html", context)


@router.get("/partials/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_partial(request: Request, run_id: str) -> HTMLResponse:
    run_store = cast(RunStoreLike, _state(request).run_store)
    context = {"request": request, **_run_context(run_store, run_id)}
    return _templates(request).TemplateResponse(request, "partials/run_status.html", context)


@router.get("/baseline", response_class=HTMLResponse)
async def baseline_page(request: Request) -> HTMLResponse:
    context: dict[str, object] = {"request": request, "snapshot_id": "", "results": [], "error": None}
    return _templates(request).TemplateResponse(request, "baseline.html", context)


@router.post("/baseline", response_class=HTMLResponse)
async def baseline_run(request: Request) -> HTMLResponse:
    form_payload = _parse_form_payload(await request.body())
    snapshot_id = form_payload.get("snapshot_id", "").strip()

    context: dict[str, object] = {
        "request": request,
        "snapshot_id": snapshot_id,
        "results": [],
        "error": None,
    }

    if not snapshot_id:
        context["error"] = "snapshot_id is required"
        return _templates(request).TemplateResponse(request, "baseline.html", context)

    try:
        _, metrics = resolve_snapshot_service(snapshot_id, Path("./output/snapshots"))
        forecasts = forecast_baseline_service(metrics)
        context["results"] = forecasts
    except (FileNotFoundError, ValueError) as exc:
        context["error"] = str(exc)

    return _templates(request).TemplateResponse(request, "baseline.html", context)


def _parse_form_payload(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}
