"""Thin Anthropic wrapper. Two calls: free text, and best-effort JSON."""
import json
import re

import anthropic

from . import config

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, base_url=config.ANTHROPIC_BASE_URL)
    return _client


def complete(system: str, user: str, max_tokens: int = 1500) -> str:
    msg = client().messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()


def complete_json(system: str, user: str, max_tokens: int = 1500):
    txt = complete(system, user + "\n\nRespond with ONLY valid JSON, no prose.", max_tokens)
    return _extract_json(txt)


def _extract_json(txt: str):
    txt = txt.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", txt, re.S)
    if m:
        txt = m.group(1).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a != -1 and b != -1:
        txt = txt[a:b + 1]
    return json.loads(txt)
