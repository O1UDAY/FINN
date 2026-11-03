"""Push channel: Telegram, optional. Unset TELEGRAM_BOT_TOKEN and this does nothing.

Anyone can subscribe: open the bot from Settings and tap Start (/stop leaves). Alerts go to every subscriber, plus
TELEGRAM_CHAT_ID if set. A bot can't message a phone number, only a chat that has started it.

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
    return bool(os.getenv("TELEGRAM_BOT_TOKEN"))


def _api(method, **body):
    r = requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/{method}", json=body, timeout=40)
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text[:120]}")
    return r.json()["result"]


def _subs(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id TEXT PRIMARY KEY, name TEXT, joined TEXT)")
    return conn


def recipients(conn=None):
    conn = _subs(conn or connect())
    chats = [r["chat_id"] for r in conn.execute("SELECT chat_id FROM subscribers")]
    own = os.getenv("TELEGRAM_CHAT_ID")
    return list(dict.fromkeys(([own] if own else []) + chats))


_bot = {}


def bot_link():
    """t.me link to the bot, for the Join button. Looked up once from the token."""
    if not configured():
        return None
    if "url" not in _bot:
        try:
            _bot["url"] = f"https://t.me/{_api('getMe')['username']}"
        except Exception:
            return None
    return _bot["url"]


WELCOME = ("<b>You're subscribed to FINN alerts.</b>\nYou'll get a message here when a filing or price move in the "
           "portfolio is unusual enough to matter. Send /stop to unsubscribe.")


def poll_subscribers(timeout=25):
    """One long-poll for /start and /stop. Runs in a loop on the server; returns how many updates it handled."""
    conn = _subs(connect())
    from .db import get_meta, set_meta
    offset = int(get_meta(conn, "telegram_offset", 0))
    ups = _api("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
    for u in ups:
        set_meta(conn, "telegram_offset", u["update_id"] + 1)
        m = u.get("message") or {}
        chat, txt = str(m.get("chat", {}).get("id", "")), (m.get("text") or "").strip().lower()
        if not chat:
            continue
        if txt.startswith("/stop"):
            conn.execute("DELETE FROM subscribers WHERE chat_id=?", (chat,)); conn.commit()
            _api("sendMessage", chat_id=chat, text="Unsubscribed. Send /start to get FINN alerts again.")
        else:
            new = conn.execute("INSERT OR IGNORE INTO subscribers VALUES (?,?,?)",
                               (chat, m["chat"].get("first_name", ""), datetime.now().isoformat(timespec="seconds"))).rowcount
            conn.commit()
            if new or txt.startswith("/start"):
                _api("sendMessage", chat_id=chat, text=WELCOME, parse_mode="HTML")
    return len(ups)


def _send(text):
    errors = 0
    chats = recipients()
    for chat in chats:
        try:
            _api("sendMessage", chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            errors += 1
            print("telegram:", chat, e)
    if chats and errors == len(chats):
        raise RuntimeError("Telegram refused every send")


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
        return {"ok": False, "error": "Telegram isn't set up. Add TELEGRAM_BOT_TOKEN to .env."}
    if not recipients():
        return {"ok": False, "error": "Nobody has joined yet. Tap Join on Telegram, then Start in the bot."}
    try:
        _send("<b>FINN test alert</b>\nIf you can read this, alerts will reach you here.")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
