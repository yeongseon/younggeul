# Web UI Deployment Guide

## Overview

younggeul ships a browser-based Web UI built on:

- **FastAPI** for HTTP routing and API endpoints
- **Jinja2** for server-side HTML templates
- **HTMX** for incremental page updates (run list/status polling, form-driven partial updates)

The UI is served by the same application package as the CLI (`younggeul_app_kr_seoul_apartment`) and can be started with `younggeul serve`.

## Architecture

The web app is created in `web/app.py` via `create_app()` and uses a FastAPI lifespan hook to initialize shared runtime components:

- `ThreadPoolExecutor(max_workers=2)` for background simulation execution
- `RunStore(base_dir=./output/runs)` for run metadata/report persistence
- `Jinja2Templates` for rendering pages and HTMX partials

Background simulations are submitted from UI/API handlers and executed through `run_simulation_background(...)`, while run status and report content are persisted under `./output/runs/<run_id>/`.
The app also enforces an in-flight submission cap via `YOUNGGEUL_WEB_MAX_INFLIGHT_RUNS` to avoid unbounded background queue growth.

## Pages

- **Dashboard** (`/ui`, `/ui/dashboard`): list all runs and quick status overview
- **Simulate** (`/ui/simulate`): start a simulation and receive HTMX run link/partial updates
- **Run Detail** (`/ui/simulate/{run_id}`): inspect a single run, including report/error status
- **Baseline** (`/ui/baseline`): submit snapshot ID and render baseline forecast results

## API Endpoints

### JSON API routes

| Method | Path | Description | Status |
|---|---|---|---|
| `GET` | `/health` | Service liveness/version check | Implemented |
| `POST` | `/simulate` | Create simulation run (async) | Implemented |
| `GET` | `/simulate` | List simulation runs | Implemented |
| `GET` | `/simulate/{run_id}` | Get single run metadata | Implemented |

### HTML UI routes

| Method | Path | Template/Response | Description |
|---|---|---|---|
| `GET` | `/ui` | `dashboard.html` | Dashboard entry page |
| `GET` | `/ui/dashboard` | `dashboard.html` | Dashboard alias |
| `GET` | `/ui/partials/runs` | `partials/run_list.html` | HTMX run list refresh |
| `GET` | `/ui/simulate` | `simulate.html` | Simulation form page |
| `POST` | `/ui/simulate` | `partials/simulate_result.html` | Start simulation from form |
| `GET` | `/ui/simulate/{run_id}` | `run_detail.html` | Run detail page |
| `GET` | `/ui/partials/runs/{run_id}` | `partials/run_status.html` | HTMX run status polling |
| `GET` | `/ui/baseline` | `baseline.html` | Baseline page |
| `POST` | `/ui/baseline` | `baseline.html` | Baseline form submit/result |

## Run locally

```bash
younggeul serve --host 0.0.0.0 --port 8000
# or
python -m younggeul_app_kr_seoul_apartment.cli serve --host 0.0.0.0 --port 8000
```

Then open: http://localhost:8000/ui

## Run with Docker Compose

Start web UI only:

```bash
docker compose --profile web up -d
```

Start web UI with observability stack:

```bash
docker compose --profile web-obs --profile obs up -d
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OTEL_ENABLED` | `false` (`web` profile) / `true` (`web-obs`) | Toggle OpenTelemetry metrics/tracing bootstrap |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | OTLP gRPC collector endpoint (e.g. `http://otel-collector:4317`) |
| `OTEL_EXPORTER_OTLP_INSECURE` | `false` | Use insecure OTLP gRPC transport when `true` |
| `YOUNGGEUL_ALLOWED_MODELS` | `stub,gpt-4o-mini` | Comma-separated allowlist for simulation model IDs |
| `YOUNGGEUL_WEB_MAX_INFLIGHT_RUNS` | `4` | Max number of `pending` + `running` web simulations accepted at once |

## Development notes

- App entrypoint: `younggeul_app_kr_seoul_apartment.web.app:create_app`
- Route modules live in `.../web/routes/` and are included in `create_app()`
- Template root: `.../web/templates/`
  - Top-level pages: `dashboard.html`, `simulate.html`, `run_detail.html`, `baseline.html`
  - HTMX partials: `partials/*.html`
- To add a new page:
  1. Add route handler(s) under `web/routes/pages.py` (or a new route module)
  2. Add/extend templates under `web/templates/`
  3. Include router in `web/app.py` if introducing a new module
  4. Add/extend tests in `apps/kr-seoul-apartment/tests/unit/test_web_*.py`
