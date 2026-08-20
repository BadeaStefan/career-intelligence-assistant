# Handoff: Career Intelligence Dashboard

## Overview
Career Intelligence analyzes one resume against multiple job postings. For each job it produces a
requirement-by-requirement fit verdict — **strong / partial / missing** — where every verdict is backed by a
cited span of the user's actual resume text. The dashboard is a fixed three-pane desktop workspace
(1440px) built as an analytical instrument: high information density, restrained typography, and color
reserved almost entirely for the verdict system.

Four states are documented here: the main analysis view, empty/first run, a job analysing in the rail, and a
job whose posting extraction failed.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and
behavior, not production code to copy. The task is to **recreate these designs in the target codebase's
existing environment** (React + Tailwind is the stated target) using its established patterns, component
library, and tokens. If no environment exists yet, pick the appropriate framework and implement there.

`Career Intelligence.dc.html` is a self-contained prototype: open it in a browser to see all four artboards
laid out on one canvas. `support.js` is the prototype runtime only — it has no place in the production
implementation.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and interaction behavior are final. Recreate pixel-accurately
using the codebase's existing libraries. Every value below is exact as authored. Nothing in the design uses
gradients, blur, or effects that won't survive translation to standard flexbox/grid + Tailwind.

---

## Screens / Views

### 1. Main analysis view (artboard `1a`) — 1440 × 940

**Purpose.** The default working state. User reads the fit breakdown for the selected job, expands
requirements to see rationale and citations, switches to interview prep, and asks scoped questions in chat.

**Layout.** Vertical flex. A 46px top bar, then a horizontal flex row filling the remainder:

| Pane | Width | Notes |
|---|---|---|
| Left rail | 240px fixed | `flex: none`, right border, background `oklch(0.985 0.002 250)` |
| Center | fills | `flex: 1; min-width: 0`, white, vertical flex with scrolling body |
| Right chat | 360px fixed | `flex: none`, left border, background `oklch(0.99 0.002 250)` |

All three panes are full height; only the center analysis body and the chat transcript scroll.

#### Top bar (46px)
- `border-bottom: 1px solid var(--line)`, background `oklch(0.995 0.002 250)`, padding `0 16px`,
  `justify-content: space-between`.
- Left: 12×12px solid square mark in `--ink`, then "Career Intelligence" at 13px/600, letter-spacing −0.01em,
  then mono 11px `--muted-2`: "v0.4 · analysis run 20 Aug 2026, 09:14".
- Right, mono 11px `--muted`: "3 jobs · 36 requirements evaluated", a 1×14px divider rule, "Re-run all".

#### Left rail (240px)
1. **Resume block** — padding `14px 14px 12px`, bottom border. Mono 10px uppercase 0.1em label "Resume";
   filename `alex-moraru-resume.pdf` at 13px/600 with `word-break: break-all`; mono 11px meta
   "2 pages · 118 spans indexed".
