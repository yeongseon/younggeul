# ADR-009: Use GitHub Models for simulation LLM access

## Status
Accepted

## Date
2026-04-20

## Context

The simulation workflow currently assumes a generic `LITELLM_API_KEY` and passes the selected `model_id` directly into LiteLLM. That design is serviceable for bring-your-own-provider integrations, but it is awkward for this repository's default automation path:

1. The project already runs on GitHub, so Actions always has a workflow token available.
2. GitHub Models offers a free experimentation tier, which lowers the barrier for trying the simulation with a real hosted model.
3. Requiring contributors to mint and distribute a separate generic LLM key adds setup friction for the common "run this in GitHub" case.

At the same time, the repo is pinned only to `litellm` without a first-class `github/...` provider contract in the installed LiteLLM 1.83 runtime. We therefore need a routing layer that preserves the public `github/...` model ids while still using LiteLLM as the transport abstraction.

## Decision

Simulation now accepts GitHub Models ids such as `github/openai/gpt-4o-mini` and routes them through LiteLLM using GitHub Models' OpenAI-compatible inference endpoint.

### 1. Public model id shape

- Callers keep using `github/...` ids at the CLI and web layer.
- `get_allowed_models()` now includes `github/openai/gpt-4o-mini` by default alongside `stub` and `gpt-4o-mini` for backward compatibility.

### 2. LiteLLM routing strategy

- The adapter detects `github/` prefixes before invoking `litellm.completion(...)`.
- Because the installed LiteLLM version does not provide a native GitHub provider route here, the adapter rewrites the outbound call to:
  - `custom_llm_provider="openai"`
  - `api_base="https://models.github.ai/inference"`
  - `model=<original model id without the leading github/>`
- Metrics and tracing still record the caller-facing model id and provider as `github`, so observability reflects the intended provider rather than the transport workaround.

### 3. Auth environment bridge

- `GH_MODELS_TOKEN` is the preferred explicit secret name for simulation.
- `GITHUB_TOKEN` remains supported because GitHub Actions injects it automatically.
- The adapter mirrors `GH_MODELS_TOKEN` into `GITHUB_TOKEN` when only the former is set, so local shells and Actions use one consistent auth path.
- Existing non-GitHub flows may still use `LITELLM_API_KEY`; this ADR does not remove that fallback.

### 4. Workflow changes

- `.github/workflows/simulation.yml` now exports `GH_MODELS_TOKEN: ${{ secrets.GITHUB_TOKEN }}`.
- The workflow requests `permissions:` for `contents: read` and `models: read` so the runtime token can access GitHub Models.
- The workflow runs the real `younggeul simulate` command instead of a placeholder echo.

## Rate limit notes

GitHub Models' free API usage is rate limited by request volume, daily quotas, token budgets per request, and concurrent requests. Those limits vary by model tier and account plan, and they are explicitly documented by GitHub as subject to change during preview. This is acceptable for the repository's simulation smoke workflow, but it means:

- repeated workflow_dispatch runs can hit transient 429-style throttling,
- heavier models may have materially tighter daily limits than lightweight models,
- teams that outgrow the free tier should expect to move either to paid GitHub Models usage or to an existing provider key path.

## Consequences

**Pros.**

- The default GitHub-hosted simulation path no longer requires a separate `LITELLM_API_KEY` secret.
- Contributors can try a real model from the CLI or Actions with a token name that matches GitHub's ecosystem.
- The adapter keeps LiteLLM as the single LLM transport abstraction, so the rest of the graph code stays unchanged.

**Cons.**

- The adapter now owns a small amount of provider-specific routing logic until LiteLLM's native GitHub provider support is dependable in this repo.
- Free-tier rate limits may be too small for frequent or large simulation runs.
- Not every catalog model name is guaranteed to behave identically through the OpenAI-compatible endpoint, so future model additions should be validated before being added to the default allow-list.

## Migration from generic `LITELLM_API_KEY`

1. For GitHub Models usage, stop depending on `LITELLM_API_KEY` and provide either `GH_MODELS_TOKEN` or `GITHUB_TOKEN`.
2. Use a GitHub Models id such as `github/openai/gpt-4o-mini` when invoking `younggeul simulate`.
3. Keep `LITELLM_API_KEY` only for non-GitHub model routes that still rely on LiteLLM's existing provider integrations.

## Related

- `apps/kr-seoul-apartment/src/younggeul_app_kr_seoul_apartment/simulation/llm/litellm_adapter.py` — provider routing and token bridge.
- `.github/workflows/simulation.yml` — workflow token wiring and `younggeul simulate` invocation.
- [README](../../README.md) — top-level setup note.
