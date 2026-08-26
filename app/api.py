"""FastAPI surface: ingest a filing, list filings, get an outline, ask a question.
Also serves the web UI at /."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent
from . import ingest as ingest_module
from .database import SessionLocal, Filing, init_db

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Filing Copilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- serializers: turn ORM objects into plain dicts for the JSON responses ---

def filing_summary(filing: Filing) -> dict:
    return {
        "id": filing.id,
        "ticker": filing.ticker,
        "company": filing.company,
        "form": filing.form,
        "period": filing.period,
    }


def node_summary(node) -> dict:
    return {"item": node.item, "title": node.title, "summary": node.summary}


def dataset_summary(dataset) -> dict:
    return {"name": dataset.name, "label": dataset.label, "columns": dataset.columns}


# --- routes ---

@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/filings")
def list_filings():
    with SessionLocal() as session:
        filings = session.query(Filing).order_by(Filing.id).all()

        results = []
        for filing in filings:
            results.append(filing_summary(filing))
        return results


@app.get("/filings/{filing_id}/outline")
def filing_outline(filing_id: int):
    with SessionLocal() as session:
        filing = session.get(Filing, filing_id)
        if filing is None:
            return {"nodes": [], "datasets": []}

        ordered_nodes = sorted(filing.nodes, key=lambda node: node.order_ix)

        nodes = []
        for node in ordered_nodes:
            nodes.append(node_summary(node))

        datasets = []
        for dataset in filing.datasets:
            datasets.append(dataset_summary(dataset))

        return {"nodes": nodes, "datasets": datasets}


class IngestRequest(BaseModel):
    ticker: str
    form: str = "10-K"


@app.post("/ingest")
def ingest_filing(request: IngestRequest):
    filing_id = ingest_module.ingest(request.ticker, request.form)

    with SessionLocal() as session:
        filing = session.get(Filing, filing_id)
        response = filing_summary(filing)
        response["nodes"] = len(filing.nodes)
        response["datasets"] = len(filing.datasets)
        return response


class AskRequest(BaseModel):
    filing_id: int
    question: str


@app.post("/ask")
def ask(request: AskRequest):
    return agent.answer(request.filing_id, request.question)
