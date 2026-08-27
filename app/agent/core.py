"""The agent entry point: load the filing, route the question, and hand off to
the retrieve or analyze path."""
import re

from .. import llm
from .. import intents as intents_mod
from ..database import SessionLocal, Filing
from . import skills, retrieve as retrieve_path, analyze as analyze_path


def answer(filing_id: int, question: str) -> dict:
    filing = _load_filing(filing_id)

    # RAG-style pre-filter: classify the question's intent, then pass only the
    # matching sections/datasets to the router (not the whole filing).
    question_intents = intents_mod.classify_question(question)
    candidate_nodes, candidate_datasets = intents_mod.select_candidates(
        filing["nodes"], filing["datasets"], question_intents
    )

    plan = _route(question, candidate_nodes, candidate_datasets)
    if plan.get("mode") == "analyze" and candidate_datasets:
        result = analyze_path.analyze(question, candidate_datasets, plan.get("dataset"), plan.get("skill"))
    else:
        result = retrieve_path.retrieve(question, candidate_nodes, plan.get("item"))

    intent_label = ", ".join(question_intents) if question_intents else "general"
    result["trace"] = [
        {"label": f"Intent → {intent_label}", "sub": "classified from the question"},
        {"label": "Select by intent", "sub": f"{len(candidate_nodes)} of {len(filing['nodes'])} sections"},
    ] + result["trace"]
    return result


def _load_filing(filing_id: int) -> dict:
    with SessionLocal() as session:
        filing = session.get(Filing, filing_id)
        if filing is None:
            raise ValueError("filing not found")

        ordered_nodes = sorted(filing.nodes, key=lambda node: node.order_ix)
        nodes = []
        for node in ordered_nodes:
            nodes.append({"item": node.item, "title": node.title, "summary": node.summary,
                          "text": node.text, "intents": node.intents})

        datasets = {}
        for dataset in filing.datasets:
            datasets[dataset.name] = {"label": dataset.label, "columns": dataset.columns,
                                      "rows": dataset.rows, "intents": dataset.intents}

        return {"company": filing.company, "form": filing.form, "nodes": nodes, "datasets": datasets}


def _route(question: str, nodes: list[dict], datasets: dict) -> dict:
    section_lines = []
    for node in nodes:
        section_lines.append(f"- {node['item']}: {node['title']} — {node['summary'][:120]}")
    section_list = "\n".join(section_lines)

    dataset_lines = []
    for name, dataset in datasets.items():
        dataset_lines.append(f"- {name}: columns {dataset['columns']}")
    dataset_list = "\n".join(dataset_lines) or "(none)"

    system_prompt = (
        "You route a question about one SEC filing to RETRIEVE (answer from a section's narrative "
        "text) or ANALYZE (compute a metric over a structured financial dataset with an analysis "
        "skill). Prefer ANALYZE when the question asks for numbers, trends, growth, margins, or "
        "ratios and a suitable dataset exists."
    )
    user_prompt = (
        f"Question: {question}\n\nSections:\n{section_list}\n\nDatasets:\n{dataset_list}\n\n"
        f"Analysis skills:\n{skills.catalog()}\n\n"
        'Return JSON: {"mode":"retrieve"|"analyze","item":<Item or null>,'
        '"dataset":<name or null>,"skill":<name or null>}'
    )
    try:
        return llm.complete_json(system_prompt, user_prompt, max_tokens=300)
    except Exception:
        return _fallback_plan(question, datasets)


def _fallback_plan(question: str, datasets: dict) -> dict:
    """If the router call fails, keyword-guess retrieve vs analyze."""
    looks_analytical = re.search(r"margin|growth|ratio|trend|revenue|cagr|common.?size|yoy", question, re.I)
    if looks_analytical and datasets:
        return {"mode": "analyze", "item": None, "dataset": next(iter(datasets)), "skill": None}
    return {"mode": "retrieve", "item": None, "dataset": None, "skill": None}
