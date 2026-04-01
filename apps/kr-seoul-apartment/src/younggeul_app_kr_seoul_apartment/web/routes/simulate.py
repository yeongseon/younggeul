from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from ..config import get_allowed_models, get_max_inflight_runs, validate_max_rounds, validate_model_id
from ..run_store import RunCapacityExceededError, RunMeta
from ..services import run_simulation_background

router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    query: str
    max_rounds: int = Field(default=3)
    model_id: str = Field(
        default="stub",
        description=f"Allowed model IDs: {', '.join(get_allowed_models())}",
    )

    @model_validator(mode="after")
    def validate_inputs(self) -> SimulateRequest:
        validate_model_id(self.model_id)
        validate_max_rounds(self.max_rounds)
        return self


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_simulation_run(request: Request, payload: SimulateRequest) -> dict[str, str]:
    run_store = request.app.state.run_store
    executor = request.app.state.executor

    try:
        run_id = run_store.create_run(payload.query, max_inflight_runs=get_max_inflight_runs())
        executor.submit(
            run_simulation_background,
            run_store,
            run_id,
            payload.query,
            payload.max_rounds,
            payload.model_id,
        )
    except RunCapacityExceededError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        if "run_id" in locals():
            run_store.update_status(run_id, "failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "pending"}


@router.get("/{run_id}")
async def get_simulation_run(request: Request, run_id: str) -> dict[str, Any]:
    run_store = request.app.state.run_store
    run_meta = run_store.get_run(run_id)
    if run_meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    result: dict[str, Any] = run_meta.model_dump(mode="json")
    return result


@router.get("")
async def list_simulation_runs(request: Request) -> list[dict[str, Any]]:
    run_store = request.app.state.run_store
    runs: list[RunMeta] = run_store.list_runs()
    return [run.model_dump(mode="json") for run in runs]