2. **"Jobs"** mono 10px uppercase label, padding `14px 14px 8px`.
3. **Job rows** — padding `11px 14px`, `border-top: 1px solid oklch(0.93 0.004 250)`, cursor pointer.
   Row content: title 12.5px/600 on the left, score mono 12px/500 on the right (color = verdict color for
   the score band), company 11.5px `--muted` below, then a 3px-tall verdict distribution bar
   (`display:flex; gap:2px`) whose segments are flex-weighted by verdict counts.
   - Unselected hover: background `oklch(0.97 0.003 250)`.
   - Selected: background white + `box-shadow: inset 3px 0 0 var(--ink)` (a left indicator rail, not a border,
     so it doesn't shift layout).

   | Job | Score | Score color | Bar weights (strong/partial/missing) |
   |---|---|---|---|
   | Backend Engineer · Nova Fintech | 84% | `--strong-text` | 10 / 1 / 1 (missing seg uses `oklch(0.9 0.01 250)`) |
   | Senior Backend Engineer · Datadog **(selected)** | 72% | `--partial-text` | 8 / 2 / 2 |
   | Platform Engineer · Snyk | 55% | `--missing-text` | 5 / 2 / 4 |

4. **Footer** — `margin-top: auto`, top border, padding `12px 14px`. "+ Add job" 12px/500 `--ink-3`
   (hover `--ink`), and mono 10.5px hint "Paste a posting URL or text".

#### Center pane — header (padding `18px 24px 0`, non-scrolling)
- Job title 20px/600, letter-spacing −0.015em: "Senior Backend Engineer".
- Meta line, mono 11.5px, `·`-separated items in a flex with 8px gap: **Datadog** (in `--ink-2`), "Remote (US)",
  "posted 6d ago", "12 requirements extracted" (remaining items `--muted`).
- Right-aligned score block: "72%" in mono 34px/500, line-height 1, letter-spacing −0.02em, color
  `oklch(0.5 0.13 75)`; below it mono 10px uppercase 0.1em "Weighted fit".
- **Requirement strip** — 6px tall flex row, `gap: 2px`, 12 equal `flex: 1` cells in verdict order:
  8 × `--strong`, 2 × `--partial`, 2 × `--missing`. This is the primary at-a-glance graphic.
- Legend row, mono 11px, 20px gaps: 7×7px swatch + "8 strong", "2 partial", "2 missing"; right-aligned
  `margin-left: auto` note "Required requirements weighted 2×" in `--muted-2`.
- **Tabs** — flex, 22px gap, `border-bottom: 1px solid var(--line)`, `margin-top: 18px`.
  - Active: 13px/600, `padding-bottom: 9px`, `border-bottom: 2px solid var(--ink)`, `margin-bottom: -1px`.
  - Inactive: 13px/500, color `--muted-2`, same padding, no underline.
  - Tabs: "Analysis" (default), "Interview Prep".

#### Center pane — Analysis tab body (scrolls, padding `0 24px`, inner `18px 0 24px`)
Three verdict groups, each opened by a group header and followed by its rows.

**Group header** — flex, 10px gap, padding `8px 0 10px` (22px top for the 2nd and 3rd groups):
8×8px verdict swatch, mono 10.5px uppercase 0.12em label ("Strong · 8", "Partial · 2", "Missing · 2"),
then a `flex: 1` 1px rule in `oklch(0.93 0.004 250)`.

**Requirement row (collapsed)** — `border-top: 1px solid oklch(0.94 0.004 250)`, clickable header laid out as
`display: grid; grid-template-columns: 1fr 78px 92px 18px; gap: 12px; align-items: center; padding: 11px 4px`.
Hover background `oklch(0.985 0.002 250)`.
1. Requirement text — 13.5px/500, line-height 1.35.
2. Tag — mono 10px uppercase 0.08em `--muted`: "Required" or "Preferred".
3. Verdict badge — inline flex, 6px gap, `padding: 3px 7px`, `justify-self: start`, mono 10px, 0.08em tracking,
   square (no radius): 6×6px dot + uppercase word. Backgrounds/foregrounds in the token table.
4. Disclosure chevron — `▸` collapsed / `▾` expanded, 10px, centered, `--muted-2`.

**Requirement row (expanded)** — appended below the header, `padding: 2px 4px 16px`, vertical flex, 10px gap:
- Rationale paragraph, 13px/1.55, `--ink-4`, `max-width: 660px`, `text-wrap: pretty`.
- **Citation block** — `border-left: 2px solid <verdict color>`, `padding: 8px 12px`, background
  `oklch(0.985 0.002 250)`. Mono 10px uppercase 0.1em caption "Cited from resume · p.1, Ingestion Platform";
  below it the quote at 13px/1.5 with the quoted text wrapped in a `<span>` highlighted in the verdict's
  highlight tint, `padding: 1px 3px`.
  For **missing** rows the block instead reads "No evidence found" and shows the nearest-miss note in mono 12px
  `--muted` — no highlight span, and the border-left is the desaturated `oklch(0.85 0.02 25)`.
- Provenance line, mono 10.5px `--muted-2`: "retrieval score 0.91 · 1 span cited" (partial rows append the gap
  note; missing rows read "best retrieval score 0.38 · below 0.45 threshold").

Default expanded state: only `p1` (Go) is open on load — it demonstrates the expanded treatment without
burying the list.

**Requirement data (12, exact copy).**

| # | Requirement | Tag | Verdict | Score | Citation location |
|---|---|---|---|---|---|
| 1 | Python, 5+ years production experience | Required | STRONG | 0.91 | p.1, Ingestion Platform |
| 2 | Distributed systems design | Required | STRONG | 0.88 | p.1, Ingestion Platform |
| 3 | PostgreSQL and relational data modeling | Required | STRONG | 0.86 | p.1, Ingestion Platform |
| 4 | High-volume data ingestion | Required | STRONG | 0.84 | p.1, Ingestion Platform |
| 5 | REST and gRPC API design | Required | STRONG | 0.79 | p.1, Payments API |
| 6 | Observability and on-call ownership | Preferred | STRONG | 0.77 | p.1, Ingestion Platform |
| 7 | CI/CD pipeline ownership | Preferred | STRONG | 0.74 | p.1, Ingestion Platform |
| 8 | Mentorship and technical leadership | Preferred | STRONG | 0.68 | p.2, Antler Labs |
| 9 | Go for performance-critical services | Required | PARTIAL | 0.57 | p.2, Projects |
| 10 | AWS at scale | Preferred | PARTIAL | 0.62 | p.1, Ingestion Platform |
| 11 | Kubernetes in production | Required | MISSING | 0.38 | — |
| 12 | Terraform / infrastructure as code | Preferred | MISSING | 0.21 | — |

Cited quotes, rationales, and gap notes are in the prototype's logic class (`STRONG`, `PARTIAL`, `MISSING`
arrays) — copy them verbatim; they are written to read as real model output.

