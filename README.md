# Career Intelligence Assistant

Upload one resume and a couple of job postings and the app tells you how well you fit
each job requirement by requirement, with citations pointing at the exact lines
of your resume. In adition it has a chat and per-job interview prep.

---

## Quick start

You need Docker and an OpenAI API key.

put your OPENAI_API_KEY in .env
then run: docker compose up --build


- Web UI: http://localhost:5173
- API: http://localhost:8000

Running the tests (no network, no API key needed — OpenAI is faked in unit tests):

cd api
uv sync
uv run pytest             unit tests
uv run pytest -m live     hits the real OpenAI API

cd web
npm install && npm test

---

## What it does

- Upload a resume and multiple job postings (PDF / DOCX / TXT, or pasted text).`/docs/screenshots/Adding-job.png`
- Every resume and job pair gets a persisted fit analysis: a verdict
  (strong / partial / missing) for each requirement, with citations that
  highlight the exact span of the resume that supports it.
- Chat that can be scoped to selected job or to all jobs. `/docs/screenshots/Job-analysis-and-chat-question.png`
- Interview prep per job, derived from the fit analysis: likely questions,
  why they'll ask them, and how to frame your answer using real resume evidence. `/docs/screenshots/Interview-prep.png`
- An observability drawer: token counts, latency, cost, and retrieval scores
  for the current interaction. `/docs/screenshots/Observability.png`


The loading and failure states were designed on purpose, a
failed analysis shows a retry button, and a job whose extraction failed degrades
to plain chunk RAG in chat instead of erroring.

---

## Architecture

Three containers. The api service is the only thing that talks to OpenAI or
the database. The frontend is just reflecting the backend (api) processes


┌──────────────┐        ┌───────────────────────────┐        ┌──────────────┐
│  web         │  HTTP  │  api                      │        │  db          │
│  Vite+React  │◄──────►│  FastAPI                  │◄──────►│  Postgres 16 │
│  TypeScript  │        │  ingest / analysis / chat │        │  + pgvector  │
└──────────────┘        └────────────┬──────────────┘        └──────────────┘
                                     │
                                     ▼  OpenAI (LLM + embeddings)
                              


Repo layout: `api` (FastAPI, own Dockerfile + uv.lock), `web/` (Vite + React,
own Dockerfile), `docs/` (design spec, screenshots). The full design doc with
the reasoning behind every decision is at `/docs/superpowers/specs/2026-08-20-career-intelligence-design.md`

---

## RAG / LLM approach and decisions

### Retrieval

Ingest parses the document once, then produces three kinds of record:

- chunks — ~400-token overlapping windows of the raw text
- evidence units (resumes) — skills, roles, achievement bullets
- requirements (jobs) — one row per requirement, tagged required/preferred

All three are embedded. The fit engine does per-requirement kNN over the
resume's evidence units.

Chunking isn’t the main way we retrieve information. We keep it for two reasons: 
1. As a backup when structured extraction fails
2. For handling larger amounts of data that won’t fit in the context window.

### Model choices

- LLM gpt-4o-mini. Every call here is either structured extraction or
  grounded Q&A over a small, fully-supplied context, exactly the kind of task
  where a small model with structured outputs is reliable. It's cheap enough to
  run the full ingest + analysis pipeline on every upload without problems, and
  the llm_calls table proves the cost. 
- Embeddings use text-embedding-3-small with 1536 dimensions.
  Since the amount of text is very small (~5k tokens), retrieval quality isn’t a concern. 
  The embedding dimension is fixed in the code rather than configurable, 
  so database migrations always create the same schema.

  Another reason for this choice was that it's requiring a single api key since both
  the LLM and embedding are from OpenAI.

### Vector database: pgvector, not a dedicated vector store

The vector data is stored directly in the relational database because
it is closely connected to the rest of the application data.
For example, evidence, verdicts, requirements, resumes, and chunks
are linked using foreign keys. Using a separate vector database like Pinecone
would make the system more complex because we would need to keep two databases synchronized.
Since the amount of data is small, there would not be a real performance benefit.

### No orchestration framework

No LangChain / LlamaIndex. The "orchestration" is one ingest pipeline and two
prompt paths.

### Prompt engineering

The model does not generate text positions. Instead, it returns the exact quote,
and Python finds where that quote appears in the original text. This avoids incorrect
citations caused by the LLM guessing character positions.
Short IDs are used in prompts. Requirements and evidence are shown as simple names like r1 and e2,
then Python maps them back to the real database IDs.
The final score is calculated in Python. The LLM only decides whether a requirement is strong, partial, or missing. Python then calculates the final percentage using fixed rules, which makes the result consistent and easy to test.

