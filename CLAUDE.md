# CLAUDE.md — monolith

## Project Overview

Blockchain anomaly detector and bug report engine for EVE Frontier

## Current State

- **Version**: 0.2.0
- **Language**: Python
- **Files**: 136 across 4 languages
- **Lines**: 18,699

## Architecture

```
monolith/
├── .github/
│   └── workflows/
├── backend/
│   ├── alerts/
│   ├── api/
│   ├── db/
│   ├── detection/
│   ├── ingestion/
│   └── reports/
├── contracts/
│   └── sources/
├── docs/
│   └── chain-samples/
├── frontend/
│   ├── .vercel/
│   ├── public/
│   └── src/
├── tests/
│   ├── test_alerts/
│   ├── test_api/
│   ├── test_db/
│   ├── test_detection/
│   ├── test_ingestion/
│   └── test_reports/
├── .dockerignore
├── .env.example
├── .gitignore
├── CLAUDE.md
├── Dockerfile
├── README.md
├── demo_seed.py
├── docker-compose.yml
├── explore_chain.py
├── fly.toml
├── pyproject.toml
├── test_bug_report_e2e.py
```

## Tech Stack

- **Language**: Python, JavaScript, HTML, CSS
- **Framework**: fastapi
- **Package Manager**: pip
- **Linters**: ruff
- **Formatters**: ruff
- **Test Frameworks**: pytest
- **Runtime**: Docker
- **CI/CD**: GitHub Actions

## Coding Standards

- **Naming**: snake_case
- **Quote Style**: double quotes
- **Type Hints**: present
- **Docstrings**: google style
- **Imports**: absolute
- **Path Handling**: pathlib
- **Line Length (p95)**: 78 characters
- **Error Handling**: Custom exception classes present

## Common Commands

```bash
# test
pytest tests/ -v
# lint
ruff check src/ tests/
# format
ruff format src/ tests/

# docker CMD
["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Anti-Patterns (Do NOT Do)

- Do NOT commit secrets, API keys, or credentials
- Do NOT skip writing tests for new code
- Do NOT use `os.path` — use `pathlib.Path` everywhere
- Do NOT use bare `except:` — catch specific exceptions
- Do NOT use mutable default arguments
- Do NOT use `print()` for logging — use the `logging` module
- Do NOT hardcode secrets in Dockerfiles — use environment variables
- Do NOT use `latest` tag — pin specific versions
- Do NOT use synchronous database calls in async endpoints
- Do NOT return raw dicts — use Pydantic response models

## Dependencies

### Core
- fastapi
- uvicorn

### Dev
- pytest
- pytest-asyncio
- pytest-cov
- ruff
- respx

## Domain Context

### Key Models/Classes
- `Anomaly`
- `AnomalyStatus`
- `AssemblyChecker`
- `BaseChecker`
- `BulkStatusRequest`
- `ChainReader`
- `ContinuityChecker`
- `DetectionEngine`
- `EconomicChecker`
- `EventProcessor`
- `FakeSettings`
- `KillmailChecker`
- `PodChecker`
- `PodVerifier`
- `SequenceChecker`

### Domain Terms
- AI
- Anomaly Detail
- Anomaly Feed
- Blockchain Integrity Monitor
- Bug Report
- Bug Reports Each
- CCP
- CLAUDE
- CRITICAL
- Configuration All

### API Endpoints
- `/admin/errors`
- `/anomalies`
- `/anomalies/{anomaly_id}`
- `/api/health`
- `/bulk/status`
- `/generate`
- `/health`
- `/ledger`
- `/map`
- `/nexus/webhook`
- `/resolve`
- `/stats`
- `/{anomaly_id}`
- `/{anomaly_id}/status`
- `/{full_path:path}`

### Enums/Constants
- `CHAIN_RPC`
- `CONFIRMED`
- `FALSE_POSITIVE`
- `FTS`
- `GITHUB_API`
- `GRAPHQL`
- `INDEXES`
- `INVESTIGATING`
- `PACKAGE_ID`
- `RESOLVED`

## AI Skills

**Installed**: 122 skills in `~/.claude/skills/`
- `a11y`, `accessibility-checker`, `agent-teams-orchestrator`, `align-debug`, `api-client`, `api-docs`, `api-tester`, `apple-dev-best-practices`, `arch`, `backup`, `brand-voice-architect`, `build`, `changelog`, `ci`, `cicd-pipeline`
- ... and 107 more

**Recommended bundles**: `api-integration`, `full-stack-dev`, `website-builder`

**Recommended skills** (not yet installed):
- `api-integration`
- `full-stack-dev`
- `website-builder`

## Git Conventions

- Commit messages: Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)
- Branch naming: `feat/description`, `fix/description`
- Run tests before committing
