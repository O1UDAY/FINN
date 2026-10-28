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
import time
from contextvars import ContextVar
from datetime import datetime

import requests

from .config import DATA_DIR
from .db import connect

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("FINN_ANTHROPIC_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
# A visitor's own Gemini key, set per request from the X-Gemini-Key header (see app.py). Never stored or logged.
USER_KEY: ContextVar[str | None] = ContextVar("user_gemini_key", default=None)


def gemini_key():
    return USER_KEY.get() or GEMINI_KEY

MODELS = {
    "anthropic": {"cheap": "claude-haiku-5-5", "strong": "claude-sonnet-5-5"},
    # Google retires model names for new keys; override with FINN_GEMINI_CHEAP / FINN_GEMINI_STRONG.
    "gemini": {"cheap": os.getenv("FINN_GEMINI_CHEAP", "gemini-3.5-flash-lite"),
               "strong": os.getenv("FINN_GEMINI_STRONG", "gemini-3.5-flash")},
    "replay": {"cheap": "replay-cheap", "strong": "replay-strong"},
}
# USD per 1M tokens (input, output), for the cost log only.
PRICES = {
    "claude-haiku-5-5": (1.0, 5.0), "claude-sonnet-5-5": (3.0, 15.0),
    "gemini-2.5-flash-lite": (0.10, 0.40), "gemini-2.5-flash": (0.30, 2.50),
    # Estimates for the cost log; on the free tier the real spend is zero.
    "gemini-3.5-flash-lite": (0.10, 0.40), "gemini-3.5-flash": (0.30, 2.50), "gemini-3.8-flash": (0.30, 2.50),
}


REPLAY_DIR = DATA_DIR / "replay"


def provider():
    pref = os.getenv("FINN_LLM_PROVIDER")
    if pref == "replay":
        return "replay"
    if USER_KEY.get():
        return "gemini"
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
        timeout=45,
    )
    r.raise_for_status()
    j = r.json()
    text = "".join(b.get("text", "") for b in j["content"])
    return text, j["usage"]["input_tokens"], j["usage"]["output_tokens"]


def _gemini(model, system, prompt, max_tokens):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": gemini_key()},  # header, not ?key=, so the key never lands in URLs or error logs
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}],
              # Thinking models spend output tokens on reasoning first; without headroom the answer (often JSON) is cut off.
              "generationConfig": {"maxOutputTokens": max_tokens + 4096, "temperature": 0.2}},
        timeout=45,
    )
    r.raise_for_status()
    j = r.json()
    cand = j["candidates"][0]
    if cand.get("finishReason") == "MAX_TOKENS":
        print(f"llm: {model} hit the token limit; output may be truncated")
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    u = j.get("usageMetadata", {})
    return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


RETRYABLE = {429, 500, 503, 504}


def _daily_quota(e):
    """Free-tier daily request caps (e.g. 20 a day for the strong model) don't clear in seconds; retrying only burns more."""
    r = getattr(e, "response", None)
    return r is not None and r.status_code == 429 and "PerDay" in r.text


def _retryable(e):
    if isinstance(e, (requests.Timeout, requests.ConnectionError)):
        return True
    return e.response is not None and e.response.status_code in RETRYABLE


def _with_retry(call, *args, attempts=3):
    for i in range(attempts):
        try:
            return call(*args)
        except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as e:
            if not _retryable(e) or _daily_quota(e) or i == attempts - 1:
                raise
            time.sleep(2 * 2 ** i)  # 2s, 4s


def check_key(key):
    """One tiny call with a visitor's key, so a typo is caught when it's saved rather than mid-research."""
    token = USER_KEY.set(key)
    try:
        _gemini(MODELS["gemini"]["cheap"], "Be terse.", "Reply OK.", 5)
        return {"ok": True}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code == 429:
            return {"ok": True, "note": "Key works, but its free limit is used up for now."}
        return {"ok": False, "error": "Google rejected this key. Check it and try again."}
    except requests.RequestException:
        return {"ok": False, "error": "Couldn't reach Google to check the key. Try again."}
    finally:
        USER_KEY.reset(token)


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
    if p == "replay":
        # Test harness: prompts are written out, answers are written in by hand, nothing is cached.
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        ans = REPLAY_DIR / f"{key[:16]}.answer"
        if ans.exists():
            return ans.read_text(encoding="utf-8")
        (REPLAY_DIR / f"{key[:16]}.prompt").write_text(f"[{tier}]\n{system}\n\n{prompt}", encoding="utf-8")
        return None
    call = _anthropic if p == "anthropic" else _gemini
    try:
        text, tin, tout = _with_retry(call, model, system, prompt, max_tokens)
    except (requests.HTTPError, requests.Timeout, requests.ConnectionError) as e:
        # Free-tier strong models are often overloaded; a cheap-model answer beats no answer.
        if tier == "strong" and _retryable(e):
            print(f"llm: {model} unavailable ({type(e).__name__}), falling back to {MODELS[p]['cheap']}")
            model = MODELS[p]["cheap"]
            text, tin, tout = _with_retry(call, model, system, prompt, max_tokens)
            # Cache under the cheap model's key, so the next run still tries the strong model for this prompt.
            key = hashlib.sha256(f"{model}\n{system}\n{prompt}".encode()).hexdigest()
        else:
            raise
    pin, pout = PRICES.get(model, (0, 0))
    cost = (tin * pin + tout * pout) / 1e6
    conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?)",
                 (key, model, text, cost, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return text


def complete_json(prompt: str, tier="cheap", **kw):
    """Ask for JSON and parse it leniently (models sometimes wrap it in prose or code fences)."""
    try:
        out = complete(prompt + "\n\nReturn ONLY valid JSON, no prose, no code fences.", tier=tier, **kw)
    except requests.RequestException as e:  # rate limit / outage: callers fall back, nothing is cached
        print(f"llm {tier} call failed: {e}")
        return None
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
