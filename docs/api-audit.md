# Docstring Coverage Audit Report

**Generated**: 2026-03-29
**Total files scanned**: 78
**Total public symbols**: 289

## Summary

| Metric | Count |
|--------|-------|
| ✅ Full docstring | 46 |
| ⚠️ Partial docstring | 20 |
| ❌ Missing docstring | 223 |
| **Total** | **289** |
| **Coverage (full)** | **15.9%** |
| **Coverage (full+partial)** | **22.8%** |

## Per-Module Breakdown

### Core (`younggeul_core`)

| Module | Total | ✅ Full | ⚠️ Partial | ❌ Missing | Coverage |
|--------|-------|---------|------------|------------|----------|
| `younggeul_core` | 1 | 1 | 0 | 0 | 100% |
| `core.agents` | 1 | 1 | 0 | 0 | 100% |
| `core.connectors` | 1 | 1 | 0 | 0 | 100% |
| `core.connectors.hashing` | 2 | 2 | 0 | 0 | 100% |
| `core.connectors.manifest` | 2 | 2 | 0 | 0 | 100% |
| `core.connectors.protocol` | 4 | 4 | 0 | 0 | 100% |
| `core.connectors.rate_limit` | 5 | 4 | 1 | 0 | 80% |
| `core.connectors.retry` | 4 | 4 | 0 | 0 | 100% |
| `core.evidence` | 1 | 0 | 0 | 1 | 0% |
| `core.evidence.schemas` | 9 | 0 | 0 | 9 | 0% |
| `core.evidence.sql` | 1 | 0 | 0 | 1 | 0% |
| `core.runtime` | 1 | 1 | 0 | 0 | 100% |
| `core.state` | 1 | 0 | 0 | 1 | 0% |
| `core.state.bronze` | 7 | 0 | 0 | 7 | 0% |
| `core.state.gold` | 5 | 0 | 0 | 5 | 0% |
| `core.state.silver` | 7 | 0 | 0 | 7 | 0% |
| `core.state.simulation` | 19 | 0 | 0 | 19 | 0% |
| `core.storage` | 1 | 1 | 0 | 0 | 100% |
| `core.storage.snapshot` | 11 | 0 | 0 | 11 | 0% |

### App (`younggeul_app_kr_seoul_apartment`)

