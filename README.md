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
  config.py   settings from .env
  db.py       SQLAlchemy models: filings, nodes (the tree), datasets
  edgar.py    fetch filing text + XBRL financials from SEC EDGAR
  ingest.py   split into Item sections, summarize, store + datasets
  llm.py      Anthropic wrapper
  skills.py   load skill files
  sandbox.py  run analysis code in Docker (no network, capped, non-root)
  agent.py    route retrieve vs analyze -> cited answer / sandboxed artifact
  api.py      FastAPI: /ingest /filings /ask  (+ serves the UI)
skills/       analysis how-tos (margin_analysis, yoy_growth, ratio_analysis, common_size, guardrails)
web/          the UI (talks to the API)
cli.py        ingest / ask from the terminal
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

## Adding an analysis skill
Drop a markdown file in `skills/` describing the method + guardrails and the
`result` output contract (see the existing ones). The router will offer it
automatically. No code change needed.
