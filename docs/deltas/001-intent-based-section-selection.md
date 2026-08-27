# Delta 001 — Intent-based section selection (RAG-style pre-filtering)

**Against:** SPEC v1.0
**Spec sections touched:** §2 Non-goals, §4 Data model, §5 Ingest, §6 Agent, §11 Configuration

---

## Why

Today the router is handed the **entire** catalog of the filing's sections and
datasets and asked to choose ([SPEC §6](../SPEC.md#6-agent-appagent) — `_route`
lists every node + dataset). That doesn't scale as filings and the corpus grow,
and it puts irrelevant context in front of the model.

Move to a **RAG-style flow**: annotate sections with **intents** at ingest time,
classify the question's intent when it's asked, retrieve only the sections whose
intents match, and pass **just those candidates** to the agent — not everything.

## Desired behaviour (what must be true after this delta)

1. Every **Node** and **Dataset** is annotated **at ingest** with one or more
   **intents** drawn from a small, controlled vocabulary.
2. At query time the system **classifies the question** into intent(s), **selects**
   the nodes/datasets whose intents overlap, and passes **only those candidates**
   to the router/agent — the router never sees the full catalog.
3. If nothing matches, it **falls back** to a small default set (never crashes,
   never silently answers from nothing).
4. Both paths (retrieve, analyze) still work end to end; answers stay cited/grounded.
5. The agent **trace** shows the classified intent(s) and how many candidates were
   selected (e.g. "selected 2 of 23 sections").

## Design (suggested — the agent decides the exact implementation)

### Intent vocabulary (controlled, ~8–12)
Define in one place (suggested `app/agent/intents.py`), each with a one-line
description used by both the annotator and the question classifier. Starting set:
`business_overview`, `risk_factors`, `legal`, `mdna`, `market_risk`, `financials`,
`revenue_growth`, `profitability_margins`, `liquidity_capital`, `governance`,
`segments`. Keep it small; do not build a general ontology.

### Ingest annotation (beforehand)
After sections + datasets are built ([SPEC §5](../SPEC.md#5-ingest-appingest)),
tag each:
- **Nodes** — 1–3 intents. A deterministic map for the canonical Items is a fine
  fast path (Item 1A→`risk_factors`, Item 3→`legal`, Item 7→`mdna`,
  Item 7A→`market_risk`, Item 8→`financials`); fall back to an LLM tag (given the
  vocabulary + the node title/summary) for anything unmapped.
- **Datasets** — `income_statement`→`[financials, revenue_growth, profitability_margins]`;
  `balance_sheet`→`[financials, liquidity_capital]`.

### Query-time selection
- `classify_question(question) -> [intent]` — a cheap LLM call against the
  vocabulary (keyword fallback if it fails).
- `select_candidates(nodes, datasets, intents) -> (candidate_nodes, candidate_datasets)`
  — overlap on intents; cap the count; fall back to a small default set if empty.
- The router is then given **only the candidate catalog** and picks the specific
  node/dataset + skill exactly as it does today.

## Contract changes

- **Node** gains `intents: list[str]` (JSON, default `[]`). **Dataset** gains
  `intents: list[str]`. (SPEC §4 tables updated on fold-back.)
- New module (suggested) `app/agent/intents.py`: the vocabulary +
  `classify_question` + `select_candidates`.
- Ingest gains an annotate step (suggested `app/ingest/annotate.py`, or inline in
  `pipeline.py`).
- The `/ask` response `trace` gains an intent/selection step, e.g.
  `{"label": "Intent → risk_factors", "sub": "selected 2 of 23 sections"}`. The
  response **schema shape is otherwise unchanged** ([SPEC §6.3](../SPEC.md#63-response-schema-returned-by-answer-ask)).

## Files likely involved

`app/database.py` (add `intents` columns) · `app/ingest/pipeline.py` (+ annotate
step) · new `app/agent/intents.py` · `app/agent/core.py` (`_route` → classify +
select, then route over candidates) · `docs/SPEC.md` (fold-back).

## Acceptance

- After `python cli.py ingest AAPL 10-K`, **every** node and dataset has a
  non-empty `intents` from the controlled vocabulary.
- "What are the main risk factors?" → trace shows intent `risk_factors`, and the
  router is handed **only** the risk-related section(s), not all 23 (verify via the
  trace, or a debug log of the candidate count).
- "How has operating margin trended?" → intent `profitability_margins`/`financials`
  → `income_statement` dataset selected → analyze runs and produces the same cited
  artifact as today.
- A question matching **no** intent still answers via the fallback set; no crash.
- Both paths remain cited/grounded; nothing else in the product's behaviour changes.

## Out of scope / guardrails

- **No vector DB or embeddings** — intents/tags are the mechanism; the §2 non-goal
  stands. Embeddings may be a future tie-breaker only.
- Keep the vocabulary small (~8–12); no general ontology.
- Existing filings without intents: **re-ingest**, or provide a one-off backfill
  that annotates in place. No live migration needed.
- Do not change the public request/response shapes beyond the added trace step.

## Fold-back (do after implementation, then delete this file)

Update the spec: §4 (Node/Dataset gain `intents`), §5 (ingest annotate step),
§6 (routing = classify → select candidates → route over candidates), add the intent
vocabulary + `app/agent/intents.py` to §12 file layout, note the §2 non-goal nuance.
Bump **Spec version → 1.1** and add a Changelog line:
`v1.1 — intent-based section selection: sections/datasets tagged at ingest; queries classify intent and route over matched candidates only`.
