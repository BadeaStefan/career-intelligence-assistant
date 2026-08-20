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
- Grounded conversational Q&A, scoped to a selected job by default, with an
  explicit toggle to widen to all jobs for comparison questions.
- Per-job interview preparation derived from the fit analysis.
- Observable: token counts, latency, cost, and retrieval scores visible in the UI.
- Containerised, tested, reproducible.

### Non-goals (documented, not built)

- Authentication and multi-tenancy. Single implicit workspace.
- Fetching job postings from a URL. Job boards block server-side fetching and
  the ones that don't need JS rendering; it is a scraping project in disguise.
- Resume rewriting / generation.
- A cross-job comparison *matrix view*. Attractive, but requires clustering
  differently-worded requirements into shared rows — the piece most likely to
  visibly misfire in a demo. Cross-job *questions* are supported in chat via the
  "all jobs" scope (§6), which covers most of the value without that risk.

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

All network work (extraction calls, embedding batches) completes *before* the
transaction opens; the transaction wraps only the writes. A Postgres transaction
is never held open across an OpenAI call.

### Execution model

The work splits along one line: **is it fast, local, and able to fail for a
reason the user can act on?**

**Parsing happens in the request.** PDF and DOCX extraction takes milliseconds,
needs no network, and its failure modes — a scanned PDF, an unsupported type —
are things the user must fix by uploading something else. Deferring it would
mean returning `201`, then making the user poll to discover their upload was
never usable, and it would require storing the raw file bytes in Postgres so a
later task could read them. So the endpoint parses (on a threadpool, since
pypdf is blocking), returns `415`/`422` directly on failure, and on success
stores the text with `status = 'ready'`.

**Enrichment happens in a `BackgroundTask`** — chunking, extraction, embedding,
and then fit analysis for every `(resume, job)` pair that now exists (§5). This
is the slow, networked half that genuinely cannot block an upload.
`extraction_status` tracks it, and the frontend polls that. A full queue
(SQS + worker, §14) is deliberately not built locally: `BackgroundTasks` gives
the same non-blocking UX with none of the infrastructure, and the seam where a
queue slots in is exactly this one function.

This is why `status` and `extraction_status` are separate columns rather than
one: they are settled by different halves of the pipeline, at different times,
with different failure semantics.

**Crash recovery.** Background tasks run inside the API process, so a row can be
stranded at `pending` two ways. Both are closed:

1. **Process death.** On startup, *every* `documents` and `fit_analyses` row
   still `pending` — in either `status` or `extraction_status` — is marked
   `failed`, with no age check. An in-process task
   cannot survive a restart by definition, so a row that is `pending` when the
   process boots is provably orphaned — its task died with the previous process.
   An age threshold would be actively harmful here: a row younger than the
   threshold at boot would survive the sweep and then hang forever, since
   nothing remains to finish it.
2. **Task exception.** The task body is wrapped so that any exception marks its
   row `failed` before propagating.

Together these guarantee every path out of `pending` terminates. Failures are
retryable from the UI. This is the honest limitation of the in-process
shortcut — handled rather than hidden.

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

Chunking is deliberately *not* the primary retrieval mechanism; the README
states this explicitly.

### Extraction contract

Pydantic models + OpenAI structured outputs. On schema-validation failure: one
retry. On second failure: set `documents.extraction_status = 'failed'` while
`documents.status` stays `ready`, keep the chunks, and let the document degrade
to plain chunk RAG rather than erroring. The two columns are deliberately
separate: `status` means "is this document usable at all", `extraction_status`
means "did we get structured records out of it". A job whose extraction failed
is still answerable in chat but cannot produce a fit analysis, and the UI says
so.

### Span location: the model quotes, Python locates

LLMs cannot produce reliable character offsets — asked for `char_start`, a model
returns plausible-looking numbers that are off by tens or hundreds of
characters, which would quietly corrupt every citation in the UI. So the
extraction schema asks for the **exact verbatim quote** instead, and Python
computes the offsets by locating that quote in `raw_text`:

