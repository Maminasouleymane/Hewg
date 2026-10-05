# Hewg — your dependency blacksmith

Hewg analyzes the migration path between two versions of an npm package. It gathers release notes and
changelogs, sends them to an LLM, and returns a structured guide: breaking changes, deprecations, new
features, and concrete before/after code migrations.

## Why Hewg

Upgrading a dependency usually means reading changelogs by hand, cross-referencing GitHub issues, and
hoping nothing breaks silently. Hewg automates that: point it at a package and a version range, and it
forges a structured migration guide — what broke, what's deprecated, what's new, and exactly what to
change in your code.

The name comes from the blacksmith in Elden Ring who upgrades the player's weapons — Hewg upgrades your
dependencies.

**Current scope (Phase 1)**: single npm package, version-range analysis. Planned next:

- **Phase 2** — code-aware impact analysis: point Hewg at a project directory and it scans your actual
  code (tree-sitter) to tell you which changes affect you specifically, not just what changed upstream.
- **Phase 3** — full `package.json` analysis: all outdated dependencies at once, inter-dependency
  conflict detection, a prioritized migration order.
- **Phase 4** — multi-ecosystem support (Java/Maven, Python/pip).
- **Phase 5** — a migration agent: Hewg applies the changes itself, verifies the build, and iterates on
  failures.

## Architecture

```
Angular frontend  ──HTTP + SSE──>  FastAPI backend  ──>  PostgreSQL + pgvector
 (input form,                       /api/analyze           packages · releases
  SSE progress,                     /api/analyze/:id/status analyses
  results view)                     /api/analyze/:id
                                          │
                                          ▼
                                 analysis pipeline (see below)
```

Each analysis runs as a background task; the backend streams progress back over SSE so the frontend
never blocks on one long request. The LLM call is the slow, rate-limited, externally-fallible step, so
it's isolated behind a provider-agnostic dispatch + batching layer (see **LLM provider** and
**Pipeline** below) — everything else (fetching, parsing, caching) is deterministic and fast. Data and
LLM calls are cached in Postgres per `(package, version)`, so re-analyzing an overlapping range reuses
what's already fetched.

## Stack
FastAPI · PostgreSQL 16 + pgvector · pluggable LLM provider (Anthropic or any OpenAI-compatible endpoint —
Groq, OpenRouter, Ollama, etc.) · Angular 22 (signals, zoneless) · SSE progress · dark/light theme

## Run locally

Requires Node ≥ 22.22.3 (Angular 22), pnpm, Python 3.12+, and Postgres with pgvector.

```bash
cp .env.example .env   # see "LLM provider" below for what to fill in

# Backend — with Docker:
docker compose up                 # db + API on :8000 (runs migrations)
# ...or without: start a pgvector Postgres, then
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload

# Frontend
cd frontend && pnpm install && pnpm start   # http://localhost:4200, proxies /api -> :8000
```

Tests: `cd backend && .venv/bin/pytest` · `cd frontend && pnpm test`

## LLM provider

The analysis step is config-driven, not hardcoded to one provider:

```bash
LLM_PROVIDER=openai_compatible          # "anthropic" | "openai_compatible"
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
ANALYSIS_MODEL=openai/gpt-oss-120b
MAX_BATCH_TOKENS=1800                   # per-call input budget; tune to your provider's rate limit
LLM_MAX_OUTPUT_TOKENS=4000              # openai_compatible branch only
LLM_REASONING_EFFORT=low                # reasoning models (e.g. Groq's gpt-oss) only; omit otherwise
```

Defaults to Groq's free tier for cost-free early-stage dev. To use Claude instead, set
`LLM_PROVIDER=anthropic` and provide `ANTHROPIC_API_KEY` + `ANALYSIS_MODEL=claude-sonnet-4-6` — no
code change needed either way. See `.env.example` for both blocks side by side.

## Pipeline

npm registry (versions, repo) → GitHub releases + CHANGELOG.md → store full per-version content →
split any oversized release into multiple chunks (sized to the current provider's batch budget,
nothing truncated/dropped) → group chunks into token-budgeted batches → one LLM call per batch
(temperature 0, JSON, validated with Pydantic, retried once on bad JSON; if a batch's response
itself overflows the output budget, it's automatically halved — by item, then by text — and
retried) → merge batch results → store → SSE `progress`/`complete`/`error` events.
See `backend/app/services/analyzer.py` and `backend/app/services/llm.py`.

## Notes
- Anthropic has no embeddings API; embeddings use OpenAI (`OPENAI_API_KEY`, separate from the LLM
  provider key above). Without it, embedding is skipped and analysis still works (retrieval is
  currently a metadata filter, not similarity search).
- Prompts are versioned files in `backend/app/prompts/`; each analysis records its prompt version
  and which model produced it.
- Transient provider errors (rate limits, temporary overload) are retried with backoff
  automatically; a provider's own free-tier limits (requests/tokens per minute) still apply, so a
  very large version range will take longer due to pacing, not fail outright.