#### Center pane — Interview Prep tab
- Intro paragraph, 13px/1.55 `--ink-3`, `max-width: 660px`, `margin-bottom: 18px`.
- Five question blocks, each `border-top: 1px solid oklch(0.94 0.004 250)`, `padding: 16px 4px`, flex row with
  18px gap:
  - Ordinal, mono 11px `--muted-2`, 20px fixed column ("01"…"05").
  - Body column, vertical flex, 10px gap:
    - Question, 15px/600, line-height 1.4, letter-spacing −0.01em, `max-width: 660px`.
    - Anchor row, mono 10.5px: uppercase "Anchored to", then the requirement name in a 1px `--line-2` outlined
      chip (`padding: 2px 6px`, `--ink-2`), then a 6×6px verdict dot + verdict word.
    - Two-column grid (`1fr 1fr`, 20px gap, `max-width: 760px`): "Why they'll ask" and "How to frame it", each a
      mono 10px uppercase 0.1em caption over 12.5px/1.55 `--ink-3` body.
    - Citation block, same as Analysis but with neutral `2px solid oklch(0.86 0.006 250)` border and the neutral
      highlight `oklch(0.94 0.03 100)`; caption "Answer from · p.1, Ingestion Platform".

Question set, in order, each anchored to a requirement: Go (PARTIAL), Kubernetes (MISSING), distributed systems
(STRONG), Postgres migration (STRONG), on-call paging reduction (STRONG). Full copy in the `QUESTIONS` array.

#### Center pane — "How did I get this answer?" drawer
Pinned to the bottom of the center pane (`flex: none`), `border-top: 1px solid var(--line)`, background
`oklch(0.985 0.002 250)`.
- **Collapsed (default):** a single 11px mono row, `padding: 9px 24px`, `justify-content: space-between`:
  chevron + "How did I get this answer?" on the left, "claude-sonnet-4.5 · 11.4s · $0.21" in `--muted-2` on the
  right. Hover darkens the label to `--ink`.
- **Expanded:** a 5-column grid (`repeat(5, 1fr)`, 18px gap) above a 1px top rule, `padding: 4px 24px 16px`.
  Each column: mono 9.5px uppercase 0.08em caption, a primary value in `--ink-2`, and a secondary value in
  `--muted`.

| Column | Primary | Secondary |
|---|---|---|
| Model | claude-sonnet-4.5 | temp 0.2 · 2 passes |
| Tokens | 48,210 in / 3,974 out | cache hit 71% |
| Latency | 11.4s total | extract 3.1s · judge 8.3s |
| Cost | $0.21 | $0.63 for all 3 jobs |
| Retrieval | 118 spans · top 0.91 | median 0.63 · cutoff 0.45 |

