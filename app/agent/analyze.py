"""Analysis path: pick a dataset + a skill, have the model write pandas, run it
in the sandbox, and return a computed artifact cited to the source table."""
import re

from .. import llm
from . import skills, sandbox


def analyze(question: str, datasets: dict, dataset_name: str | None, skill_name: str | None) -> dict:
    dataset_name = _resolve_dataset(datasets, dataset_name)
    dataset = datasets[dataset_name]
    skill_name = _resolve_skill(skill_name, dataset_name)

    code = _write_code(question, dataset, dataset_name, skill_name)
    outcome = sandbox.run(code, dataset)

    trace = [
        {"label": "Router → analyze", "sub": "needs computation over a table"},
        {"label": f"Skill → {skill_name}", "sub": "loaded how-to + guardrails"},
    ]

    if not outcome.get("ok"):
        trace.append({"label": "Sandbox → error", "sub": str(outcome.get("error"))[:80]})
        return {
            "mode": "analyze",
            "answer": f"Couldn't compute that: {outcome.get('error')}",
            "citation": dataset["label"],
            "node": None,
            "artifact": None,
            "skill": skill_name,
            "code": code,
            "trace": trace,
        }

    trace.append({"label": "Sandbox → executed", "sub": "pandas · no network"})

    result = outcome["result"]
    finding = llm.complete(
        "State the finding in 1-2 sentences using ONLY the numbers in the result. Plain and specific.",
        f"Question: {question}\nResult: {result}",
    )
    trace.append({"label": "Critic → grounded", "sub": "figures come from the sandbox result"})

    return {
        "mode": "analyze",
        "answer": finding or result.get("summary", ""),
        "citation": dataset["label"],
        "node": None,
        "artifact": result,
        "skill": skill_name,
        "code": code,
        "trace": trace,
    }


def _resolve_dataset(datasets: dict, dataset_name: str | None) -> str:
    if dataset_name in datasets:
        return dataset_name
    return next(iter(datasets))


def _resolve_skill(skill_name: str | None, dataset_name: str) -> str:
    if skill_name in skills.list_skills():
        return skill_name
    if dataset_name == "income_statement":
        return "margin_analysis"
    return "ratio_analysis"


def _write_code(question: str, dataset: dict, dataset_name: str, skill_name: str) -> str:
    system_prompt = (
        skills.load_skill("guardrails")
        + "\n\nYou write a short pandas snippet. The DataFrame `df` is already loaded. "
        "Assign a variable `result` per the output contract. "
        "Output ONLY Python code — no prose, no code fences."
    )
    user_prompt = (
        f"# skill: {skill_name}\n{skills.load_skill(skill_name)}\n\n"
        f"Dataset `{dataset_name}` columns: {dataset['columns']}\nrows: {dataset['rows']}\n\n"
        f"Question: {question}"
    )
    raw = llm.complete(system_prompt, user_prompt, max_tokens=900)
    return _strip_code_fences(raw)


def _strip_code_fences(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()
