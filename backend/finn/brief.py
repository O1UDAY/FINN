"""Push side: the windowed Brief and triggered alerts."""
import json
from datetime import datetime, timedelta

from . import llm
from .config import DEFAULT_THRESHOLDS, PORTFOLIO
from .db import connect
from .enrich import clean_detail
from .ingest.classify import classify
from .ingest.prices import detect_moves

ROUTINE_BELOW = 45     # importance under this is folded into "Also filed"
LONG_WINDOW_STORY = 70  # windows over 24h: only items this strong (or alerts) stay stories
LONG_WINDOW_ALERT = 60  # ...and an alert-category item still needs this much on its own
GENERIC = {  # NSE subject vocabulary: never good enough to be a headline
    "general updates", "updates", "press release", "outcome of board meeting", "change in management",
    "action(s) initiated or orders passed", "bagging/receiving of orders/contracts", "credit rating", "acquisition",
    "shareholders meeting", "analysts/institutional investor meet/con. call updates", "copy of newspaper publication",
    "corporate insolvency resolution process", "allotment of securities", "record date", "news verification",
    "sale or disposal", "resignation", "resignation of director/kmp/smp", "issue of securities", "preferential issue",
    "qualified institutional placement", "monitoring agency report", "trading window", "esop/esos/esps",
}


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


CAT_LABEL = {
    "results": "results", "M&A": "deal", "management_change": "management change", "fund_raise": "fundraising",
    "litigation": "legal matter", "credit_rating": "credit rating", "pledging": "pledge", "insider_trading": "insider dealing",
    "capex": "capex", "press_release": "company news", "dividend": "dividend", "bonus_split": "bonus or split",
    "earnings_call": "earnings call", "investor_meetings": "investor meeting", "agm_egm": "shareholder meeting",
    "postal_ballot": "postal ballot", "unclassified": "routine filing", "other": "filing",
}


def is_generic(text: str, subject: str) -> bool:
    t = (text or "").strip().lower().rstrip(".")
    return not t or t == (subject or "").strip().lower() or t in GENERIC or len(t) < 25


def fallback_headline(symbol, cat, subject, detail, amount_cr=None):
    """Deterministic headline when no enrichment exists. Uses the filing's own description when it says something,
    otherwise category + company + any amount, and never the raw NSE subject."""
    d = clean_detail(detail)
    if not is_generic(d, subject):
        return d
    from .materiality import fmt_cr
    amt = f", {fmt_cr(amount_cr)}" if amount_cr else ""
    return f"{symbol}: {CAT_LABEL.get(cat, 'filing')}{amt} (details in filing)"


def story_reason(item, alert, cat, imp, role=None):
    label = CAT_LABEL.get(cat, "filing")
    if item.get("ratio"):
        return f"Large vs size: {item['ratio'] * 100:.2f}% of market cap"
    if alert:
        return f"Your alert: {label}"
    if cat == "management_change" and role:
        return f"Management change: {role}"
    return f"High impact: {label}"


