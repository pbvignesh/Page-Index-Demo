# Filing Copilot — Specification

**Spec version:** 1.0
**Status:** matches the current implementation.

This document is the source of truth for the product. It is written to support
**spec-driven development**: new work is described as a **delta** against this
spec, a coding agent implements the delta, and the delta is then **folded back**
into the relevant sections here (see [§14 Evolving this spec](#14-evolving-this-spec)).

---

## 1. Overview

Filing Copilot is a small agent over SEC filings (10-K / 10-Q). For each question
it decides between two capabilities:

- **Retrieve** — navigate a reasoning-based document index (a *PageIndex*-style
  tree of the filing's Items) and answer from the relevant section, **cited**.
- **Analyze** — when a question needs computation, pick a structured dataset
  extracted from the filing, load an **analysis skill** (a how-to), have the model
  write pandas, run it in an **isolated Docker sandbox**, and return a computed
  **artifact** (a table) cited to the source.

Filings are ingested once (text → PageIndex tree; financial statements → datasets)
and stored in Postgres. A FastAPI service exposes ingest/list/ask and serves a
single-page web UI.

## 2. Goals & non-goals

**Goals**
- Faithfully demonstrate the two capabilities end to end, on real filings.
- Stay **small, readable, and easy to change** — one clear module per concern,
  descriptive names, minimal dependencies, no framework sprawl.
- Make analysis **safe** (untrusted, model-written code runs only in the sandbox)
  and **grounded** (answers cite a source; computed numbers come from the sandbox).
- Make skills additive: a new analysis type is a new markdown file, no code change.

**Non-goals (deliberately out of scope unless a delta adds them)**
- No authentication, multi-tenancy, or user accounts.
- No vector database — retrieval is tree navigation, not similarity search.
- No streaming responses; `/ask` returns a single JSON object.
- No production hardening of the sandbox (local Docker only; no gVisor/k8s).
- No background jobs / queues; ingest runs synchronously in the request.

## 3. Architecture

```
INGEST (once per filing)
  SEC EDGAR ── filing HTML ──▶ parse text ──▶ split into Item sections (tree nodes)
            └─ XBRL companyfacts ──▶ income statement + balance sheet datasets
  ──▶ Postgres (filings, nodes, datasets)

ASK (per question)
  question ─▶ router ─┬─ retrieve: navigate tree → answer from a section (cited)
                      └─ analyze:  pick dataset + skill → model writes pandas
                                   → Docker sandbox → artifact (cited)
```

Two packages mirror this: `app/ingest/` (getting filings in) and `app/agent/`
(answering questions). See [§12 File layout](#12-file-layout).

## 4. Data model

Three tables (`app/database.py`), all owned by one filing.

**Filing**
| field | type | notes |
|---|---|---|
| id | int PK | |
| ticker | str | uppercased |
| cik | str | 10-digit, zero-padded |
| company | str | |
| form | str | "10-K" / "10-Q" |
| period | str | report date, e.g. "2025-09-27" |
| accession | str | SEC accession number (dedupe key with ticker+form) |
| created_at | datetime | |

**Node** (one Item section — a node of the PageIndex tree)
| field | type | notes |
|---|---|---|
| id | int PK | |
| filing_id | FK | |
| order_ix | int | document order |
| item | str | e.g. "Item 1A" |
| title | str | e.g. "Risk Factors" |
| summary | str | 1–2 sentence summary, used for tree search |
| text | str | section body, capped at 30,000 chars |

**Dataset** (a structured table extracted from the filing)
| field | type | notes |
|---|---|---|
| id | int PK | |
| filing_id | FK | |
| name | str | "income_statement" \| "balance_sheet" |
| label | str | human label + citation, e.g. "Item 8 · Income Statement (XBRL)" |
| columns | json | `["line_item", "FY2022", "FY2023", ...]` |
| rows | json | `[["Revenues", 394328000000, ...], ...]`; values are **raw USD** or `null` |

## 5. Ingest (`app/ingest/`)

`ingest(ticker, form="10-K", summarize=True) -> filing_id`

1. `edgar.resolve_cik(ticker)` → (cik, company) via SEC `company_tickers.json`.
2. `edgar.latest_filing(cik, form)` → the most recent matching filing (accession,
   primary document, period) via the submissions API.
3. **Dedupe**: if a Filing with the same (ticker, form, accession) exists, return it.
4. `edgar.fetch_filing_text(...)` → filing HTML → text (BeautifulSoup, scripts/styles stripped).
5. `pipeline._split_items(text)` → the PageIndex nodes. A filing repeats every item
   (table-of-contents line + body); for each item code we keep the **longest** span
   (the body). Titles fall back to a canonical 10-K item map.
6. `pipeline._summarize(...)` → a short LLM summary per node (skipped, empty string,
   if no API key — ingest still works offline).
7. `edgar.fetch_financials(cik)` → datasets from **XBRL company facts**. Values are
   keyed by each value's **period end** (not the filing's `fy`, which is unreliable);
   income-statement concepts are limited to ~full-year periods; balance-sheet
   concepts take the year-end value; candidate tags are merged; latest restatement wins.
   Concepts are declared in `edgar.INCOME_STATEMENT_CONCEPTS` / `BALANCE_SHEET_CONCEPTS`
   as `(display_name, [candidate_us_gaap_tags])`.
8. Persist Filing + Nodes + Datasets; return the filing id.

**Contract:** ingest is idempotent per (ticker, form, accession). Network calls go
to SEC with the configured `SEC_USER_AGENT`.

## 6. Agent (`app/agent/`)

`answer(filing_id, question) -> Response` (`agent/core.py`) is the entry point.

1. `_load_filing` — load nodes (item/title/summary/text) and datasets (name/label/columns/rows).
2. `_route` — one LLM call returns a **plan**: `{"mode": "retrieve"|"analyze",
   "item": <Item|null>, "dataset": <name|null>, "skill": <name|null>}`. It prefers
   ANALYZE for numeric/trend/margin/ratio questions when a dataset exists. On failure,
   `_fallback_plan` keyword-guesses.
3. Dispatch: `analyze` (if mode=analyze and datasets exist) else `retrieve`.

### 6.1 Retrieve (`agent/retrieve.py`)
Pick the planned Item node (fallback: first node). One LLM call answers using only
that section's text (first 6,000 chars), cited as `Item X · Title`.

### 6.2 Analyze (`agent/analyze.py`)
1. Resolve the dataset (fallback: first) and skill (fallback: `margin_analysis` for
   income statement, else `ratio_analysis`).
2. `_write_code` — one LLM call, prompted with the shared **guardrails** skill + the
   selected skill + the dataset's columns/rows + the question. Returns Python only
   (code fences stripped).
3. `sandbox.run(code, dataset)` — execute in Docker (see [§8](#8-sandbox)).
4. On success, one LLM call writes a 1–2 sentence finding from the result numbers.
5. On sandbox failure, return an honest "couldn't compute" answer (still carries the
   code + a `Sandbox → error` trace step).

### 6.3 Response schema (returned by `answer`, `/ask`)
```json
{
  "mode": "retrieve" | "analyze",
  "answer": "string",
  "citation": "Item 8 · Income Statement (XBRL)",
  "node": {"item": "Item 1A", "title": "Risk Factors"} | null,
  "artifact": {"columns": ["..."], "rows": [["..."]], "summary": "..."} | null,
  "skill": "margin_analysis" | null,
  "code": "pandas source" | null,
  "trace": [{"label": "Router → analyze", "sub": "..."}]
}
```
`node` is set on retrieve; `artifact`/`skill`/`code` are set on analyze.

## 7. Skills (`app/agent/skills.py` + `skills/*.md`)

A **skill** is a markdown file in `skills/` describing how to perform one kind of
analysis. `skills.py` loads them; `list_skills()` excludes shared files; `catalog()`
gives the router one line per selectable skill (its first non-heading line).

- **`guardrails.md`** (shared, always included) — units ($M), periods, missing data,
  grounding, and the **output contract**.
- Selectable: **`margin_analysis`**, **`yoy_growth`**, **`ratio_analysis`**, **`common_size`**.

**Output contract (every analysis skill).** The code the model writes runs against a
pandas DataFrame `df` (the dataset) and must assign:
```python
result = {
    "columns": ["Line item", "FY2023", "FY2024", "FY2025"],  # display headers
    "rows": [["Revenue", "1,204", "1,405", "1,613"], ...],    # display strings
    "summary": "one plain-English sentence with the key finding",
}
```

**Adding a skill = adding a `skills/<name>.md` file** with a description first line,
a method, and the output contract. The router offers it automatically; no code change.

## 8. Sandbox (`app/agent/sandbox.py`)

`run(code, dataset, timeout=35) -> {"ok": bool, "result": {...}} | {"ok": false, "error": str}`

- Writes `dataset.json` + a harness `main.py` to a temp dir. The harness loads `df`,
  runs the code (which must set `result`), and prints one JSON line.
- Executes: `docker run --rm --network none --memory 512m --cpus 1 --pids-limit 128
  -v <tmp>:/work:ro <SANDBOX_IMAGE> python /work/main.py`.
- **Isolation contract:** no network, capped memory/CPU/processes, read-only mount,
  non-root user (from `Dockerfile.sandbox`: `python:3.11-slim` + pandas). Timeout kills
  runaways. Docker-missing and timeout are returned as `{"ok": false, "error": ...}`.
- `build_image()` builds the image (`python cli.py build-sandbox`).

## 9. API (`app/api.py`)

| method | path | request | response |
|---|---|---|---|
| GET | `/` | — | the web UI (`web/index.html`) |
| GET | `/filings` | — | `[{id, ticker, company, form, period}]` |
| GET | `/filings/{id}/outline` | — | `{nodes: [{item, title, summary}], datasets: [{name, label, columns}]}` |
| POST | `/ingest` | `{ticker, form="10-K"}` | `{id, ticker, company, form, period, nodes, datasets}` |
| POST | `/ask` | `{filing_id, question}` | the [§6.3 Response schema](#63-response-schema-returned-by-answer-ask) |

CORS is open (dev). Serializers (`filing_summary`, `node_summary`, `dataset_summary`)
turn ORM objects into plain dicts.

## 10. Web UI (`web/index.html`)

Single self-contained page (light, professional theme). Three panes:
- **Left** — corpus (from `/filings`) + the PageIndex outline (from `/filings/{id}/outline`).
- **Center** — chat; suggested chips and free text both call `/ask`; analysis answers
  render an artifact table + a "View computation" toggle showing the generated code.
- **Right** — the agent trace for the last answer (+ the sandbox constraints for analyze).
- **Ingest modal** — posts `/ingest`, shows the pipeline animation, refreshes the corpus.

## 11. Configuration (`app/config.py`, `.env`)

| var | default | purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/pageindex` | Postgres |
| `ANTHROPIC_API_KEY` | — | required for LLM calls |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5-20250929` | model id |
| `ANTHROPIC_BASE_URL` | — | optional gateway; empty is cleared so the SDK default is used |
| `SANDBOX_IMAGE` | `pageindex-sandbox` | analysis sandbox image |
| `SEC_USER_AGENT` | `Page-Index-Demo contact@example.com` | SEC requires a descriptive UA |

## 12. File layout

```
app/
  config.py        settings from .env
  database.py      SQLAlchemy models: filings, nodes, datasets
  llm.py           Anthropic wrapper (complete, complete_json)
  api.py           FastAPI + serves the UI
  ingest/
    edgar.py       SEC EDGAR: filing text + XBRL financials
    pipeline.py    split into Item sections, summarize, store + datasets
  agent/
    core.py        answer(): load filing, route retrieve vs analyze
    retrieve.py    retrieval path
    analyze.py     analysis path (skill → pandas → sandbox → artifact)
    sandbox.py     Docker runner
    skills.py      load skill files
skills/            analysis how-tos (+ guardrails)
web/index.html     the UI
cli.py             ingest / ask / build-sandbox
docs/              HTML walkthroughs
Dockerfile.sandbox · docker-compose.yml (Postgres)
```

## 13. Conventions

- **Readability first**: descriptive names (no one-letter locals), explicit loops over
  dense comprehensions, small functions, sparse comments that explain *why*.
- **Minimal dependencies**; keep each file focused on one concern.
- **Commits**: short, neutral, human-sounding messages. No AI-tool attribution or trailers.

---

## 14. Evolving this spec

This spec drives development. The loop:

1. **Describe the change as a delta.** Write a short delta that references the spec
   sections it touches — what behavior/contract/file changes, and the acceptance check.
   (Use the template below.) A delta does not need to restate unchanged parts.
2. **Implement.** The coding agent reads this spec + the delta, makes the changes so the
   delta holds, and verifies (imports succeed; retrieve + analyze still work end to end;
   any new behavior demonstrably works).
3. **Fold the delta back in.** Update the affected sections of this spec so it again
   describes the whole product as-built, bump **Spec version**, and add one line to the
   Changelog. The standalone delta is then discarded — the spec is always current.

**Delta template**
```
# Delta: <short title>
Spec sections touched: <e.g. §7 Skills, §9 API>
Change: <what should now be true that isn't yet>
Files likely involved: <best guess>
Acceptance: <how we'll know it's done — a check or example>
Out of scope: <optional guardrails>
```

**Changelog**
- v1.0 — initial spec, matches the first implementation (ingest + retrieve + analyze,
  4 analysis skills, FastAPI + UI, Docker sandbox).
