"""Thin Anthropic wrapper: a plain-text call, and a best-effort JSON call."""
import json
import re

import anthropic

from . import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, base_url=config.ANTHROPIC_BASE_URL)
    return _client


def complete(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    message = _get_client().messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_blocks = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            text_blocks.append(block.text)
    return "".join(text_blocks).strip()


def complete_json(system_prompt: str, user_prompt: str, max_tokens: int = 1500):
    raw = complete(system_prompt, user_prompt + "\n\nRespond with ONLY valid JSON, no prose.", max_tokens)
    return _extract_json(raw)


def _extract_json(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)