#### Right pane — chat (360px)
1. **Header** (`padding: 12px 16px`, bottom border): "Ask about this analysis" 12.5px/600 on the left; on the
   right a two-segment scope toggle — a 1px `--line-2` bordered flex with no gap and no radius, each segment
   mono 10px `padding: 4px 8px`. Active segment: background `--ink`, text `oklch(0.99 0 0)`. Inactive: text
   `--muted-2`. Segments: "This job" (default active) / "All jobs". Below, mono 10.5px scope note that changes
   with the toggle:
   - this job → "Scoped to Datadog · 12 requirements, 118 resume spans"
   - all jobs → "Scoped to 3 jobs · 36 requirements, 118 resume spans"
2. **Transcript** (`flex: 1`, scrolls, `padding: 14px 16px`, vertical flex, 16px gap). Two turns.
   - **User turn** — right-aligned column: mono 9.5px uppercase 0.1em "You" label, then a bubble with
     background `oklch(0.955 0.004 250)`, `1px solid oklch(0.92 0.004 250)`, `padding: 9px 11px`,
     12.5px/1.5, `max-width: 290px`. Square corners.
   - **Assistant turn** — left-aligned, no bubble: mono label "Career Intelligence", then body text 12.5px/1.6
     `--ink-2`. Inline citations are two parts: the quoted resume span highlighted in the verdict tint
     (`padding: 1px 3px`) and immediately after it a superscript marker `[1]` in mono 10px
     `oklch(0.45 0.11 250)`, `vertical-align: super`. Under the message, a mono 10px `--muted-2` footnote line
     resolving the marker: "[1] resume p.1, Ingestion Platform · score 0.38".
   - Turn 1 asks why Kubernetes is missing; turn 2 asks how to move 72% → 80%. Copy verbatim in the prototype.
3. **Composer** (`flex: none`, top border, `padding: 10px 16px 12px`):
   - Suggested prompt chips — wrapping flex, 6px gap, `margin-bottom: 9px`. Each chip: `1px solid oklch(0.9
     0.004 250)`, white background, `padding: 4px 8px`, 11px, `--ink-3`; hover border `oklch(0.75 0.008 250)`
     and text `--ink`. Chips: "Where am I weakest here?", "Rewrite my Go bullet", "Compare with Nova Fintech",
     "What should I learn first?".
   - Input row — `1px solid oklch(0.88 0.004 250)`, white, `padding: 8px 10px`, flex with 8px gap: placeholder
     "Ask about a requirement, verdict, or citation…" at 12.5px `oklch(0.68 0.012 250)`, and a mono 10px `⏎`
     affordance at the right.

---

### 2. Empty / first run (artboard `1b`) — shown at 900 × 560, same three-pane system at full width

**Purpose.** No resume indexed yet. Nothing can be analyzed, because every verdict must cite resume text.

- **Rail:** labels remain, content replaced by dashed placeholder blocks (`1px dashed`, heights 34px for the
  resume slot and 52px for two job slots, borders progressively lighter). "+ Add job" is present but dimmed to
  `oklch(0.75 0.012 250)`.
- **Center:** centered column, `max-width: 440px`.
  - Heading "Start with the resume" 19px/600, letter-spacing −0.015em.
  - Body 13px/1.6 `--ink-3`: explains that verdicts cite actual resume spans, so nothing can run until one is
    indexed; jobs can be added after.
  - **Dropzone:** `1px dashed oklch(0.8 0.006 250)`, background `oklch(0.99 0.002 250)`, `padding: 34px 24px`,
    centered. "Drop a PDF or DOCX here" 13.5px/500; below, mono 11px "or **choose a file** · max 10 MB" where
    the link is `oklch(0.35 0.06 250)` with a 1px underline.
  - **"or" divider:** 1px rules either side of a mono 10px uppercase 0.1em "or", 12px gap, `margin: 16px 0`.
  - **Paste option:** `1px solid oklch(0.9 0.004 250)`, `padding: 12px 14px`. "Paste resume text" 12.5px/500 +
    11.5px/1.5 `--muted` note that plain text works and citations will reference line numbers instead of pages.
- **Chat pane:** header title dimmed, mono note "Chat unlocks once a resume is indexed.", disabled composer
  (`1px solid oklch(0.93 0.004 250)`, background `oklch(0.975 0.002 250)`, placeholder `oklch(0.72 0.012 250)`).

