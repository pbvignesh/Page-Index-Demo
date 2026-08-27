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

# Deterministic Item -> intents (fast path; anything unmapped is tagged by the LLM).
ITEM_INTENTS = {
    "Item 1": ["business_overview"],
    "Item 1A": ["risk_factors"],
    "Item 3": ["legal"],
    "Item 7": ["mdna", "profitability_margins", "revenue_growth"],
    "Item 7A": ["market_risk"],
    "Item 8": ["financials"],
    "Item 9A": ["governance"],
    "Item 10": ["governance"],
    "Item 11": ["governance"],
    "Item 12": ["governance"],
}
DATASET_INTENTS = {
    "income_statement": ["financials", "revenue_growth", "profitability_margins"],
    "balance_sheet": ["financials", "liquidity_capital"],
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
    """Intents for one section — deterministic for canonical Items, LLM otherwise."""
    if item in ITEM_INTENTS:
        return list(ITEM_INTENTS[item])
    return _llm_tag(f"{item} — {title}\n{summary}")


def annotate_dataset(name: str) -> list[str]:
    return list(DATASET_INTENTS.get(name, ["financials"]))


def _llm_tag(section_text: str) -> list[str]:
    system = "Tag a SEC-filing section with 1-3 intents from the list. Return only intents that clearly apply."
    user = f'Intents:\n{_catalog_text()}\n\nSection:\n{section_text}\n\nReturn JSON: {{"intents": ["<intent>", ...]}}'
    try:
        tags = _valid(llm.complete_json(system, user, max_tokens=120).get("intents", []))
        return tags or ["business_overview"]
    except Exception:
        return ["business_overview"]


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