def build_brief(hours=24, now=None, enrich_missing=True):
    from .materiality import immaterial_line
    conn = connect()
    s = get_settings(conn)
    now = now or datetime.now()
    since = now - timedelta(hours=hours)
    care = set(s["categories"])
    long_window = hours > 24

    # Pre-computed enrichment headlines let a collapsed card lead with the "so what" instead of the raw filing line.
    headlines, roles = {}, {}
    for e in conn.execute("SELECT id, payload FROM enrichments"):
        p = json.loads(e["payload"])
        if p.get("headline"):
            headlines[e["id"]] = p["headline"]
        people = p.get("people") or []
        if people and people[0].get("role"):
            roles[e["id"]] = people[0]["role"]

    cards, routine, seen = [], [], {}
    for r in conn.execute("SELECT * FROM announcements WHERE symbol IN (%s)" % ",".join("?" * len(s["portfolio"])), s["portfolio"]):
        ts = parse_ts(r["ts"])
        if not ts or ts < since:
            continue
        cat = r["category"] or "other"
        imp = r["importance"] if r["importance"] is not None else classify(r["subject"], r["detail"])[1]
        alert = cat in care
        item = {"id": r["id"], "kind": "filing", "symbol": r["symbol"], "ts": ts.isoformat(), "category": cat,
                "importance": imp + (10 if alert else 0), "alert": alert, "subject": r["subject"], "url": r["attachment"],
                "text": headlines.get(r["id"]) or fallback_headline(r["symbol"], cat, r["subject"], r["detail"], r["amount_cr"]),
                "enriched": r["id"] in headlines}

        if r["material"] == 0:  # size check ran and the amount is noise for a company this big
            item["text"] = immaterial_line(r["amount_cr"], r["mcap_cr"])
            routine.append(item)
            continue
        if r["material"] == 1 and r["mcap_cr"]:
            item["ratio"] = r["amount_cr"] / r["mcap_cr"]

        # The last 24h is judged the same in every window, so widening the window never hides today's stories.
        recent = ts >= now - timedelta(hours=24)
        story = imp >= ROUTINE_BELOW and (not long_window or recent or imp >= LONG_WINDOW_STORY or (alert and imp >= LONG_WINDOW_ALERT))
        if not story:
            routine.append(item)
            continue
        # One story per company, category and day: results come as statement + deck + press release.
        key = (r["symbol"], cat, ts.date())
        if key in seen:
            first = seen[key]
            first["related"] = first.get("related", 0) + 1
            if item["enriched"] and not first["enriched"]:  # the filing with a computed headline represents the group
                for k in ("id", "text", "url", "subject", "enriched", "ts"):
                    first[k] = item[k]
            continue
        item["why"] = story_reason(item, alert, cat, imp, roles.get(r["id"]))
        seen[key] = item
        cards.append(item)

    # Price/volume alerts: only sessions that fall inside the window.
    for a in detect_moves(conn, s["portfolio"], s["volume_multiple"], s["price_move_pct"]):
        if datetime.fromisoformat(a["date"]) + timedelta(hours=16) >= since:
            strength = max(a["volume_x"] / s["volume_multiple"], abs(a["pct"]) / s["price_move_pct"])
            cards.append({"id": f"px-{a['symbol']}-{a['date']}", "kind": "move", "symbol": a["symbol"], "ts": a["date"] + "T15:30:00",
                          "category": "price_move", "importance": min(95, int(60 + 15 * strength)), "alert": True,
                          "subject": " · ".join(a["reasons"]), "move": a, "spark": _spark(conn, a["symbol"]),
                          "why": "Unusual move: " + " and ".join(a["reasons"])})

    cards.sort(key=lambda c: c["ts"], reverse=True)
    cards.sort(key=lambda c: c["importance"], reverse=True)  # stable: newest first within equal importance
    routine.sort(key=lambda c: c["ts"], reverse=True)
    folded_by_cat = {}
    for x in routine:
        folded_by_cat[x["category"]] = folded_by_cat.get(x["category"], 0) + 1

    missing = [c["id"] for c in cards if c["kind"] == "filing" and not c["enriched"]]
    if enrich_missing and missing:
        _enrich_later(missing)
    return {"window_hours": hours, "generated": now.isoformat(timespec="seconds"), "cards": cards, "routine": routine,
            "folded_by_category": folded_by_cat, "pending_enrichment": len(missing),
            "counts": {"material": len(cards), "routine": len(routine), "alerts": sum(c["alert"] for c in cards)},
            "settings": s}


_enriching = set()


def _enrich_later(ids):
    """Stories without a summary get one in the background (cached), so the next load shows it. The card shows the
    deterministic fallback headline meanwhile, never the raw subject."""
    import threading
    from .enrich import enrich
    todo = [i for i in ids if i not in _enriching]
    if not todo:
        return
    _enriching.update(todo)

    def run():
        for aid in todo:
            try:
                ann = find_announcement(aid)
                if ann:
                    enrich(ann)
            except Exception as e:
                print("background enrich failed", aid, e)
            finally:
                _enriching.discard(aid)
    threading.Thread(target=run, daemon=True).start()


def _spark(conn, symbol, n=30):
    rows = conn.execute("SELECT close, volume FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?", (symbol, n)).fetchall()
    return {"close": [r["close"] for r in reversed(rows)], "volume": [r["volume"] for r in reversed(rows)]}


def find_announcement(aid):
    r = connect().execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
    return dict(r) if r else None
