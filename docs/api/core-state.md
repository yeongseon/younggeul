# State Schemas

Data models for the Bronze → Silver → Gold data pipeline and simulation state.

## Bronze Layer

Raw ingested data — all fields are `str | None` for conservative parsing.

::: younggeul_core.state.bronze

## Silver Layer

Typed and validated data with proper Python types.

::: younggeul_core.state.silver

## Gold Layer

Aggregated features at district-monthly granularity.

::: younggeul_core.state.gold

## Simulation State

Schemas for simulation runs, scenarios, participants, and outcomes.

::: younggeul_core.state.simulation