### 3. Job analysing in the rail (artboard `1c`) — rail crop, 280 × 560

Only the second job differs from the resting rail. The analysing card keeps its white selected background and
replaces the score with mono 10.5px "— —", then below the company:
- Determinate progress track: 3px tall, background `oklch(0.93 0.004 250)`, fill 45% wide in `--muted`
  (neutral, never a verdict color — progress is not a verdict).
- Status row, mono 10px `--muted`, `justify-content: space-between`: "Analysing · judging 5/12" and "~8s".

No spinner, no shimmer. Progress is reported in requirements judged, because that is the unit the user cares
about. The other two jobs render normally, so scores stay comparable while one is in flight.

### 4. Extraction failed (artboard `1d`) — 1440 × 600

**Purpose.** The Snyk posting could not be read. Analysis is unavailable; chat remains usable at reduced scope.

- **Rail:** the failed job is selected with `box-shadow: inset 3px 0 0 var(--missing)`, its score replaced by
  mono 11px "failed" in `--missing-text`, plus a mono 10px line "Extraction error · 09:21".
- **Center:** header renders normally but reads "0 requirements extracted"; the tabs render with "Interview
  Prep" disabled (`oklch(0.72 0.012 250)`, no pointer). Body holds one error panel, `max-width: 560px`,
  `1px solid oklch(0.9 0.02 25)` with `border-left: 3px solid var(--missing)`, background
  `oklch(0.995 0.004 25)`, `padding: 18px 20px`:
  - Mono 10px uppercase 0.1em "Analysis unavailable" preceded by a 7×7px `--missing` square.
  - Heading 15px/600 "Couldn't read the requirements from this posting".
  - Body 13px/1.6 explaining the login wall and why guessing verdicts is refused.
  - Technical detail block above a 1px rule, mono 11px `--muted`, two lines: "fetch → 403 · 214 bytes returned ·
    attempt 2 of 2" and the URL.
  - Actions, 8px gap: primary "Retry extraction" (background `oklch(0.24 0.01 250)`, text `oklch(0.99 0 0)`,
    12.5px/500, `padding: 7px 13px`, square) and secondary "Paste posting text instead"
    (`1px solid oklch(0.88 0.004 250)`, transparent).
- **Provenance drawer:** collapsed, right side reads "extraction aborted · 1.2s · $0.00".
- **Chat:** scope toggle is forced to **All jobs**; scope note reads "Scoped to 2 analysed jobs · Snyk
  excluded". A notice block above the transcript (`1px solid oklch(0.93 0.004 250)`, background
  `oklch(0.975 0.002 250)`, `padding: 10px 12px`, 12px/1.55 `--ink-3`) explains chat can cite the resume and the
  two analysed jobs only. One example turn follows, citing a strong span. Chips reduce to "Paste the posting for
  me" and "Compare Datadog vs Nova".

---

## Interactions & Behavior

| Trigger | Result |
|---|---|
| Click a requirement row header | Toggles that row's expanded panel. Independent per row; multiple can be open. Chevron flips `▸` → `▾`. |
| Click a tab | Swaps the center body between Analysis and Interview Prep. Scroll position resets; the job header and score strip stay mounted. |
| Click the scope toggle | Switches chat scope between this job and all jobs; the mono scope note under the header updates. In production this also re-scopes retrieval for the next message. |
| Click the drawer row | Expands/collapses the provenance grid in place; the drawer stays pinned to the bottom of the center pane. |
| Click a job in the rail | Selects it; center and chat re-scope. (Not wired in the prototype — the Datadog row is fixed as selected.) |
| Hover a job row | Background `oklch(0.97 0.003 250)`; selected row does not change on hover. |
| Hover a requirement row | Background `oklch(0.985 0.002 250)`. |
| Hover a chip | Border `oklch(0.75 0.008 250)`, text `--ink`. |
| Hover "+ Add job" / drawer label | Text darkens to `--ink`. |

**Motion.** Essentially none by design. Disclosure and tab swaps are instantaneous; if any transition is added,
keep it to ≤120ms on `background-color` only. No height animations, no fades on content, no spinners — the
analysing state uses a determinate bar.

