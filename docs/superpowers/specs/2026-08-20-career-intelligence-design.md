# Career Intelligence Assistant — Design

**Date:** 2026-08-20
**Status:** Approved, pre-implementation
**Context:** Fullstack AI Engineer take-home, Option 4.

---

## 1. What we are building

A web application that ingests one resume and several job postings, then answers
questions about fit, skill gaps, experience alignment, and interview preparation.

The distinguishing decision: **retrieval happens over extracted requirements and
evidence units, not only over prose chunks.** A question like "what am I missing
for Job #2?" demands *complete* coverage of that job's requirements. Top-k
similarity search is incomplete by construction and will silently omit the
requirement that mattered. So we extract each job's requirements as discrete
records at ingest time and evaluate every one of them.

### Goals

- Upload a resume and multiple job postings (file or pasted text).
- A persisted, per-job fit analysis: requirement-by-requirement verdicts with
  citations pointing at exact spans of the resume.
- Grounded conversational Q&A, scoped to a selected job.
- Observable: token counts, latency, cost, and retrieval scores visible in the UI.
- Containerised, tested, reproducible.

### Non-goals (documented, not built)

- Authentication and multi-tenancy. Single implicit workspace.
- Fetching job postings from a URL. Job boards block server-side fetching and
  the ones that don't need JS rendering; it is a scraping project in disguise.
- Resume rewriting / generation.
- A cross-job comparison matrix. Attractive, but requires clustering
  differently-worded requirements into shared rows — the piece most likely to
  visibly misfire in a demo. Candidate for later.

---

## 2. Architecture

Three containers.

```
┌──────────────┐        ┌───────────────────────────┐        ┌──────────────┐
│  web         │  HTTP  │  api                      │        │  db          │
│  Vite+React  │◄──────►│  FastAPI                  │◄──────►│  Postgres 16 │
│  TypeScript  │        │  ingest / analysis / chat │        │  + pgvector  │
└──────────────┘        └────────────┬──────────────┘        └──────────────┘
                                     │
                                     ▼  OpenAI (LLM + embeddings)
```

`api` is the only component that touches OpenAI or the database. The frontend is
a pure consumer of a typed HTTP API. This boundary is what makes the
productionisation story concrete: `api` becomes an ECS service or Lambda, `web`
becomes static assets behind CloudFront, `db` becomes RDS/Aurora with pgvector.

### Repository layout

```
career-intelligence-assistant/
├── api/                    FastAPI service — own Dockerfile, pyproject.toml, uv.lock
├── web/                    Vite + React — own Dockerfile, package.json
├── docker-compose.yml
├── CLAUDE.md               conventions for AI-assisted development
└── README.md
```

---

## 3. Ingest pipeline

One pipeline, three outputs. A single ingest function parses the file once, then
writes three kinds of record inside one transaction. Nothing is duplicated;
deletion cascades from one foreign key.

```
file upload (PDF/DOCX/TXT)  ─┐
                             ├─►  parse to plain text  ─►  documents row
pasted raw text             ─┘         (the only branch)
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              ▼                              ▼                              ▼
      chunk + embed                LLM structured extraction        embed extracted units
      ~400 tokens, overlapping     strict JSON schema, 1 retry
      → chunks                     resume → skills, roles,          → evidence_units
      [fallback + scale path]               achievement bullets      → requirements
                                   job    → requirements tagged
                                            required / preferred
```

Both document kinds accept either a file upload or pasted text. Parsing is the
only branch; everything downstream is identical.

### Why keep chunking at all?

The entire corpus is ~5000 tokens and would fit in a single context window. Chunk
retrieval is nonetheless kept, for three reasons:

1. **Degradation path.** If extraction returns malformed JSON twice, the document
   must still be answerable. Chunks are lossless; extraction is lossy by design.
2. **Scale.** One resume and three jobs fits in context. Thirty saved postings
   does not.
3. It is ~30 lines of code. If it sprawls, cut it.

Chunking is deliberately *not* the primary retrieval mechanism, and the README
should say so explicitly.

### Extraction contract

