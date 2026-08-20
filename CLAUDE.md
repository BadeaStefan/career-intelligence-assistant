# Career Intelligence Assistant — working conventions

Read `docs/superpowers/specs/2026-08-20-career-intelligence-design.md` before
changing anything. It records *why* each decision was made; this file records
how to work inside those decisions.

## Layout

- `api/` — FastAPI service. Owns all database and OpenAI access.
- `web/` — Vite + React SPA. Pure consumer of the HTTP API.
- Named by role, not position, so a queue `worker/` can join them later
  without renaming anything.

## Non-negotiables

These are not style preferences. Each one exists because violating it
reintroduces a specific bug the design set out to prevent.

1. **Test first.** Write the failing test, run it, watch it fail for the
   expected reason, then implement. A test that has never failed has not
   been shown to test anything.

2. **No network in unit tests.** OpenAI sits behind the `LLMClient` and
   `Embedder` Protocols in `api/src/career_intel/llm/protocol.py`. Tests
   inject `FakeLLM` / `FakeEmbedder`. Tests that hit the real API carry
   `@pytest.mark.live` and are deselected by default.

3. **Route handlers stay thin.** No business logic, no LLM calls, no query
   construction in `api/routes/`. Handlers call services and serialise.

4. **Never hold a database transaction across an OpenAI call.** All network
   work completes first; the transaction wraps only the writes.

5. **Every LLM call records an `llm_calls` row** with its `purpose`. This is
   the observability story — telemetry is not optional instrumentation to be
   added later.

6. **The model never produces character offsets.** Extraction returns verbatim
   quotes; `ingest/locate.py` finds them in `raw_text`. Unlocatable quotes get
   null offsets. Never guessed, and never fuzzy-matched — an approximate match
   highlights the wrong span, which is the failure this exists to prevent.

7. **Model-returned identifiers are validated, not trusted.** Anything citing
   a handle outside the candidate set it was given is dropped
   (`analysis/validation.py`).

8. **Scores are arithmetic, in Python.** The LLM is never asked for a holistic
   percentage.

9. **`EMBEDDING_DIM` is a constant, not a setting.** Migrations must be
   deterministic. See `constants.py` for the full reasoning.

10. **Raw document text never enters logs.** A resume is PII.

11. **Anything that can be a database constraint must never be a prompt
    instruction.** Scoping, ownership, and filtering are SQL concerns.

## Commands

```bash
# API
cd api
uv sync                       # install; add --reinstall-package career-intel if imports fail
uv run pytest                 # unit + eval, no network
uv run pytest -m live         # hits the real OpenAI API
uv run ruff check && uv run mypy src

# Web
cd web
npm install && npm test

# Everything
docker compose up --build
```

## Commits

Conventional commits. Explain *why* in the body, not what — the diff already
says what. End messages with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