| Module | Total | ✅ Full | ⚠️ Partial | ❌ Missing | Coverage |
|--------|-------|---------|------------|------------|----------|
| `younggeul_app_kr_seoul_apartment` | 1 | 1 | 0 | 0 | 100% |
| `app.canonical` | 1 | 1 | 0 | 0 | 100% |
| `app.cli` | 10 | 0 | 0 | 10 | 0% |
| `app.connectors` | 1 | 1 | 0 | 0 | 100% |
| `app.connectors.bok` | 4 | 3 | 1 | 0 | 75% |
| `app.connectors.kostat` | 4 | 3 | 1 | 0 | 75% |
| `app.connectors.molit` | 4 | 3 | 1 | 0 | 75% |
| `app.entity_resolution` | 1 | 1 | 0 | 0 | 100% |
| `app.eval` | 1 | 1 | 0 | 0 | 100% |
| `app.features` | 1 | 1 | 0 | 0 | 100% |
| `app.forecaster` | 3 | 0 | 0 | 3 | 0% |
| `app.pipeline` | 5 | 3 | 1 | 1 | 60% |
| `app.policies` | 1 | 1 | 0 | 0 | 100% |
| `app.reports` | 1 | 1 | 0 | 0 | 100% |
| `app.simulation` | 1 | 1 | 0 | 0 | 100% |
| `app.simulation.domain` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.domain.gu_resolver` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.domain.shock_catalog` | 3 | 0 | 0 | 3 | 0% |
| `app.simulation.event_store` | 13 | 0 | 0 | 13 | 0% |
| `app.simulation.events` | 8 | 2 | 5 | 1 | 25% |
| `app.simulation.evidence` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.evidence.store` | 16 | 2 | 4 | 10 | 12% |
| `app.simulation.graph` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.graph_state` | 5 | 0 | 0 | 5 | 0% |
| `app.simulation.llm` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.llm.litellm_adapter` | 5 | 0 | 0 | 5 | 0% |
| `app.simulation.llm.ports` | 4 | 0 | 1 | 3 | 0% |
| `app.simulation.nodes` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.nodes.citation_gate_node` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.continue_gate` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.evidence_builder` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.intake_planner` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.participant_decider` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.report_renderer` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.report_writer` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.round_resolver` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.round_summarizer` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.nodes.scenario_builder` | 4 | 0 | 0 | 4 | 0% |
| `app.simulation.nodes.world_initializer` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.policies` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.policies.heuristic` | 11 | 0 | 0 | 11 | 0% |
| `app.simulation.policies.protocol` | 3 | 0 | 1 | 2 | 0% |
| `app.simulation.policies.registry` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.ports` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.ports.snapshot_reader` | 6 | 0 | 3 | 3 | 0% |
| `app.simulation.replay` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.replay.engine` | 6 | 0 | 0 | 6 | 0% |
| `app.simulation.schemas` | 1 | 0 | 0 | 1 | 0% |
| `app.simulation.schemas.intake` | 2 | 0 | 0 | 2 | 0% |
| `app.simulation.schemas.participant_roster` | 3 | 0 | 0 | 3 | 0% |
| `app.simulation.schemas.report` | 4 | 0 | 0 | 4 | 0% |
| `app.simulation.schemas.round` | 7 | 0 | 0 | 7 | 0% |
| `app.simulation.tracing` | 4 | 0 | 0 | 4 | 0% |
| `app.snapshot` | 3 | 0 | 0 | 3 | 0% |
| `app.transforms` | 1 | 0 | 0 | 1 | 0% |
| `app.transforms.gold_district` | 2 | 0 | 0 | 2 | 0% |
| `app.transforms.gold_enrichment` | 2 | 0 | 1 | 1 | 0% |
| `app.transforms.silver_apt` | 12 | 0 | 0 | 12 | 0% |
| `app.transforms.silver_macro` | 9 | 0 | 0 | 9 | 0% |

## Gap List (Missing & Partial Docstrings)

### Priority: Missing Docstrings