Pydantic models + OpenAI structured outputs. On schema-validation failure: one
retry. On second failure: set `documents.extraction_status = 'failed'` while
`documents.status` stays `ready`, keep the chunks, and let the document degrade
to plain chunk RAG rather than erroring. The two columns are deliberately
separate: `status` means "is this document usable at all", `extraction_status`
means "did we get structured records out of it". A job whose extraction failed
is still answerable in chat but cannot produce a fit analysis, and the UI says
so.

---

## 4. Data model

No polymorphic "embeddings" table. Retrieval queries are always scoped to exactly
one kind, so a shared table would force a `WHERE kind = …` filter onto every
query and span one index across three unrelated distributions.

```
documents            id, kind(resume|job), title, company, filename,
                     source(upload|paste), raw_text,
                     status(pending|ready|failed),
                     extraction_status(pending|ready|failed), created_at

  ├─ chunks          document_id, ordinal, text, char_start, char_end,
  │                  embedding vector(1536)

  ├─ evidence_units  (resume only)
  │                  document_id, kind(skill|achievement|role), text,
  │                  char_start, char_end, embedding vector(1536)

  └─ requirements    (job only)
                     document_id, ordinal, text,
                     importance(required|preferred), category,
                     embedding vector(1536)

fit_analyses         resume_doc_id, job_doc_id, overall_score, summary,
                     model, created_at    UNIQUE(resume_doc_id, job_doc_id)

  └─ requirement_matches
                     fit_analysis_id, requirement_id,
                     verdict(strong|partial|missing), score, rationale
      └─ match_evidence    requirement_match_id, evidence_unit_id

chat_sessions        id, job_doc_id (nullable), created_at
  └─ chat_messages   session_id, role, content, citations jsonb, created_at

llm_calls            purpose, model, prompt_tokens, completion_tokens,
                     latency_ms, cost_usd, request_id, created_at
retrieval_traces     request_id, query, results jsonb (ids + scores)
```

`char_start` / `char_end` are what make citations real: every claim in the UI
points at an exact span of the actual resume text, not a paraphrase.

SQLAlchemy 2.0 for models, Alembic for migrations. HNSW indexes on each
`embedding` column.

### Requirement-to-job linkage

Requirements are linked to their job by foreign key, written by Python after a
per-document extraction call. The model is never asked which job a requirement
belongs to, so it cannot get it wrong. Fit analysis is scoped to one
`(resume, job)` pair, so no other job's data is ever in the context window.

> **Anything that can be a database constraint must never be a prompt
> instruction.**

---

## 5. Fit analysis engine

Runs once per `(resume, job)` pair and is **persisted**. The dashboard must
render instantly; it cannot be issuing LLM calls while the user waits.

```
for each requirement:  kNN vs. this resume's evidence_units → top 5 + scores
        ▼
ONE structured-output call carrying all requirements + their candidates
        ▼
per requirement: { verdict: strong|partial|missing, score, rationale, evidence_ids }
        ▼
VALIDATE: every evidence_id must be one supplied for that requirement
        ▼
overall score computed in Python
```

**One call, not N.** Scoring 14 requirements in 14 calls yields 14
independently-calibrated opinions. Batched, the model grades against itself. Also
~14x cheaper and one round trip. Jobs with more than ~10 requirements are batched
in groups so outputs stay short enough to remain reliable.

**Evidence ids are validated, not trusted.** The model may cite only from the
candidate set supplied for that specific requirement; anything else is dropped.
This is a structural grounding guarantee, not a prompt-based one — the model
cannot fabricate a citation that survives validation.

**Short handles in prompts.** Requirements and evidence appear as `r1`, `r2`,
`e1`, `e2` and are mapped back to database ids in Python. Long UUIDs get mangled
by tokenizers; two-character handles do not.

**Scoring is arithmetic, in Python.** `required` weighs double, `preferred`
single; `strong` = 1.0, `partial` = 0.5, `missing` = 0. The LLM is never asked
for a holistic percentage — models are inconsistent at it and cannot explain it.
This version is reproducible, unit-testable, and every number on screen traces to
a specific verdict.

---

## 6. Chat

Cheaper, separate path. Context = the selected job's spec + its cached fit
analysis + top-k resume chunks + recent turns. Answers carry citations, validated
the same way as the fit engine's.

