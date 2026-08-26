"""The agent. Routes a question to one of two paths:
  - retrieve: navigate the PageIndex nodes, answer from a section's text (cited)
  - analyze:  pick a dataset + a skill, write code, run it in the sandbox, and
              return a computed artifact (cited to the source table)
"""
import re

from . import llm, skills, sandbox
from .db import SessionLocal, Filing


def _load(filing_id: int):
    with SessionLocal() as s:
        f = s.get(Filing, filing_id)
        if not f:
            raise ValueError("filing not found")
        nodes = [{"item": n.item, "title": n.title, "summary": n.summary, "text": n.text}
                 for n in sorted(f.nodes, key=lambda n: n.order_ix)]
        datasets = {d.name: {"label": d.label, "columns": d.columns, "rows": d.rows} for d in f.datasets}
        return {"company": f.company, "form": f.form, "nodes": nodes, "datasets": datasets}


def _route(question, nodes, datasets):
    node_list = "\n".join(f"- {n['item']}: {n['title']} — {n['summary'][:120]}" for n in nodes)
    ds_list = "\n".join(f"- {name}: columns {d['columns']}" for name, d in datasets.items()) or "(none)"
    system = ("You route a question about one SEC filing to RETRIEVE (answer from a section's "
              "narrative text) or ANALYZE (compute a metric over a structured financial dataset "
              "with an analysis skill). Prefer ANALYZE when the question asks for numbers, trends, "
              "growth, margins, or ratios and a suitable dataset exists.")
    user = (f"Question: {question}\n\nSections:\n{node_list}\n\nDatasets:\n{ds_list}\n\n"
            f"Analysis skills:\n{skills.catalog()}\n\n"
            'Return JSON: {"mode":"retrieve"|"analyze","item":<Item or null>,'
            '"dataset":<name or null>,"skill":<name or null>}')
    try:
        return llm.complete_json(system, user, max_tokens=300)
    except Exception:
        analyze = bool(re.search(r"margin|growth|ratio|trend|revenue|cagr|common.?size|yoy", question, re.I)) and datasets
        return {"mode": "analyze" if analyze else "retrieve", "item": None,
                "dataset": next(iter(datasets), None), "skill": None}


def _retrieve(question, nodes, item):
    node = next((n for n in nodes if n["item"] == item), None) or nodes[0]
    system = "Answer using ONLY the provided filing section. Be specific; never invent facts. 2-4 sentences."
    answer = llm.complete(system, f"Question: {question}\n\nSection {node['item']} — {node['title']}:\n{node['text'][:6000]}")
    return {
        "mode": "retrieve", "answer": answer,
        "citation": f"{node['item']} · {node['title']}",
        "node": {"item": node["item"], "title": node["title"]},
        "artifact": None, "skill": None, "code": None,
        "trace": [
            {"label": "Router → retrieve", "sub": "no computation needed"},
            {"label": f"Navigator → {node['item']}", "sub": "PageIndex tree search"},
            {"label": "Critic → grounded", "sub": "answer drawn from the cited section"},
        ],
    }


def _analyze(question, datasets, dataset_name, skill_name):
    if dataset_name not in datasets:
        dataset_name = next(iter(datasets))
    ds = datasets[dataset_name]
    if skill_name not in skills.list_skills():
        skill_name = "margin_analysis" if dataset_name == "income_statement" else "ratio_analysis"

    system = (skills.load_skill("guardrails") +
              "\n\nYou write a short pandas snippet. The DataFrame `df` is already loaded. "
              "Assign a variable `result` per the output contract. Output ONLY Python code — no prose, no code fences.")
    user = (f"# skill: {skill_name}\n{skills.load_skill(skill_name)}\n\n"
            f"Dataset `{dataset_name}` columns: {ds['columns']}\nrows: {ds['rows']}\n\n"
            f"Question: {question}")
    code = _strip_code(llm.complete(system, user, max_tokens=900))

    run = sandbox.run(code, ds)
    trace = [
        {"label": "Router → analyze", "sub": "needs computation over a table"},
        {"label": f"Skill → {skill_name}", "sub": "loaded how-to + guardrails"},
        {"label": "Sandbox → executed" if run.get("ok") else "Sandbox → error",
         "sub": "pandas · no network" if run.get("ok") else str(run.get("error"))[:80]},
    ]
    if not run.get("ok"):
        return {"mode": "analyze", "answer": f"Couldn't compute that: {run.get('error')}", "citation": ds["label"],
                "node": None, "artifact": None, "skill": skill_name, "code": code, "trace": trace}

    result = run["result"]
    summary = llm.complete(
        "State the finding in 1-2 sentences using ONLY the numbers in the result. Plain and specific.",
        f"Question: {question}\nResult: {result}")
    trace.append({"label": "Critic → grounded", "sub": "figures come from the sandbox result"})
    return {
        "mode": "analyze", "answer": summary or result.get("summary", ""), "citation": ds["label"],
        "node": None, "artifact": result, "skill": skill_name, "code": code, "trace": trace,
    }


def _strip_code(txt):
    m = re.search(r"```(?:python)?\s*(.*?)```", txt, re.S)
    return (m.group(1) if m else txt).strip()


def answer(filing_id: int, question: str) -> dict:
    f = _load(filing_id)
    plan = _route(question, f["nodes"], f["datasets"])
    if plan.get("mode") == "analyze" and f["datasets"]:
        return _analyze(question, f["datasets"], plan.get("dataset"), plan.get("skill"))
    return _retrieve(question, f["nodes"], plan.get("item"))
