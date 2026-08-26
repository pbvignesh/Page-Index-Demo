"""FastAPI surface: ingest a filing, list filings, get an outline, ask a question.
Also serves the web UI at /."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent
from . import ingest as ingest_mod
from .db import SessionLocal, Filing, init_db

WEB = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Filing Copilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/filings")
def filings():
    with SessionLocal() as s:
        return [{"id": f.id, "ticker": f.ticker, "company": f.company, "form": f.form, "period": f.period}
                for f in s.query(Filing).order_by(Filing.id).all()]


@app.get("/filings/{fid}/outline")
def outline(fid: int):
    with SessionLocal() as s:
        f = s.get(Filing, fid)
        if not f:
            return {"nodes": [], "datasets": []}
        return {
            "nodes": [{"item": n.item, "title": n.title, "summary": n.summary}
                      for n in sorted(f.nodes, key=lambda n: n.order_ix)],
            "datasets": [{"name": d.name, "label": d.label, "columns": d.columns} for d in f.datasets],
        }


class IngestReq(BaseModel):
    ticker: str
    form: str = "10-K"


@app.post("/ingest")
def do_ingest(req: IngestReq):
    fid = ingest_mod.ingest(req.ticker, req.form)
    with SessionLocal() as s:
        f = s.get(Filing, fid)
        return {"id": f.id, "ticker": f.ticker, "company": f.company, "form": f.form,
                "period": f.period, "nodes": len(f.nodes), "datasets": len(f.datasets)}


class AskReq(BaseModel):
    filing_id: int
    question: str


@app.post("/ask")
def ask(req: AskReq):
    return agent.answer(req.filing_id, req.question)