**Loading.** Per-job, in the rail (state 3). The center pane for an in-flight job should show the header with a
placeholder score and requirements streaming in as they are judged, in verdict-group order.

**Errors.** Extraction failure is job-scoped, never global (state 4): the other jobs stay analysed and chat
stays available with an explicit reduced-scope note. Always surface the technical detail (status code, bytes,
attempt count, URL) — this is a tool whose credibility depends on showing its work.

**Responsive.** Desktop-first and fixed at 1440. Below ~1180 the intended behavior is to collapse the chat pane
into a right-edge drawer over the center pane; below ~900 the rail becomes an overlay. Neither is designed yet
— confirm before implementing.

## State Management

```
selectedJobId: string                 // drives center + chat scope
activeTab: 'analysis' | 'prep'        // per selected job; resets to 'analysis' on job change
expandedRequirements: Set<string>     // requirement ids; defaults to the first partial requirement
provenanceDrawerOpen: boolean         // collapsed by default, persists across job changes
chatScope: 'job' | 'all'              // forced to 'all' when the selected job has no analysis
```

Per-job server data: `{ id, company, title, status: 'analysed'|'analysing'|'failed', score, requirements[],
questions[], provenance, error? }`. Each requirement: `{ id, text, tag: 'required'|'preferred',
verdict: 'strong'|'partial'|'missing', rationale, citation?: { quote, location, score }, gapNote? }`.
Analysing jobs additionally carry `{ judged, total, etaSeconds }`.

Fetching: job list and resume metadata on load; per-job analysis lazily on selection (cache it — re-selecting
must not re-run); chat is streamed per message with the current scope attached. Citation markers in chat
responses arrive as structured spans, not parsed out of text.

## Design Tokens

**Color** — oklch throughout; hex equivalents given for convenience. Neutrals are a cool near-grey at chroma
≤0.012; verdict hues share chroma 0.13–0.16 so no verdict shouts over another.

| Token | oklch | ≈ hex | Use |
|---|---|---|---|
| `--ink` | `oklch(0.22 0.01 250)` | `#2c3138` | Body text, mark, active tab underline, primary button |
| `--ink-2` | `oklch(0.28 0.01 250)` / `oklch(0.3 0.01 250)` | `#3a4048` | Chat body, emphasized meta |
| `--ink-3` | `oklch(0.4 0.012 250)` / `oklch(0.42 0.012 250)` | `#5a616a` | Secondary body copy |
| `--ink-4` | `oklch(0.38 0.012 250)` | `#555c65` | Rationale text |
| `--muted` | `oklch(0.5 0.012 250)` / `oklch(0.55 0.012 250)` | `#767d86` | Mono meta, company names |
| `--muted-2` | `oklch(0.6–0.65 0.012 250)` | `#9097a0` | Captions, provenance, chevrons |
| `--line` | `oklch(0.91 0.004 250)` | `#e3e5e8` | Pane and section borders |
| `--line-2` | `oklch(0.88–0.89 0.004 250)` | `#dcdee1` | Input and chip borders |
| `--line-3` | `oklch(0.93–0.94 0.004 250)` | `#eaecee` | Row separators |
| `--bg` | `oklch(1 0 0)` | `#ffffff` | Center pane |
| `--bg-2` | `oklch(0.985 0.002 250)` | `#fafafb` | Rail, citation blocks, drawer |
| `--bg-3` | `oklch(0.99 0.002 250)` | `#fcfcfd` | Chat pane |
| `--canvas` | `oklch(0.955 0.003 250)` | `#f2f2f4` | Page behind the app frame |
| `--strong` | `oklch(0.62 0.13 155)` | `#3f9c6d` | Strong swatches, bars, citation rule |
| `--strong-text` | `oklch(0.5 0.13 155)` / badge fg `oklch(0.42 0.11 155)` | `#2f7c54` | Strong scores, badge text |
| `--strong-bg` | `oklch(0.96 0.035 155)` | `#e6f4ec` | Strong badge fill |
| `--strong-hl` | `oklch(0.93 0.055 155)` | `#d6efdf` | Strong citation highlight |
| `--partial` | `oklch(0.72 0.13 75)` | `#c58a34` | Partial swatches, bars |
| `--partial-text` | `oklch(0.58 0.13 75)` / badge fg `oklch(0.45 0.1 70)` | `#96681f` | Partial scores, badge text |
| `--partial-bg` | `oklch(0.97 0.04 85)` | `#f8efdc` | Partial badge fill |
| `--partial-hl` | `oklch(0.95 0.06 85)` | `#f6e7c8` | Partial citation highlight |
| `--missing` | `oklch(0.62 0.16 25)` | `#cd5b4c` | Missing swatches, bars, failure rule |
| `--missing-text` | `oklch(0.58 0.16 25)` / badge fg `oklch(0.45 0.14 25)` | `#a24034` | Missing scores, badge text |
| `--missing-bg` | `oklch(0.965 0.03 25)` | `#fbe9e5` | Missing badge fill |
| `--neutral-hl` | `oklch(0.94 0.03 100)` | `#eeecd9` | Neutral citation highlight (prep tab, chat) |
| `--citation-marker` | `oklch(0.45 0.11 250)` | `#3f6394` | Superscript `[n]` markers, links |

