"""FINN API. Serves the built PWA from ../frontend/dist when present, so one service = one URL."""
import os
import contextvars
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from finn import env  # noqa: F401  (loads .env before anything reads keys)

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from finn import llm, notify
from finn.ask import ask
from finn.brief import build_brief, find_announcement, get_settings, put_settings
from finn.db import connect, get_meta
from finn.enrich import enrich
from finn.research import STEPS, analysis, numbers
from finn.screener import SourceBusy
from finn.snapshot import status as data_status
from ingest import run as run_ingest

app = FastAPI(title="FINN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def visitor_key(request, call_next):
    """A visitor may bring their own Gemini key; it applies to their requests only and is never stored."""
    key = (request.headers.get("x-gemini-key") or "").strip()[:200] or None
    token = llm.USER_KEY.set(key)
    try:
        return await call_next(request)
    finally:
        llm.USER_KEY.reset(token)


_state = {"refreshing": False, "last_refresh": None, "last_error": None}
_refresh_lock = threading.Lock()


IST = timezone(timedelta(hours=5, minutes=30))
FULL_EVERY = int(os.getenv("FINN_REFRESH_SECONDS", 6 * 3600))
FILINGS_EVERY = int(os.getenv("FINN_FILINGS_SECONDS", 15 * 60))
PRICES_AFTER = 16  # IST hour: NSE closes 15:30, Yahoo's end-of-day bar is settled by 16:00
_last = {"full": 0.0, "prices_day": None}


def _refresh(full=None):
    """One refresh. Filings (and the alerts on them) every FILINGS_EVERY; prices, the 30-day sweep and enrichment
    of the whole month on a full run: every FULL_EVERY, and once each day after the market closes."""
    if not _refresh_lock.acquire(blocking=False):  # idempotent: a second trigger during a run is a no-op
        return False
    _state["refreshing"] = True
    try:
        now = datetime.now(IST)
        new_close = now.hour >= PRICES_AFTER and _last["prices_day"] != now.date()
        if full is None:
            full = new_close or time.time() - _last["full"] >= FULL_EVERY
        if full:
            run_ingest(days=30, docs=False)
            _last["full"] = time.time()
            if now.hour >= PRICES_AFTER:
                _last["prices_day"] = now.date()
        else:
            run_ingest(days=2, docs=False, prices=False)
        _state["last_refresh"], _state["last_error"] = time.strftime("%Y-%m-%dT%H:%M:%S"), None
        _state["last_kind"] = "full" if full else "filings"
    except Exception as e:
        _state["last_error"] = str(e)
    finally:
        _state["refreshing"] = False
        _refresh_lock.release()
    return True


def _scheduler():
    while True:
        _refresh()
        time.sleep(min(FILINGS_EVERY, FULL_EVERY))


@app.on_event("startup")
def startup():
    if os.getenv("FINN_AUTO_REFRESH", "1") == "1":
        threading.Thread(target=_scheduler, daemon=True).start()


@app.get("/api/status")
def status():
    return {**_state, "llm": llm.spend(), "data": data_status(), "telegram": notify.configured(),
            "own_key": bool(llm.USER_KEY.get())}


@app.post("/api/key/check")
def key_check(body: dict = Body(...)):
    key = str(body.get("key") or "").strip()
    if len(key) < 20:
        return {"ok": False, "error": "That doesn't look like a Gemini key."}
    return llm.check_key(key)


@app.get("/api/health")
def health():
    conn = connect()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("announcements", "prices", "enrichments", "research", "documents", "notified_alerts", "llm_cache")}
    d = data_status()
    source = "snapshot" if d["mode"] == "snapshot" else get_meta(conn, "announcements_source", "unknown")
    return {"ok": counts["announcements"] > 0, "rows": counts, "data_source": source, "data": d,
            "last_refresh": get_meta(conn, "last_refresh"), "refreshing": _state["refreshing"],
            "last_error": _state["last_error"], "announcement_errors": get_meta(conn, "announcements_errors")}


@app.post("/api/refresh")
def refresh():
    threading.Thread(target=_refresh, kwargs={"full": True}, daemon=True).start()
    return {"started": not _state["refreshing"]}


@app.post("/api/admin/refresh")
def admin_refresh(x_admin_token: str | None = Header(default=None)):
    """For an external cron. Requires FINN_ADMIN_TOKEN; disabled when it isn't set."""
    token = os.getenv("FINN_ADMIN_TOKEN")
    if not token:
        raise HTTPException(503, "Admin refresh is disabled: set FINN_ADMIN_TOKEN.")
    if x_admin_token != token:
        raise HTTPException(401, "Wrong or missing X-Admin-Token.")
    if _state["refreshing"]:
        return {"started": False, "reason": "a refresh is already running"}
    threading.Thread(target=_refresh, daemon=True).start()
    return {"started": True}