| File | Symbol | Kind | Line |
|------|--------|------|------|
| `src/younggeul_core/evidence/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_core/evidence/schemas.py` | `(module)` | module | L1 |
| `src/younggeul_core/evidence/schemas.py` | `EvidenceRecord` | class | L11 |
| `src/younggeul_core/evidence/schemas.py` | `EvidenceRecord.validate_evidence_id_uuid` | method | L27 |
| `src/younggeul_core/evidence/schemas.py` | `EvidenceRecord.validate_sha256_hex` | method | L33 |
| `src/younggeul_core/evidence/schemas.py` | `ClaimRecord` | class | L39 |
| `src/younggeul_core/evidence/schemas.py` | `ClaimRecord.validate_uuid` | method | L54 |
| `src/younggeul_core/evidence/schemas.py` | `ClaimRecord.validate_repair_count` | method | L60 |
| `src/younggeul_core/evidence/schemas.py` | `GateResult` | class | L66 |
| `src/younggeul_core/evidence/schemas.py` | `GateResult.validate_claim_id_uuid` | method | L77 |
| `src/younggeul_core/evidence/sql.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/bronze.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/bronze.py` | `BronzeIngestMeta` | class | L7 |
| `src/younggeul_core/state/bronze.py` | `BronzeAptTransaction` | class | L15 |
| `src/younggeul_core/state/bronze.py` | `BronzeInterestRate` | class | L52 |
| `src/younggeul_core/state/bronze.py` | `BronzeMigration` | class | L61 |
| `src/younggeul_core/state/bronze.py` | `BronzeLegalDistrictCode` | class | L73 |
| `src/younggeul_core/state/bronze.py` | `BronzeIngestManifest` | class | L81 |
| `src/younggeul_core/state/gold.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/gold.py` | `GoldDistrictMonthlyMetrics` | class | L7 |
| `src/younggeul_core/state/gold.py` | `GoldComplexMonthlyMetrics` | class | L29 |
| `src/younggeul_core/state/gold.py` | `BaselineForecast` | class | L43 |
| `src/younggeul_core/state/gold.py` | `BaselineForecast.validate_direction_confidence` | method | L58 |
| `src/younggeul_core/state/silver.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/silver.py` | `SilverDataQualityScore` | class | L8 |
| `src/younggeul_core/state/silver.py` | `SilverDataQualityScore.validate_score_range` | method | L17 |
| `src/younggeul_core/state/silver.py` | `SilverAptTransaction` | class | L23 |
| `src/younggeul_core/state/silver.py` | `SilverInterestRate` | class | L47 |
| `src/younggeul_core/state/silver.py` | `SilverMigration` | class | L57 |
| `src/younggeul_core/state/silver.py` | `SilverComplexBridge` | class | L70 |
| `src/younggeul_core/state/simulation.py` | `(module)` | module | L1 |
| `src/younggeul_core/state/simulation.py` | `RunMeta` | class | L7 |
| `src/younggeul_core/state/simulation.py` | `SnapshotRef` | class | L17 |
| `src/younggeul_core/state/simulation.py` | `SnapshotRef.validate_dataset_snapshot_id` | method | L26 |
| `src/younggeul_core/state/simulation.py` | `Shock` | class | L34 |
| `src/younggeul_core/state/simulation.py` | `Shock.validate_magnitude` | method | L44 |
| `src/younggeul_core/state/simulation.py` | `ScenarioSpec` | class | L50 |
| `src/younggeul_core/state/simulation.py` | `ScenarioSpec.validate_target_period` | method | L60 |
| `src/younggeul_core/state/simulation.py` | `SegmentState` | class | L66 |
| `src/younggeul_core/state/simulation.py` | `SegmentState.validate_sentiment_index` | method | L79 |
| `src/younggeul_core/state/simulation.py` | `SegmentState.validate_supply_pressure` | method | L86 |
| `src/younggeul_core/state/simulation.py` | `ParticipantState` | class | L92 |
| `src/younggeul_core/state/simulation.py` | `ParticipantState.validate_risk_tolerance` | method | L104 |
| `src/younggeul_core/state/simulation.py` | `ActionProposal` | class | L110 |
| `src/younggeul_core/state/simulation.py` | `ActionProposal.validate_confidence` | method | L123 |
| `src/younggeul_core/state/simulation.py` | `RoundOutcome` | class | L129 |
| `src/younggeul_core/state/simulation.py` | `ReportClaim` | class | L139 |
| `src/younggeul_core/state/simulation.py` | `ReportClaim.validate_repair_count` | method | L150 |
| `src/younggeul_core/state/simulation.py` | `SimulationState` | class | L156 |
| `src/younggeul_core/storage/snapshot.py` | `(module)` | module | L1 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotTableEntry` | class | L11 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotTableEntry.validate_table_hash` | method | L23 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest` | class | L29 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.validate_dataset_snapshot_id` | method | L42 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.table_hashes` | method | L49 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.record_counts` | method | L54 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.total_records` | method | L59 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.validate_integrity` | method | L62 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.get_table` | method | L66 |
| `src/younggeul_core/storage/snapshot.py` | `SnapshotManifest.compute_snapshot_id` | method | L73 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `main` | function | L194 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `ingest_command` | function | L207 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `snapshot_group` | function | L247 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `snapshot_publish_command` | function | L264 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `snapshot_list_command` | function | L297 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `baseline_command` | function | L364 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `simulate_command` | function | L404 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `report_command` | function | L440 |
| `src/younggeul_app_kr_seoul_apartment/cli.py` | `eval_command` | function | L456 |
| `src/younggeul_app_kr_seoul_apartment/forecaster.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/forecaster.py` | `forecast_baseline` | function | L23 |
| `src/younggeul_app_kr_seoul_apartment/forecaster.py` | `generate_baseline_report` | function | L100 |
| `src/younggeul_app_kr_seoul_apartment/pipeline.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/gu_resolver.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/gu_resolver.py` | `resolve_gu_codes` | function | L33 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/shock_catalog.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/shock_catalog.py` | `normalize_shock_key` | function | L74 |
| `src/younggeul_app_kr_seoul_apartment/simulation/domain/shock_catalog.py` | `expand_shock` | function | L83 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore` | class | L11 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore.append` | method | L16 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore.get_events` | method | L20 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore.get_events_by_type` | method | L25 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore.count` | method | L28 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `InMemoryEventStore.clear` | method | L32 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore` | class | L37 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore.append` | method | L46 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore.get_events` | method | L52 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore.get_events_by_type` | method | L68 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore.count` | method | L71 |
| `src/younggeul_app_kr_seoul_apartment/simulation/event_store.py` | `FileEventStore.clear` | method | L79 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceRecord` | class | L9 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceStore` | class | L20 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore` | class | L34 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.add` | method | L38 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.get` | method | L43 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.get_all` | method | L46 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.get_by_kind` | method | L49 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.get_by_subject` | method | L52 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `InMemoryEvidenceStore.count` | method | L59 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph.py` | `build_simulation_graph` | function | L54 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph_state.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph_state.py` | `SimulationGraphState` | class | L23 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph_state.py` | `seed_graph_state` | function | L75 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph_state.py` | `to_simulation_state` | function | L91 |
| `src/younggeul_app_kr_seoul_apartment/simulation/graph_state.py` | `validate_initialized_state` | function | L103 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` | `StructuredLLMTransportError` | class | L14 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` | `StructuredLLMResponseError` | class | L18 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` | `LiteLLMStructuredLLM` | class | L22 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` | `LiteLLMStructuredLLM.generate_structured` | method | L27 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/ports.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/ports.py` | `LLMMessage` | class | L11 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/ports.py` | `StructuredLLM` | class | L16 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/citation_gate_node.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/citation_gate_node.py` | `make_citation_gate_node` | function | L35 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/continue_gate.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/continue_gate.py` | `should_continue` | function | L8 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/evidence_builder.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/evidence_builder.py` | `make_evidence_builder_node` | function | L11 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/intake_planner.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/intake_planner.py` | `make_intake_planner_node` | function | L28 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/participant_decider.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/participant_decider.py` | `make_participant_decider_node` | function | L71 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/report_renderer.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/report_renderer.py` | `make_report_renderer_node` | function | L26 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/report_writer.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/report_writer.py` | `make_report_writer_node` | function | L52 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/round_resolver.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/round_resolver.py` | `make_round_resolver_node` | function | L50 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/round_summarizer.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/round_summarizer.py` | `make_round_summarizer_node` | function | L11 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/scenario_builder.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/scenario_builder.py` | `ScenarioSelection` | class | L25 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/scenario_builder.py` | `compute_max_rounds` | function | L33 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/scenario_builder.py` | `make_scenario_builder_node` | function | L181 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/world_initializer.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/nodes/world_initializer.py` | `make_world_initializer_node` | function | L158 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `BuyerPolicy` | class | L39 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `BuyerPolicy.decide` | method | L40 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `InvestorPolicy` | class | L64 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `InvestorPolicy.decide` | method | L65 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `TenantPolicy` | class | L98 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `TenantPolicy.decide` | method | L99 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `LandlordPolicy` | class | L109 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `LandlordPolicy.decide` | method | L110 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `BrokerPolicy` | class | L132 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/heuristic.py` | `BrokerPolicy.decide` | method | L133 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/protocol.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/protocol.py` | `ParticipantPolicy` | class | L13 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/registry.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/registry.py` | `get_default_policy` | function | L15 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `SnapshotCoverage` | class | L11 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `SnapshotReader` | class | L22 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `ReplayResult` | class | L15 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `ReplayContext` | class | L26 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `ReplayError` | class | L30 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `ReplayEngine` | class | L197 |
| `src/younggeul_app_kr_seoul_apartment/simulation/replay/engine.py` | `ReplayEngine.replay` | method | L201 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/intake.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/intake.py` | `IntakePlan` | class | L8 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/participant_roster.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/participant_roster.py` | `RoleBucketSpec` | class | L8 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/participant_roster.py` | `ParticipantRosterSpec` | class | L22 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/report.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/report.py` | `RenderedClaimEntry` | class | L8 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/report.py` | `RenderedSection` | class | L17 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/report.py` | `RenderedReport` | class | L24 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `DecisionContext` | class | L12 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `SegmentDelta` | class | L21 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `SegmentDelta.validate_price_change_pct` | method | L30 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `ParticipantDelta` | class | L36 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `RoundResolvedPayload` | class | L44 |
| `src/younggeul_app_kr_seoul_apartment/simulation/schemas/round.py` | `validate_v01_action` | function | L52 |
| `src/younggeul_app_kr_seoul_apartment/simulation/tracing.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/simulation/tracing.py` | `init_tracing` | function | L18 |
| `src/younggeul_app_kr_seoul_apartment/simulation/tracing.py` | `get_tracer` | function | L44 |
| `src/younggeul_app_kr_seoul_apartment/simulation/tracing.py` | `trace_node` | function | L49 |
| `src/younggeul_app_kr_seoul_apartment/snapshot.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/snapshot.py` | `publish_snapshot` | function | L49 |
| `src/younggeul_app_kr_seoul_apartment/snapshot.py` | `resolve_snapshot` | function | L86 |
| `src/younggeul_app_kr_seoul_apartment/transforms/__init__.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/transforms/gold_district.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/transforms/gold_district.py` | `aggregate_district_monthly` | function | L54 |
| `src/younggeul_app_kr_seoul_apartment/transforms/gold_enrichment.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `parse_deal_amount` | function | L39 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `parse_deal_date` | function | L52 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `parse_int` | function | L64 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `parse_decimal` | function | L76 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `derive_gu_code` | function | L88 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `derive_gu_name` | function | L94 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `is_cancelled` | function | L100 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `generate_transaction_id` | function | L106 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `compute_quality_score` | function | L122 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `normalize_apt_transaction` | function | L186 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_apt.py` | `normalize_batch` | function | L243 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `(module)` | module | L1 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `parse_date` | function | L13 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `parse_decimal_2dp` | function | L25 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `parse_count` | function | L37 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `build_period` | function | L49 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `normalize_interest_rate` | function | L62 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `normalize_migration` | function | L84 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `normalize_interest_rate_batch` | function | L115 |
| `src/younggeul_app_kr_seoul_apartment/transforms/silver_macro.py` | `normalize_migration_batch` | function | L124 |