1. Exact substring match.
2. Fallback: whitespace-normalised match (extraction sometimes collapses line
   breaks), offsets mapped back to the original text.
3. If neither matches, the unit is kept for retrieval but stored with null
   offsets — it can still support a verdict, it just cannot be highlighted.
   Never guessed.

The eval fixture (§9) asserts a minimum location rate so a prompt change that
degrades quoting fidelity is caught, not shipped.

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
  │                  char_start, char_end (nullable, see §3 span location),
  │                  embedding vector(1536)

  └─ requirements    (job only)
                     document_id, ordinal, text,
                     importance(required|preferred), category,
                     embedding vector(1536)

fit_analyses         resume_doc_id, job_doc_id, status(pending|ready|failed),
                     overall_score, summary, model, created_at
                     UNIQUE(resume_doc_id, job_doc_id)

  └─ requirement_matches
                     fit_analysis_id, requirement_id,
                     verdict(strong|partial|missing), score, rationale
      └─ match_evidence    requirement_match_id, evidence_unit_id

chat_sessions        id, job_doc_id (nullable), scope(job|all), created_at
  └─ chat_messages   session_id, role, content, citations jsonb, created_at

interview_preps      fit_analysis_id, model, created_at
                                      UNIQUE(fit_analysis_id)
  └─ prep_questions  interview_prep_id, requirement_id, question,
                     why_they_will_ask, how_to_frame, evidence_ids[]

llm_calls            purpose, model, prompt_tokens, completion_tokens,
                     latency_ms, cost_usd, request_id, created_at
retrieval_traces     request_id, query, results jsonb (ids + scores)
```

`char_start` / `char_end` are what make citations real: every claim in the UI
points at an exact span of the actual resume text, not a paraphrase. They are
computed by Python from verbatim quotes (§3), never taken from the model.

Chat citations live in a `jsonb` column while fit citations get a join table —
a deliberate asymmetry. `match_evidence` is queried relationally (the dashboard
joins verdicts to evidence spans); a chat message's citations are only ever read
back with that one message.

SQLAlchemy 2.0 for models, Alembic for migrations.

HNSW indexes on each `embedding` column, with an honest caveat: at this corpus
size they buy nothing. A sequential scan is fine under roughly 10k rows, and
because HNSW is an *approximate* index it trades recall for speed — so at this
scale it is fractionally worse for correctness than no index at all. They are
present so the schema is the one that scales, and the README says exactly that
rather than claiming a performance win.

The `1536` dimension is a single named constant in code, imported by both the
models and the migration. It is deliberately **not** read from the
embedding-model setting at migration time: a migration must produce the same
schema on every run, and one that reads live config would generate a 3072-dim
column the day someone switches to `text-embedding-3-large`, silently diverging
two databases built from identical history. Changing dimensions requires a new
migration — which is correct, because it is a genuine schema change that also
requires re-embedding every row.

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

### Lifecycle

Analysis is triggered automatically by ingest (§3): when a document becomes
`ready`, a `fit_analyses` row is inserted with `status = 'pending'` for each
newly-completed pair, then computed in the same background task. The dashboard
reads that status — a card is "analysing…" until `ready`, and a `failed`
analysis shows a retry button rather than a blank. Uploading a new resume
replaces the old one: the old `documents` row is deleted, analyses cascade away
with it, and every pair is recomputed against the new resume.

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

Cheaper, separate path. Answers carry citations, validated the same way as the
fit engine's.

Chat has two scopes, chosen by an **explicit toggle in the chat header**:

```
"this job"  (default)  → job spec + its cached analysis + top-k resume chunks
"all jobs"             → every job's summary + every cached fit analysis
                         + top-k resume chunks

