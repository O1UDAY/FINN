"""FINN API. Serves the built PWA from ../frontend/dist when present, so one service = one URL."""
import os

from finn import env  # noqa: F401  (loads .env before anything reads keys)
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from finn import llm
from finn.brief import build_brief, find_announcement, get_settings, put_settings
from finn.enrich import enrich
from finn.research import analysis, numbers
from ingest import run as run_ingest

app = FastAPI(title="FINN")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_state = {"refreshing": False, "last_refresh": None, "last_error": None}


def _refresh():
    if _state["refreshing"]:
        return
    _state["refreshing"] = True
    try:
        run_ingest(days=30, docs=False)
        _state["last_refresh"], _state["last_error"] = time.strftime("%Y-%m-%dT%H:%M:%S"), None
    except Exception as e:
        _state["last_error"] = str(e)
    finally:
        _state["refreshing"] = False


def _scheduler():
    while True:
        _refresh()
        time.sleep(int(os.getenv("FINN_REFRESH_SECONDS", 6 * 3600)))


@app.on_event("startup")
def startup():
    if os.getenv("FINN_AUTO_REFRESH", "1") == "1":
        threading.Thread(target=_scheduler, daemon=True).start()


@app.get("/api/status")
def status():
    return {**_state, "llm": llm.spend()}


@app.post("/api/refresh")
def refresh():
    threading.Thread(target=_refresh, daemon=True).start()
    return {"started": True}


@app.get("/api/brief")
def brief(hours: int = 24):
    return build_brief(hours=max(1, min(hours, 24 * 30)))


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


@app.get("/api/research/{symbol}")
def research_numbers(symbol: str):
    try:
        return numbers(symbol)
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.get("/api/research/{symbol}/analysis")
def research_analysis(symbol: str, refresh: bool = False):
    try:
        return analysis(symbol, refresh=refresh)
    except LookupError as e:
        raise HTTPException(404, str(e))


DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