### Lower Priority: Partial Docstrings (missing Args/Returns sections)

| File | Symbol | Kind | Line |
|------|--------|------|------|
| `src/younggeul_core/connectors/rate_limit.py` | `RateLimiter.min_interval` | method | L26 |
| `src/younggeul_app_kr_seoul_apartment/connectors/bok.py` | `BokInterestRateConnector.fetch` | method | L173 |
| `src/younggeul_app_kr_seoul_apartment/connectors/kostat.py` | `KostatMigrationConnector.fetch` | method | L194 |
| `src/younggeul_app_kr_seoul_apartment/connectors/molit.py` | `MolitAptConnector.fetch` | method | L173 |
| `src/younggeul_app_kr_seoul_apartment/pipeline.py` | `run_pipeline` | function | L44 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `EventStore.append` | method | L26 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `EventStore.get_events` | method | L31 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `EventStore.get_events_by_type` | method | L36 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `EventStore.count` | method | L41 |
| `src/younggeul_app_kr_seoul_apartment/simulation/events.py` | `EventStore.clear` | method | L46 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceStore.add` | method | L21 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceStore.get` | method | L23 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceStore.get_by_kind` | method | L27 |
| `src/younggeul_app_kr_seoul_apartment/simulation/evidence/store.py` | `EvidenceStore.get_by_subject` | method | L29 |
| `src/younggeul_app_kr_seoul_apartment/simulation/llm/ports.py` | `StructuredLLM.generate_structured` | method | L17 |
| `src/younggeul_app_kr_seoul_apartment/simulation/policies/protocol.py` | `ParticipantPolicy.decide` | method | L14 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `SnapshotReader.get_coverage` | method | L23 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `SnapshotReader.get_latest_metrics` | method | L25 |
| `src/younggeul_app_kr_seoul_apartment/simulation/ports/snapshot_reader.py` | `SnapshotReader.get_baseline_forecasts` | method | L31 |
| `src/younggeul_app_kr_seoul_apartment/transforms/gold_enrichment.py` | `enrich_district_monthly_trends` | function | L28 |