Job selection scopes retrieval via SQL (`WHERE document_id = :job_id`), not via a
prompt instruction.

---

## 7. Frontend

Layout: **analysis-first with a docked chat**.

```
┌────────────────────────────────────────────────────────────┐
│ Career Intelligence · resume.pdf                           │
├──────────┬──────────────────────────────┬──────────────────┤
│ Jobs     │ Senior Backend · Datadog 72% │ Ask about this   │
│ ▸ #2 72% │  Strong match · 8            │ job              │
│   #1 84% │   Python, 5+ yrs             │                  │
│   #3 55% │    "Built ingestion…" l.9    │  [chat turns]    │
│ + Add    │  Gaps · 4                    │                  │
│          │   Kubernetes      missing    │  [ask…]          │
│          │   Go              partial    │                  │
└──────────┴──────────────────────────────┴──────────────────┘
```

Scored fit cards are present the moment upload finishes — no empty chat box
demanding the user already know what to ask. Clicking a job opens its
requirement-by-requirement breakdown with evidence citations. Chat is scoped to
the selected job.

A "how did I get this answer?" drawer exposes `llm_calls` and
`retrieval_traces` for the current interaction.

Stack: Vite + React + TypeScript, TanStack Query for server state, Tailwind.
Visual design is a later pass; this spec fixes structure only.

---

## 8. Guardrails

- **Untrusted content.** Job postings are pasted from the web. Document text is
  delimited and the system prompt declares it data, never instructions.
- **Grounding.** Evidence-id validation (§5) applied to chat answers too.
- **No invented experience.** Explicit prompt rule *and* an eval that baits it.
- **Scope.** Off-topic questions get a polite redirect, not a general-purpose
  chatbot answer.
- **Input limits.** Mime allowlist, 5 MB cap, text length cap, page cap.
- **PII.** A resume is PII. Raw content never enters logs; retention stated
  plainly in the README.

---

## 9. Quality and evaluation

A golden fixture: one synthetic resume, three job postings, hand-labelled
expectations ("Kubernetes is missing for job 2"; "Python is strong for job 1").
Evals assert precision/recall against those labels rather than exact strings, so
they survive rewording. This is what makes prompt changes measurable rather than
vibes.

---

## 10. Observability

`structlog` JSON logging with a request-id middleware. Every LLM call writes an
`llm_calls` row (model, tokens, latency, computed cost); every retrieval writes a
`retrieval_traces` row (ids + scores). These feed the UI drawer.

Nearly free — the calls are already being made — and real numbers on screen are a
better answer to "how would you monitor this?" than a paragraph about Datadog.

---

## 11. Testing

- The OpenAI client sits behind a small provider interface. Unit tests inject a
  fake embedder and fake LLM: no network, runs in seconds.
- Live-API tests sit behind a pytest marker, skipped by default.
- Route handlers stay thin; logic lives in services testable without HTTP.
- Frontend: Vitest + Testing Library on the components that carry logic.

---

## 12. Configuration and reproducibility

`uv` for Python dependency management, with `uv.lock` committed. The Dockerfile
installs from the same lockfile, so local venv and container are provably
identical. Local `api/.venv` exists for editor resolution and fast test runs;
the container remains the source of truth for running the app.

Config via `pydantic-settings`, `.env.example` committed, `.env` ignored.

---

## 13. Known edge cases (acknowledged, not all handled)

- Scanned/image PDFs produce no text. Detected and surfaced as a clear error; no
  OCR.
- Multi-column resume layouts can interleave badly on text extraction.
- Very long job postings (>20 requirements) are batched; batch boundaries may
  slightly affect calibration.
- Non-English documents are untested.
- Concurrent uploads of the same document are not deduplicated.

---

## 14. Productionisation sketch (for the README)

`web` → S3 + CloudFront. `api` → ECS Fargate behind an ALB, or Lambda with an
adapter. `db` → RDS Postgres with pgvector. Secrets in Secrets Manager. Ingest
and analysis move to a queue (SQS + worker) so uploads return immediately.
Per-user isolation requires auth plus a tenant column and row-level security.
Cost controls: per-user rate limits, and the `llm_calls` table already provides
the spend telemetry.
