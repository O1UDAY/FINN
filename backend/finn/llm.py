"""Two-tier model router with a persistent cache.

tier="cheap"  -> bulk extraction / classification / one-liners (Haiku or Gemini Flash-Lite)
tier="strong" -> judgement calls only: promised-vs-delivered, bull/bear (Sonnet or Gemini Flash)

Every call is cached by sha256(model + prompt), so re-opening a card or re-running research costs nothing.
With no key configured, `available()` is False and callers fall back to deterministic output.
"""
import hashlib
import json
import os
import re
from datetime import datetime

import requests

from .db import connect

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("FINN_ANTHROPIC_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

MODELS = {
    "anthropic": {"cheap": "claude-haiku-5-5", "strong": "claude-sonnet-5-5"},
    "gemini": {"cheap": "gemini-2.5-flash-lite", "strong": "gemini-2.5-flash"},
}
# USD per 1M tokens (input, output), for the cost log only.
PRICES = {
    "claude-haiku-5-5": (1.0, 5.0), "claude-sonnet-5-5": (3.0, 15.0),
    "gemini-2.5-flash-lite": (0.10, 0.40), "gemini-2.5-flash": (0.30, 2.50),
}


def provider():
    pref = os.getenv("FINN_LLM_PROVIDER")
    if pref == "gemini" and GEMINI_KEY:
        return "gemini"
    if ANTHROPIC_KEY:
        return "anthropic"
    if GEMINI_KEY:
        return "gemini"
    return None


def available() -> bool:
    return provider() is not None


def _anthropic(model, system, prompt, max_tokens):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=180,
    )
    r.raise_for_status()
    j = r.json()
    text = "".join(b.get("text", "") for b in j["content"])
    return text, j["usage"]["input_tokens"], j["usage"]["output_tokens"]


def _gemini(model, system, prompt, max_tokens):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": GEMINI_KEY},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}},
        timeout=180,
    )
    r.raise_for_status()
    j = r.json()
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    u = j.get("usageMetadata", {})
    return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def complete(prompt: str, tier="cheap", system="You are a precise financial analyst. Be terse.", max_tokens=1500):
    p = provider()
    if not p:
        return None
    model = MODELS[p][tier]
    key = hashlib.sha256(f"{model}\n{system}\n{prompt}".encode()).hexdigest()
    conn = connect()
    hit = conn.execute("SELECT output FROM llm_cache WHERE key=?", (key,)).fetchone()
    if hit:
        return hit["output"]
    text, tin, tout = (_anthropic if p == "anthropic" else _gemini)(model, system, prompt, max_tokens)
    pin, pout = PRICES.get(model, (0, 0))
    cost = (tin * pin + tout * pout) / 1e6
    conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?)",
                 (key, model, text, cost, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return text


def complete_json(prompt: str, tier="cheap", **kw):
    """Ask for JSON and parse it leniently (models sometimes wrap it in prose or code fences)."""
    out = complete(prompt + "\n\nReturn ONLY valid JSON, no prose, no code fences.", tier=tier, **kw)
    if out is None:
        return None
    m = re.search(r"[\[{].*[\]}]", out, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def spend():
    conn = connect()
    rows = conn.execute("SELECT model, COUNT(*) n, ROUND(SUM(cost_usd), 4) usd FROM llm_cache GROUP BY model").fetchall()
    return {"provider": provider(), "by_model": [dict(r) for r in rows],
            "total_usd": round(sum(r["usd"] or 0 for r in rows), 4)}
