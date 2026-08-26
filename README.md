# Filing Copilot

A small agent over SEC filings that does two things, and decides which per question:

1. **Retrieve** — navigates a reasoning-based document index (a *PageIndex*-style
   tree of the filing's Items) and answers from the relevant section, with a citation.
2. **Analyze** — when a question needs computation, it picks a structured dataset
   extracted from the filing, loads an **analysis skill** (a how-to), writes pandas
   code, runs it in an **isolated Docker sandbox**, and returns a computed artifact
   (table) cited back to the source.

Everything is stored in **Postgres**. The retrieval index is built from the filing
text; the analysis datasets come from the filing's financial statements (via SEC
XBRL company facts).

> The tree-navigation retrieval is an implementation of the *PageIndex* idea
> (reasoning-based, vectorless RAG — see github.com/VectifyAI/PageIndex). The rest
> (skill-driven analysis, the sandbox, the UI) is built around it.

## Layout
```
app/
  config.py        settings from .env
  database.py      SQLAlchemy models: filings, nodes (the tree), datasets
  llm.py           Anthropic wrapper
  api.py           FastAPI: /ingest /filings /ask  (+ serves the UI)
  ingest/          getting filings in
    edgar.py       fetch filing text + XBRL financials from SEC EDGAR
    pipeline.py    split into Item sections, summarize, store + datasets
  agent/           answering questions
    core.py        route retrieve vs analyze  (the answer() entry point)
    retrieve.py    retrieval path: navigate the tree, answer from a section
    analyze.py     analysis path: skill -> pandas -> sandbox -> artifact
    sandbox.py     run analysis code in Docker (no network, capped, non-root)
    skills.py      load the skill files
skills/            analysis how-tos (margin_analysis, yoy_growth, ratio_analysis, common_size, guardrails)
web/               the UI (talks to the API)
cli.py             ingest / ask from the terminal
docs/              HTML walkthroughs (this codebase; the ZoomRx architecture)
```

## Run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY

docker compose up -d db       # Postgres on localhost:5433
python cli.py build-sandbox   # build the analysis sandbox image

# ingest a filing, then ask
python cli.py ingest AAPL 10-K
python cli.py ask 1 "How has operating margin trended?"

# or run the app + UI
uvicorn app.api:app --reload   # open http://localhost:8000
```

## Spec-driven development

[`docs/SPEC.md`](docs/SPEC.md) is the source of truth for the product. New work is
described as a **delta** against it; a coding agent implements the delta, then folds
it back into the spec (see `docs/SPEC.md` §14). Architecture walkthroughs also live
in [`docs/`](docs/).

## Adding an analysis skill
Drop a markdown file in `skills/` describing the method + guardrails and the
`result` output contract (see the existing ones). The router will offer it
automatically. No code change needed.
