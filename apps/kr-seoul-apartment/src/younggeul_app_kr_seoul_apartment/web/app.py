from __future__ import annotations

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from ..simulation.metrics import init_metrics, shutdown_metrics
from ..simulation.tracing import init_tracing, shutdown_tracing

from .run_store import RunStore
from .routes.baseline import router as baseline_router
from .routes.health import router as health_router
from .routes.pages import router as pages_router
from .routes.simulate import router as simulate_router
from .routes.snapshot import router as snapshot_router


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_tracing()
    init_metrics()
    executor = ThreadPoolExecutor(max_workers=2)
    app.state.executor = executor
    app.state.run_store = RunStore(base_dir=Path("./output/runs"))
    app.state.templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    try:
        yield
    finally:
        try:
            shutdown_tracing()
        except Exception:
            pass
        try:
            shutdown_metrics()
        except Exception:
            pass
        executor.shutdown(wait=True)


def create_app() -> FastAPI:
    app = FastAPI(title="영끌 시뮬레이터", version="0.2.0", lifespan=app_lifespan)
    app.include_router(health_router)
    app.include_router(simulate_router)
    app.include_router(snapshot_router)
    app.include_router(baseline_router)
    app.include_router(pages_router)
    return app
