from __future__ import annotations

from fastapi import APIRouter

from ...runtime_version import get_runtime_version

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": get_runtime_version()}