### Context management

Chat requests carry the last 8 turns, ~1500 tokens, oldest dropped
first.

Scope ("this job" vs "all jobs") is a UI toggle, not an LLM intent classifier:
deterministic, zero added latency. Within a scope, job
filtering is a SQL `WHERE document_id = :job_id` — my working rule was:
anything that can be a database constraint must never be a prompt instruction.

### Guardrails

- Job postings are pasted from the web, so document text is delimited and
  declared as data, never instructions.
- Citations are validated structurally, not by prompt. The model may only
  cite evidence ids from the candidate set it was given for that specific
  requirement; anything else is dropped in Python. It cannot fabricate a
  citation that survives validation. The same validation applies to chat
  answers and interview prep.
- Explicit "no invented experience" rule.
- Off-topic questions get a polite redirect, not a general chatbot answer.
- A resume it's raw document text that never enters logs.

### Observability

Every attempted LLM call writes an llm_calls row (purpose, model, tokens,
latency, computed cost). Every retrieval writes a retrieval_traces row with ids + scores. structlog JSON logging with
request-id middleware ties them together, and a "how did I get this answer?"
drawer in the UI exposes them for the current interaction. `/docs/screenshots/Observability.png`

---

## Key technical decisions

The ones I'd defend hardest (each has a fuller writeup in the design doc):

1. Extract requirements at ingest; evaluate all of them.
2. Citations either point at the real text or don't render — never at
   the wrong span.
3. FastAPI BackgroundTasks are used instead of a separate job queue. 
   Slow tasks like extraction, embeddings, and analysis run in the background. 
   If the server crashes while a task is still pending, that task is marked as failed when the app starts again. 
   Errors during processing also mark the task as failed.
6. Separate tables per embedded kind instead of one polymorphic embeddings
   table — queries are always scoped to one kind, and one index shouldn't span
   three unrelated distributions.

Deliberate non-goals: auth/multi-tenancy, fetching postings from URLs,
resume rewriting, and a cross-job comparison 

---

## Productionising it

If this application was used by real users, I would make a few changes:

- Frontend - host the static website using Vercel.
- Backend - deploy the API on AWS.
- Database - use a managed PostgreSQL database with pgvector.
- Secrets - store API keys and other sensitive values in AWS Secrets Manager instead of .env files.
- Multiple users - add authentication and make sure each user can only access their own data.
- Cost control - add rate limits and use the existing llm_calls table to track LLM usage and cost.

---

## Engineering standards

- Unit tests
- Thin route handlers: no business logic, no LLM calls, no query construction
  in routes.
- uv with a committed lockfile; the Dockerfile installs from the same
  lockfile, so the local venv and the container are provably identical.
- Alembic migrations; conventional commits with "why" in the body.

---

## How I used AI tools

First, i discussed with claude code and codex about the app in order to get a good perspective.
Then i started writing the spec file `/docs/superpowers/specs/2026-08-20-career-intelligence-design.md`, making
sure that it is following the design, arhitecture and decisions that I need. After that followed a full plan
`/docs/superpowers/plans/2026-08-20-career-intelligence.md` that was in more detail, split in 5 phases each one with more tasks.
*My rule is that in order to have the best and most repetable AI outputs you need to make sure it doesn't have to guess what to do*
The implementation was phase 1 -> all phase 1 tasks -> phase 2 -> all phase 2 tasks etc.. After each task i demanded a review,
and in some cases were needed fixes. Mostily it was an agent that had the whole phase in context then deployed subagent for
tasks, then reviews then fixes.
Ai tools used:
- Claude design for the UI/UX
- Claude code and Codex for implementation, code review and verification.

---

## Known limitations

- Scanned/image PDFs produce no text - no OCR
- Multi-column resume layouts can interleave badly on text extraction.
- Non-English documents are untested.
- Concurrent uploads of the same document are not deduplicated.
- Chat history is truncated.
- Chat dissapears if switched beetwen jobs.
- Retention: documents live in Postgres until you delete them.

## What I'd do next

1. Add authentication so multiple users can securely use the app.
2. Add OCR support for scanned resumes and documents.
3. Add job posting import from a URL, so users don’t have to copy and paste the description manually.
4. Add a feature that suggests resume improvements based on a specific job description.

---

