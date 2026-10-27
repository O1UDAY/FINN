"""Push channel: Telegram, optional. Unset TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID and this does nothing.

Every alert ID that has been delivered (or, with Telegram off, surfaced) is written to notified_alerts, so a refresh
never re-alerts the same filing or price move. Plain HTTPS to the Bot API, no extra dependency.
"""
import html
import os
from datetime import datetime

import requests

from .db import connect

MAX_PER_REFRESH = 10


def configured():
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _send(text):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text[:120]}")


def story_link(alert_id):
    base = os.getenv("FINN_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/?story={alert_id}"


def format_alert(card) -> str:
    """One tight message: headline, why it's here, the numbers, a deep link into the story."""
    head = card.get("text") or card.get("subject") or ""
    if card["kind"] == "move":
        m = card["move"]
        head = f"{card['symbol']} {'up' if m['pct'] >= 0 else 'down'} {abs(m['pct']):.1f}%, {m['volume_x']:.1f}× volume"
        nums = f"Close ₹{m['close']:,.2f}"
    else:
        nums = card["symbol"]
    why = card.get("why") or ""
    return (f"<b>{html.escape(head)}</b>\n{html.escape(why)} · {html.escape(nums)}\n"
            f"<a href=\"{story_link(card['id'])}\">Open in FINN</a>")


def new_alerts(conn, cards):
    sent = {r["id"] for r in conn.execute("SELECT id FROM notified_alerts")}
    return [c for c in cards if c.get("alert") and c["id"] not in sent]


def mark(conn, ids, channel):
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany("INSERT OR IGNORE INTO notified_alerts VALUES (?,?,?,?)", [(i, "alert", now, channel) for i in ids])
    conn.commit()


def send_new_alerts(conn=None, hours=24):
    from .brief import build_brief
    conn = conn or connect()
    todo = new_alerts(conn, build_brief(hours, enrich_missing=False)["cards"])
    if not todo:
        return 0
    if not configured():
        mark(conn, [c["id"] for c in todo], "in-app")  # surfaced in the Brief; don't fire them later in a burst
        return 0
    sent = []
    for c in todo[:MAX_PER_REFRESH]:
        try:
            _send(format_alert(c))
            sent.append(c["id"])
        except Exception as e:
            print("telegram:", e)
            break  # leave the rest unmarked so the next refresh retries them
    rest = len(todo) - len(sent)
    if sent and rest > 0 and len(sent) == MAX_PER_REFRESH:
        try:
            _send(f"+{rest} more in FINN: <a href=\"{story_link('')}\">open the Brief</a>")
            sent += [c["id"] for c in todo[MAX_PER_REFRESH:]]  # summarised, so counted as delivered
        except Exception as e:
            print("telegram:", e)
    mark(conn, sent, "telegram")
    return len(sent)


def send_test():
    if not configured():
        return {"ok": False, "error": "Telegram isn't set up. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env."}
    try:
        _send("<b>FINN test alert</b>\nIf you can read this, alerts will reach you here.")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
