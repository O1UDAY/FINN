"""Push side: the windowed Brief and triggered alerts."""
import json
from datetime import datetime, timedelta

from . import llm
from .config import DEFAULT_THRESHOLDS, PORTFOLIO
from .db import connect
from .enrich import clean_detail
from .ingest.classify import classify
from .ingest.prices import detect_moves

ROUTINE_BELOW = 30  # importance under this is collapsed as routine


def parse_ts(ts: str):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except (ValueError, TypeError):
            pass
    return None


def get_settings(conn=None):
    conn = conn or connect()
    s = {"portfolio": PORTFOLIO, **DEFAULT_THRESHOLDS}
    for r in conn.execute("SELECT key, value FROM settings"):
        s[r["key"]] = json.loads(r["value"])
    return s


def put_settings(values: dict):
    conn = connect()
    for k, v in values.items():
        if k in ("portfolio", "volume_multiple", "price_move_pct", "categories"):
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, json.dumps(v)))
    conn.commit()
    return get_settings(conn)


def classify_unknowns(conn, limit=40):
    """Rules couldn't place these; one batched cheap-model call places up to `limit` at once."""
    rows = conn.execute("SELECT id, subject, detail FROM announcements WHERE category IS NULL LIMIT ?", (limit,)).fetchall()
    if not rows or not llm.available():
        return 0
    cats = "results, M&A, fund_raise, management_change, litigation, insider_trading, earnings_call, investor_meetings, " \
           "credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm, pledging, unclassified"
    got = llm.complete_json(
        f"Classify each NSE filing into one of: {cats}. 'unclassified' = routine paperwork.\n"
        'Return {"<id>": "<category>"}.\n\n' + "\n".join(f"{r['id']}: {r['subject']} — {(r['detail'] or '')[:200]}" for r in rows),
        tier="cheap", max_tokens=1200) or {}
    from .ingest.classify import IMPORTANCE
    n = 0
    for r in rows:
        cat = got.get(r["id"])
        if cat in IMPORTANCE:
            conn.execute("UPDATE announcements SET category=?, importance=? WHERE id=?", (cat, IMPORTANCE[cat], r["id"]))
            n += 1
    conn.commit()
    return n


def build_brief(hours=24, now=None):
    conn = connect()
    s = get_settings(conn)
    now = now or datetime.now()
    since = now - timedelta(hours=hours)
    care = set(s["categories"])

    cards, routine = [], []
    for r in conn.execute("SELECT * FROM announcements WHERE symbol IN (%s)" % ",".join("?" * len(s["portfolio"])), s["portfolio"]):
        ts = parse_ts(r["ts"])
        if not ts or ts < since:
            continue
        cat = r["category"] or "other"
        imp = r["importance"] if r["importance"] is not None else classify(r["subject"], r["detail"])[1]
        alert = cat in care
        item = {"id": r["id"], "kind": "filing", "symbol": r["symbol"], "ts": ts.isoformat(), "category": cat,
                "importance": imp + (10 if alert else 0), "alert": alert, "subject": r["subject"],
                "text": clean_detail(r["detail"]), "url": r["attachment"]}
        (routine if imp < ROUTINE_BELOW else cards).append(item)

    # Price/volume alerts: only sessions that fall inside the window.
    for a in detect_moves(conn, s["portfolio"], s["volume_multiple"], s["price_move_pct"]):
        if datetime.fromisoformat(a["date"]) + timedelta(hours=16) >= since:
            strength = max(a["volume_x"] / s["volume_multiple"], abs(a["pct"]) / s["price_move_pct"])
            cards.append({"id": f"px-{a['symbol']}-{a['date']}", "kind": "move", "symbol": a["symbol"], "ts": a["date"] + "T15:30:00",
                          "category": "price_move", "importance": min(95, int(60 + 15 * strength)), "alert": True,
                          "subject": " · ".join(a["reasons"]), "move": a, "spark": _spark(conn, a["symbol"])})

    cards.sort(key=lambda c: c["ts"], reverse=True)
    cards.sort(key=lambda c: c["importance"], reverse=True)  # stable: newest first within equal importance
    routine.sort(key=lambda c: c["ts"], reverse=True)
    return {"window_hours": hours, "generated": now.isoformat(timespec="seconds"), "cards": cards, "routine": routine,
            "counts": {"material": len(cards), "routine": len(routine), "alerts": sum(c["alert"] for c in cards)},
            "settings": s}


def _spark(conn, symbol, n=30):
    rows = conn.execute("SELECT close, volume FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?", (symbol, n)).fetchall()
    return {"close": [r["close"] for r in reversed(rows)], "volume": [r["volume"] for r in reversed(rows)]}


def find_announcement(aid):
    r = connect().execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
    return dict(r) if r else None