both scopes        also → last N conversation turns
```

### Context management

Every request also carries the **last 8 turns** of the session, capped at
~1500 tokens; when the cap is exceeded the oldest turns are dropped first.
Without this, follow-ups like "what about that second gap?" have no referent.

Dropped turns are **not** summarised. Summarisation is a second LLM call in the
hot path that can itself hallucinate, and at this corpus size a session long
enough to need it is already an outlier. Truncation is visible and predictable;
the README notes it as a deliberate limit and summarisation as the next step if
sessions grow.

Rough budget for a `this job` request: ~800 tokens job spec, ~600 analysis,
~1000 chunks, ~1500 history, leaving ample headroom. The `all jobs` scope
substitutes analyses for the single job spec and stays under ~4000.

Cross-job comparison needs no special retrieval machinery. A cached analysis is
an overall score plus ~15 short requirement verdicts; three jobs is 1–2k tokens
total, so the model compares from structured data it can see *completely* rather
than from a sampled top-k. This delivers most of the value of the deferred
comparison matrix without the requirement-clustering risk.

Scope is a UI toggle rather than an LLM intent classifier: deterministic, no
added latency, cannot misroute.

> **Anything that can be UI state must never be a prompt inference.**

Within a scope, job selection filters retrieval via SQL
(`WHERE document_id = :job_id`), not via a prompt instruction.

## 6b. Interview preparation

A per-job **Prep** view, derived entirely from the cached fit analysis — the gaps
are what the candidate will be pressed on; the strong matches are the stories to
lead with. One extra LLM call over data the fit engine (§5) already computed: no
new pipeline, no new retrieval.

Produces 5–8 likely questions, each anchored to the requirement it probes:

```
question, probes_requirement_id, verdict,
why_they_will_ask, how_to_frame, evidence_ids[]
```

`evidence_ids` pass the same validation as §5, so "lead with…" advice cites real
resume spans rather than invented achievements.

Generated on demand and cached in `interview_preps`, not precomputed at ingest —
most users will not open it for every job and it is not free.

---

## 7. Frontend

Layout: **analysis-first with a docked chat**.

```
┌────────────────────────────────────────────────────────────┐
│ Career Intelligence · resume.pdf                           │
├──────────┬──────────────────────────────┬──────────────────┤
│ Jobs     │ Senior Backend · Datadog 72% │ ( this job │ all)│
│ ▸ #2 72% │ ┌ Analysis ┬ Prep ┐          │                  │
│   #1 84% │  Strong match · 8            │  [chat turns]    │
│   #3 55% │   Python, 5+ yrs             │                  │
│ + Add    │    "Built ingestion…" l.9    │                  │
│          │  Gaps · 4                    │  [ask…]          │
│          │   Kubernetes      missing    │                  │
│          │   Go              partial    │                  │
└──────────┴──────────────────────────────┴──────────────────┘
```

The centre pane has two tabs: **Analysis** (§5) and **Prep** (§6b). The chat
header carries the scope toggle from §6.

Scored fit cards are present the moment upload finishes — no empty chat box
demanding the user already know what to ask. Clicking a job opens its
requirement-by-requirement breakdown with evidence citations. Chat is scoped to
the selected job.

A "how did I get this answer?" drawer exposes `llm_calls` and
`retrieval_traces` for the current interaction.

Stack: Vite + React + TypeScript, TanStack Query for server state, Tailwind.

This spec fixes structure only. Visual design happens as a **timeboxed mockup
pass (Claude Design) before frontend implementation** — the dashboard plus its
loading / analysing / extraction-failed states — so the React code implements a
target rather than accreting one. Design is an explicit evaluation criterion,
not a leftover polish task.

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

`structlog` JSON logging with a request-id middleware. Every attempted LLM call
writes an `llm_calls` row. Successful calls include model, tokens, latency, and
computed cost; provider failures include model, latency, a safe exception-class
name, and null usage/cost rather than invented zeroes. Every retrieval writes a
`retrieval_traces` row (ids + scores). These feed the UI drawer. Valid inbound
request ids are limited to the database's 64-character boundary; invalid values
are replaced with a generated UUID.

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

Config via `pydantic-settings`, `.env.example` committed, `.env` ignored. The
embedding dimension is **not** a setting — it is a code constant, for the reason
given in §4.

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
