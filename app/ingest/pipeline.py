"""Ingest a filing: fetch it, split the text into Item sections (the PageIndex
nodes), summarize each node, pull the structured financials, and persist."""
import re

from . import edgar
from .. import llm, config, intents
from ..database import SessionLocal, Filing, Node, Dataset, init_db

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


def _split_items(text: str) -> list[dict]:
    """Split the filing into its Item sections. A filing repeats every item (a
    table-of-contents line plus the real body), so for each item we keep the
    longest span — that's the body, not the short TOC reference."""
    headers = list(_HEADER.finditer(text))
    if not headers:
        return []

    sections = {}
    for index, header in enumerate(headers):
        item_code = header.group(1).upper()
        section_start = header.start()
        section_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        section_text = text[section_start:section_end].strip()
        raw_title = re.sub(r"\s+", " ", header.group(2)).strip()[:70]

        previous = sections.get(item_code)
        if previous is None or len(section_text) > len(previous["text"]):
            sections[item_code] = {
                "item": f"Item {item_code}",
                "title": CANON.get(item_code, raw_title or item_code),
                "text": section_text[:_MAX_TEXT],
                "start": section_start,
            }

    return sorted(sections.values(), key=lambda section: section["start"])


def _summarize(item: str, title: str, text: str) -> str:
    """A one/two-sentence summary of a section, used for tree search. Returns an
    empty string if no API key is set (so ingest still works offline)."""
    if not config.ANTHROPIC_API_KEY:
        return ""
    try:
        return llm.complete(
            "You summarize sections of SEC filings for a document index. "
            "One or two sentences, plain and specific.",
            f"Section: {item} — {title}\n\n{text[:3000]}\n\nSummarize what this section covers.",
            max_tokens=160,
        )
    except Exception:
        return ""


def ingest(ticker: str, form: str = "10-K", summarize: bool = True) -> int:
    init_db()
    cik, company = edgar.resolve_cik(ticker)
    filing_meta = edgar.latest_filing(cik, form)

    with SessionLocal() as session:
        existing_filing = (
            session.query(Filing)
            .filter_by(ticker=ticker.upper(), form=form, accession=filing_meta["accession"])
            .one_or_none()
        )
        if existing_filing is not None:
            return existing_filing.id

        filing_text = edgar.fetch_filing_text(cik, filing_meta["accession"], filing_meta["primary_doc"])
        sections = _split_items(filing_text)
        financials = edgar.fetch_financials(cik)

        filing = Filing(
            ticker=ticker.upper(), cik=cik, company=company,
            form=form, period=filing_meta["period"], accession=filing_meta["accession"],
        )

        for index, section in enumerate(sections):
            summary = _summarize(section["item"], section["title"], section["text"]) if summarize else ""
            filing.nodes.append(Node(
                order_ix=index,
                item=section["item"],
                title=section["title"],
                summary=summary,
                text=section["text"],
                intents=intents.annotate_node(section["item"], section["title"], summary),
            ))

        for dataset_name, dataset_data in financials.items():
            filing.datasets.append(Dataset(
                name=dataset_name,
                label=dataset_data["label"],
                columns=dataset_data["columns"],
                rows=dataset_data["rows"],
                intents=intents.annotate_dataset(dataset_name),
            ))

        session.add(filing)
        session.commit()
        return filing.id
