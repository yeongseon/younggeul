from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..run_store import RunMeta
from ..services import run_simulation_background

router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    query: str
    max_rounds: int = Field(default=3)
    model_id: str = Field(default="stub")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_simulation_run(request: Request, payload: SimulateRequest) -> dict[str, str]:
    run_store = request.app.state.run_store
    executor = request.app.state.executor

    run_id = run_store.create_run(payload.query)
    executor.submit(
        run_simulation_background,
        run_store,
        run_id,
        payload.query,
        payload.max_rounds,
        payload.model_id,
    )
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