Rule: color appears **only** on verdicts, citation highlights, citation markers, and the single primary button.
No brand color, no accent surfaces, no tinted cards.

**Typography** — two families, both Google Fonts.

| Role | Family | Size / weight | Notes |
|---|---|---|---|
| Job title | IBM Plex Sans | 20 / 600 | letter-spacing −0.015em |
| Score readout | IBM Plex Mono | 34 / 500 | line-height 1, letter-spacing −0.02em |
| Prep question | IBM Plex Sans | 15 / 600 | line-height 1.4, −0.01em |
| Requirement text | IBM Plex Sans | 13.5 / 500 | line-height 1.35 |
| Section / product labels | IBM Plex Sans | 13 / 600 | −0.01em |
| Body copy | IBM Plex Sans | 13 / 400 | line-height 1.55–1.6, `text-wrap: pretty`, `max-width: 660px` |
| Chat body | IBM Plex Sans | 12.5 / 400 | line-height 1.6 |
| Rail job title | IBM Plex Sans | 12.5 / 600 | line-height 1.3 |
| Rail company | IBM Plex Sans | 11.5 / 400 | `--muted` |
| Meta / provenance | IBM Plex Mono | 10.5–11.5 / 400 | |
| Uppercase captions | IBM Plex Mono | 9.5–10.5 / 400 | uppercase, letter-spacing 0.08–0.12em |
| Verdict badge | IBM Plex Mono | 10 / 400 | uppercase, 0.08em |

Weights needed: Plex Sans 400/500/600, Plex Mono 400/500. Nothing bolder than 600 anywhere.

**Spacing.** Effective 4px scale, used as: 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28, 34.
Pane padding 14px (rail, chat) / 24px (center). Row padding `11px 4px`. Section gap 22px.

**Radius.** `0` everywhere except the artboard id badges in the canvas, which are prototype chrome and not part
of the UI. Square corners are deliberate — they read as instrument, not consumer app.

**Shadows.** None. The only `box-shadow` in the design is `inset 3px 0 0` used as a selection indicator on rail
rows.

**Borders.** 1px hairlines carry all structure. 2px left rules on citation blocks, 3px on the failure panel,
2px bottom on the active tab.

## Assets
None. No images, no icon set, no illustrations. Every graphic element is a div: verdict swatches are squares,
the fit strip is 12 flex cells, disclosure chevrons are the text characters `▸` / `▾`, and the composer's enter
affordance is `⏎`. If the target codebase has an icon library, chevrons may be swapped for its chevron-right /
chevron-down at 10px — do not introduce any other icons.

## Files

| File | What it is |
|---|---|
| `Career Intelligence.dc.html` | The design reference. Opens directly in a browser; contains all four artboards on one canvas, with tabs, row expansion, the scope toggle, and the provenance drawer working. |
| `support.js` | Prototype runtime required to render the HTML file locally. Not part of the implementation. |

Inside the HTML, the copy and data live in the logic script at the bottom of the file: `STRONG`, `PARTIAL`,
`MISSING` (the 12 requirements with rationales, quotes, locations, and retrieval scores) and `QUESTIONS` (the 5
prep questions). Take all product copy from there verbatim.
