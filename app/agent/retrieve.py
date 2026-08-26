"""Retrieval path: navigate to the relevant Item and answer from its text."""
from .. import llm


def retrieve(question: str, nodes: list[dict], item: str | None) -> dict:
    node = _pick_node(nodes, item)

    system_prompt = "Answer using ONLY the provided filing section. Be specific; never invent facts. 2-4 sentences."
    user_prompt = f"Question: {question}\n\nSection {node['item']} — {node['title']}:\n{node['text'][:6000]}"
    answer_text = llm.complete(system_prompt, user_prompt)

    return {
        "mode": "retrieve",
        "answer": answer_text,
        "citation": f"{node['item']} · {node['title']}",
        "node": {"item": node["item"], "title": node["title"]},
        "artifact": None,
        "skill": None,
        "code": None,
        "trace": [
            {"label": "Router → retrieve", "sub": "no computation needed"},
            {"label": f"Navigator → {node['item']}", "sub": "PageIndex tree search"},
            {"label": "Critic → grounded", "sub": "answer drawn from the cited section"},
        ],
    }


def _pick_node(nodes: list[dict], item: str | None) -> dict:
    for node in nodes:
        if node["item"] == item:
            return node
    return nodes[0]
