# Contributing to younggeul

Thank you for your interest in contributing to the 영끌 시뮬레이터!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yeongseon/younggeul.git
   cd younggeul
   ```

2. Install dependencies:
   ```bash
   pip install uv
   make install
   ```

3. Run linters and tests:
   ```bash
   make lint
   make test
   ```

## Development Workflow

### TDD-First Rule

All implementation MUST follow Test-Driven Development:

1. Write failing tests first (commit: `test(scope): add tests for feature X`)
2. Implement the feature to make tests pass (commit: `feat(scope): implement feature X`)
3. Refactor if needed (commit: `refactor(scope): clean up feature X`)

PRs without tests will not be merged.

### Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

Types: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `ci`, `perf`

Scopes: `core`, `app/kr-seoul`, `eval`, `ci`, `docs`

### Branch Strategy

- `main` — stable, always passing CI
- Feature branches: `feat/M{milestone}-{issue-number}-{short-description}`
- Example: `feat/M1-13-bronze-schemas`

### Code Style

- Python 3.12+
- Formatter: `ruff format`
- Linter: `ruff check`
- Type checker: `mypy` (strict mode for `core/`)
- Line length: 120 characters

### Architecture Rules

Before contributing, please read:
- [ADR-004: LangGraph Usage Boundaries](docs/adr/004-langgraph-usage-boundaries.md) — No `add_messages`, no LLM in data plane
- [ADR-005: Evidence-Gated Reporting](docs/adr/005-evidence-gated-reporting.md) — JSON-first claims, then citation gate, then prose

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests first, then implement
3. Ensure `make lint` and `make test` pass
4. Fill out the PR template completely
5. Request review

## Reporting Issues

Use our issue templates:
- [Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml)
- [Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml)
- [ADR Proposal](.github/ISSUE_TEMPLATE/adr_proposal.yml)