@app.get("/api/brief")
def brief(hours: int = 24):
    b = build_brief(hours=max(1, min(hours, 24 * 30)))
    b["data"] = data_status()
    return b


@app.get("/api/card/{aid}")
def card(aid: str):
    ann = find_announcement(aid)
    if not ann:
        raise HTTPException(404, "unknown announcement")
    return enrich(ann)


@app.get("/api/settings")
def settings():
    return get_settings()


@app.put("/api/settings")
def update_settings(values: dict = Body(...)):
    return put_settings(values)


@app.post("/api/holdings")
def add_holding(body: dict = Body(...)):
    """Validate a ticker against Yahoo (.NS, then .BO), add it, and fetch its prices and filings straight away."""
    from finn.ingest.prices import fetch_prices, resolve_ticker
    from finn.ingest.announcements import fetch_announcements
    sym = str(body.get("symbol", "")).upper().strip()
    if not sym.replace("-", "").replace("&", "").isalnum():
        raise HTTPException(400, "Enter an NSE symbol, like TITAN.")
    if not resolve_ticker(sym):
        raise HTTPException(404, f"No NSE or BSE listing found for {sym}. Check the symbol.")
    s = get_settings()
    if sym not in s["portfolio"]:
        s = put_settings({"portfolio": s["portfolio"] + [sym]})
    conn = connect()
    rows = fetch_prices(conn, [sym])
    filings = fetch_announcements(conn, [sym], days=30)
    return {"settings": s, "added": sym, "price_rows": rows, "filings": filings}


@app.post("/api/alerts/test")
def test_alert():
    return notify.send_test()


@app.get("/api/research/{symbol}")
def research_numbers(symbol: str):
    try:
        return numbers(symbol)
    except SourceBusy as e:
        raise HTTPException(503, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.post("/api/ask/{symbol}")
def ask_docs(symbol: str, body: dict = Body(...)):
    """A question answered only from the company's filings, with verified page citations."""
    q = str(body.get("question") or "").strip()
    if len(q) < 3:
        raise HTTPException(422, "Ask a question.")
    try:
        return ask(symbol, q, body.get("aid"))
    except SourceBusy as e:
        raise HTTPException(503, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


# Research analysis takes up to a minute on a cold run, longer than proxies wait, so it runs as a job.
_jobs: dict[str, dict] = {}


@app.post("/api/research/{symbol}")
def start_research(symbol: str, refresh: bool = False):
    symbol = symbol.upper().strip()
    if not refresh:
        row = connect().execute("SELECT payload FROM research WHERE symbol=?", (symbol,)).fetchone()
        if row:
            import json
            return {"job_id": None, "status": "done", "result": json.loads(row["payload"])}
    running = next((j for j in _jobs.values() if j["symbol"] == symbol and j["status"] == "running"), None)
    if running:
        return running
    jid = uuid.uuid4().hex[:12]
    job = {"job_id": jid, "symbol": symbol, "status": "running", "step": STEPS[0], "steps": STEPS,
           "started": time.time(), "result": None, "error": None}
    _jobs[jid] = job

    def work():
        try:
            job["result"] = analysis(symbol, refresh=refresh, progress=lambda st: job.update(step=st))
            job["status"] = "done"
        except SourceBusy as e:
            job["status"], job["error"] = "error", str(e)
        except LookupError as e:
            job["status"], job["error"] = "error", str(e)
        except Exception as e:
            job["status"], job["error"] = "error", f"Analysis failed ({type(e).__name__}). Try again."
    # Copy the request's context so a visitor's own key is used by the background job too.
    threading.Thread(target=contextvars.copy_context().run, args=(work,), daemon=True).start()
    return job


@app.get("/api/research/jobs/{job_id}")
def research_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job (the server may have restarted). Start the analysis again.")
    return {**job, "elapsed": round(time.time() - job["started"], 1)}


@app.get("/api/research/{symbol}/analysis")
def research_analysis(symbol: str, refresh: bool = False):
    """Synchronous variant, kept for scripts. The app uses POST /api/research/{symbol} + polling."""
    try:
        return analysis(symbol, refresh=refresh)
    except SourceBusy as e:
        raise HTTPException(503, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))


DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        # index.html must revalidate, or phones keep loading last deploy's asset hashes.
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
