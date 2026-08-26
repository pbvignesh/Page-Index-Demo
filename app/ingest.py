"""Ingest a filing: fetch it, split the text into Item sections (the PageIndex
nodes), summarize each node, pull the structured financials, and persist."""
import re

from . import edgar, llm, config
from .db import SessionLocal, Filing, Node, Dataset, init_db

# canonical 10-K item titles, used when the header line is messy
CANON = {
    "1": "Business", "1A": "Risk Factors", "1B": "Unresolved Staff Comments", "1C": "Cybersecurity",
    "2": "Properties", "3": "Legal Proceedings", "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity", "6": "Selected Financial Data",
    "7": "Management's Discussion and Analysis (MD&A)",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants", "9A": "Controls and Procedures",
    "9B": "Other Information", "10": "Directors, Executive Officers and Governance",
    "11": "Executive Compensation", "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services", "15": "Exhibits and Schedules",
}
_HEADER = re.compile(r"(?im)^\s*item\s+(\d{1,2}[A-Z]?)\b[\.\:\)\-–—\s]*(.*)$")
_MAX_TEXT = 30_000


def _split_items(text: str):
    """Return [{item, title, text}] keeping the largest body per item code."""
    matches = list(_HEADER.finditer(text))
    if not matches:
        return []
    segs = {}
    for i, m in enumerate(matches):
        code = m.group(1).upper()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start():end].strip()
        rawtitle = re.sub(r"\s+", " ", m.group(2)).strip()[:70]
        if code not in segs or len(body) > len(segs[code]["text"]):
            segs[code] = {"item": f"Item {code}", "title": CANON.get(code, rawtitle or code), "text": body[:_MAX_TEXT], "pos": m.start()}
    return sorted(segs.values(), key=lambda s: s["pos"])


def _summarize(item, title, text):
    if not config.ANTHROPIC_API_KEY:
        return ""
    try:
        return llm.complete(
            "You summarize sections of SEC filings for a document index. One or two sentences, plain and specific.",
            f"Section: {item} — {title}\n\n{text[:3000]}\n\nSummarize what this section covers.",
            max_tokens=160,
        )
    except Exception:
        return ""


def ingest(ticker: str, form: str = "10-K", summarize: bool = True) -> int:
    init_db()
    cik, company = edgar.resolve_cik(ticker)
    meta = edgar.latest_filing(cik, form)

    with SessionLocal() as s:
        existing = s.query(Filing).filter_by(ticker=ticker.upper(), form=form, accession=meta["accession"]).one_or_none()
        if existing:
            return existing.id

        text = edgar.fetch_filing_text(cik, meta["accession"], meta["primary_doc"])
        items = _split_items(text)
        financials = edgar.fetch_financials(cik)

        filing = Filing(ticker=ticker.upper(), cik=cik, company=company, form=form,
                        period=meta["period"], accession=meta["accession"])
        for ix, it in enumerate(items):
            summary = _summarize(it["item"], it["title"], it["text"]) if summarize else ""
            filing.nodes.append(Node(order_ix=ix, item=it["item"], title=it["title"], summary=summary, text=it["text"]))
        for name, ds in financials.items():
            filing.datasets.append(Dataset(name=name, label=ds["label"], columns=ds["columns"], rows=ds["rows"]))
        s.add(filing)
        s.commit()
        return filing.id
