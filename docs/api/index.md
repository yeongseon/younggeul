# API Reference

Auto-generated reference documentation for the **younggeul** public API,
built from source code docstrings using
[mkdocstrings](https://mkdocstrings.github.io/).

## Packages

### Core (`younggeul_core`)

Platform-agnostic schemas, protocols, and utilities.

| Module | Description |
|--------|-------------|
| [State Schemas](core-state.md) | Bronze, Silver, Gold, and Simulation data models |
| [Evidence Schemas](core-evidence.md) | Evidence records, claim records, and gate results |
| [Connectors](core-connectors.md) | Connector protocol, retry, rate limiting, hashing |
| [Storage](core-storage.md) | Immutable snapshot manifest and table entries |

### App (`younggeul_app_kr_seoul_apartment`)

Korea-specific application implementing the Seoul apartment market simulator.

| Module | Description |
|--------|-------------|
| [CLI](app-cli.md) | Click-based command-line interface |
| [Pipeline](app-pipeline.md) | Data pipeline orchestration and snapshot management |
| [Connectors](app-connectors.md) | MOLIT, BOK, KOSTAT government API connectors |
| [Transforms](app-transforms.md) | Bronze → Silver → Gold data transformations |
| [Simulation](app-simulation.md) | LangGraph simulation nodes, policies, and schemas |
