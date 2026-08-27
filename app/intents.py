"""Intent tags — the RAG-style routing layer.

Sections and datasets are tagged with intents at ingest (`annotate_*`). When a
question comes in it is classified into intents (`classify_question`), and only
the sections/datasets whose intents overlap are passed to the agent
(`select_candidates`). No vector DB — the tags are the index.
"""
from . import llm

# Controlled vocabulary: intent -> one-line description (used by both the
# annotator and the question classifier). Keep this small.
VOCABULARY = {
    "business_overview": "what the company does — products, services, segments, strategy",
    "risk_factors": "risks the company faces (macro, competition, supply chain, regulatory)",
    "legal": "legal proceedings, litigation, regulatory actions",
    "mdna": "management's discussion of results, drivers, outlook, liquidity",
    "market_risk": "interest-rate, foreign-currency, and market-risk exposure",
    "financials": "the financial statements and reported figures",
    "revenue_growth": "revenue, sales, top-line growth, YoY, CAGR",
    "profitability_margins": "margins, operating/net income, profitability",
    "liquidity_capital": "balance sheet, assets, liabilities, cash, leverage, liquidity",
    "governance": "board, executives, compensation, ownership, controls",
    "segments": "business or geographic segment breakdowns",
}

# Keyword fallback for question classification if the LLM call fails.
_KEYWORDS = {
    "risk_factors": ["risk", "threat", "headwind", "exposure"],
    "profitability_margins": ["margin", "profit", "operating income", "net income"],
    "revenue_growth": ["revenue", "sales", "growth", "cagr", "yoy", "top line"],
    "liquidity_capital": ["balance sheet", "asset", "liabilit", "cash", "debt", "leverage", "ratio", "liquidity"],
    "mdna": ["outlook", "guidance", "driver", "discussion"],
    "legal": ["legal", "lawsuit", "litigation"],
    "governance": ["board", "executive", "compensation", "ownership", "governance"],
    "segments": ["segment", "geograph"],
    "business_overview": ["business", "product", "what does", "overview"],
}

_MAX_NODES = 4


def _catalog_text() -> str:
    lines = []
    for name, description in VOCABULARY.items():
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def _valid(intents) -> list[str]:
    return [i for i in intents if i in VOCABULARY]


# --- annotation (at ingest) ---

def annotate_node(item: str, title: str, summary: str) -> list[str]:
    """Intents for one section — classified by the LLM from its heading + summary."""
    return _llm_tag(f"{item} — {title}\n{summary}")


def annotate_dataset(name: str, label: str = "", columns: list[str] | None = None) -> list[str]:
    """Intents for one dataset — classified by the LLM from its name, label, and columns."""
    columns = columns or []
    return _llm_tag(f"dataset: {name} — {label}\ncolumns: {', '.join(columns)}", default="financials")


def _llm_tag(content: str, default: str = "business_overview") -> list[str]:
    system = "Tag this SEC-filing content with 1-3 intents from the list. Return only intents that clearly apply."
    user = f'Intents:\n{_catalog_text()}\n\nContent:\n{content}\n\nReturn JSON: {{"intents": ["<intent>", ...]}}'
    try:
        tags = _valid(llm.complete_json(system, user, max_tokens=120).get("intents", []))
        return tags or [default]
    except Exception:
        return [default]


# --- classification + selection (at query time) ---

def classify_question(question: str) -> list[str]:
    system = "Classify a question about a SEC filing into 1-2 intents from the list. Return only intents that clearly apply."
    user = f'Intents:\n{_catalog_text()}\n\nQuestion: {question}\n\nReturn JSON: {{"intents": ["<intent>", ...]}}'
    try:
        tags = _valid(llm.complete_json(system, user, max_tokens=120).get("intents", []))
        if tags:
            return tags
    except Exception:
        pass
    return _keyword_fallback(question)


def _keyword_fallback(question: str) -> list[str]:
    lowered = question.lower()
    hits = []
    for intent, words in _KEYWORDS.items():
        if any(word in lowered for word in words):
            hits.append(intent)
    return hits


def select_candidates(nodes: list[dict], datasets: dict, intents: list[str], max_nodes: int = _MAX_NODES):
    """Return (candidate_nodes, candidate_datasets) whose intents overlap the
    question's intents. Falls back to a small default set if nothing matches."""
    wanted = set(intents)

    matched_nodes = []
    for node in nodes:
        if wanted & set(node.get("intents", [])):
            matched_nodes.append(node)
    if not matched_nodes:
        matched_nodes = nodes[:max_nodes]  # fallback: the first few sections
    matched_nodes = matched_nodes[:max_nodes]

    matched_datasets = {}
    for name, dataset in datasets.items():
        if wanted & set(dataset.get("intents", [])):
            matched_datasets[name] = dataset
    if not matched_datasets:
        matched_datasets = datasets  # fallback: all datasets (there are only a couple)

    return matched_nodes, matched_datasets
