# FINN — Financial Investment Agent

A mobile-first investor agent built for the ENAM Holdings AI Engineer Build Challenge.

**Point of view:** an investor doesn't need another dashboard or another chatbot. They need a morning paper for their own portfolio, one they can finish, and a research desk that holds management to its word.

| Tab | What it does |
|---|---|
| **Brief** (push) | Filings and unusual moves for a window you pick (since yesterday / 3 days / week / month), ranked, each with a "why it's here" line. Routine paperwork and size-immaterial legal items are folded into "Also filed" with counts per category. Swipe a story right to clear it. |
| **Research** (pull) | Any NSE ticker. Key figures, computed signals (lease-adjusted where needed), **promises and delivery** (guidance from the last four calls checked against reported numbers and later-call KPIs, with page citations), story vs numbers, guidance, the case for and against, trajectory, cash and debt. |
| **Settings** | Price/volume thresholds, alert categories, validated holdings, light/dark, data status, model spend, Telegram test alert. |

## Architecture

```
                 ┌──────────── ingest.py (thread every 6h · CLI · POST /api/admin/refresh) ─────────────┐
yfinance .NS/.BO ┤ prices                                                                                │
NSE API ─retry──►├ announcements ──(NSE gave nothing?)──► BSE API ──(both empty?)──► seed snapshot       │
screener.in ─────┤ tables, documents, line-item schedules (429/403 → "source busy", never "not found")   │
                 └───────────────────────────────────────┬────────────────────────────────────────────────┘
                                                         ▼
                                     SQLite finn.db (filings, prices, pages, enrichments, research,
                                      llm_cache, notified_alerts, meta)
        ┌────────────────────────────┬──────────────────┴───────────┬─────────────────────────────┐
  classify.py                   materiality.py                 enrich.py                    research.py
  rules → 1 batched cheap call  claimed ₹ vs market cap        results (EBITDA in code),    numbers in code (margins to 1 dp,
  + within-category rescoring   (<0.01% → folded)              management (+ referenced     lease-adjusted CFO and D/E, sanity
                                                               profiles), one-liners        bounds) → regex → cheap extraction →
                                                                                            later-call KPIs → 1 strong judge
        └──────────── brief.py (window rules, grouping, why-it's-here) ──── notify.py (Telegram, de-duplicated)
                                                         ▼
                        app.py (FastAPI: /api/*, research jobs, /api/health) + React PWA (frontend/dist)
```

**Models.** Rules first, then `gemini-3.5-flash-lite` for bulk work (classification, results and management extraction, one-liners, promise and KPI extraction), and `gemini-3.5-flash` for one judging call per company. Anthropic (Haiku/Sonnet) is supported too. Every call is cached by `sha256(model + prompt)`; arithmetic (EBITDA, growth, margins, ratios) is always done in code.

**Measured cost** (Gemini list prices; the free tier makes it $0): ~$0.00018 per cheap call, ~$0.0048 per strong call. About **$0.007–0.012 for a new company's first research run**, $0 when cached; **~$0.001–0.002 for a daily refresh**.

## Run locally

Requires **Python 3.10+** and Node 18+.

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env          # add GEMINI_API_KEY (free at aistudio.google.com); everything else optional
python ingest.py --days 30 --docs   # first run takes several minutes (--docs fetches every company's document list)
cd ../frontend && npm install && npm run build
cd .. && python -m uvicorn app:app --app-dir backend --port 8000
```

Open http://localhost:8000. To try it on a phone on the same Wi-Fi, add `--host 0.0.0.0` and open `http://<laptop-ip>:8000`. For frontend development, `npm run dev` in `frontend/` proxies `/api` to :8000.

Tests: `cd backend && python -m pytest -q` (30 tests).

## Environment variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Language model (or `ANTHROPIC_API_KEY`). Without a key FINN runs rules-only. |
| `FINN_GEMINI_CHEAP`, `FINN_GEMINI_STRONG` | Override model names when Google retires them. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional push alerts after each refresh. Unset = silently off. |
| `FINN_PUBLIC_URL` | Base URL used in alert deep links (`/?story=<id>`). |
| `FINN_ADMIN_TOKEN` | Enables `POST /api/admin/refresh` (header `X-Admin-Token`). |
| `FINN_AUTO_REFRESH`, `FINN_REFRESH_SECONDS` | In-process refresh thread (default on, every 6h). |
| `TAVILY_API_KEY` | Optional web lookup for executive bios. **Optional, untested**: no key was available; bios come from the filing's own profile annexure. |
| `VITE_EXTRA_APPEARANCE=1` (build time) | Shows the extra papers, accents and text sizes. Off by default. |

## Operations

- **Snapshot fallback.** `seed/finn_seed.db` (committed, ~3.6 MB, no secrets) holds filings, prices, enrichments and research. It's loaded when the database is empty or when NSE and BSE both return nothing; the Brief then shows "Data as of <date> (snapshot)". Rebuild it with `python scripts/make_snapshot.py`.
- **Announcement sources.** NSE with retries, falling back to BSE (scrip codes in `finn/config.py`). The source used is in `/api/health`.
- **Warm-up.** `python scripts/warmup.py [TICKERS...]` enriches every story in every window and pre-computes research for the portfolio and research list, so a cold visitor never waits. Cached items are skipped.
- **Health.** `GET /api/health`: table row counts, last refresh, data source (live NSE / BSE / snapshot), recent fetch errors.
- **External cron.** `python -m backend.ingest --refresh` from the repo root, or `POST /api/admin/refresh` with `X-Admin-Token`. Refreshes are lock-guarded and idempotent; alerts are never re-sent (`notified_alerts`).

## Testing the model paths without a key (replay mode)

`FINN_LLM_PROVIDER=replay` writes each prompt to `backend/data/replay/<hash>.prompt` and reads the answer from `<hash>.answer`. The committed fixtures were answered by hand from the source documents and exercise the whole pipeline without spending anything.

## Layout
```
backend/
  app.py                 FastAPI: brief, cards, research jobs, holdings, health, admin refresh, static PWA
  ingest.py              refresh pipeline (prices → filings → classify → size check → enrich → notify)
  finn/llm.py            two-tier router, retries/fallback, cache, cost log
  finn/brief.py          window rules, grouping, fallback headlines, why-it's-here
  finn/materiality.py    claimed-amount parsing, size rule
  finn/enrich.py         results / management / one-liners
  finn/research.py       numbers, lease view, promises → later-call KPIs → judge
  finn/screener.py       tables, documents, schedules, rate-limit handling
  finn/notify.py         Telegram + de-duplication
  finn/snapshot.py       seed export/load
  finn/ingest/*          prices (.NS/.BO), announcements (NSE/BSE), classifier
  scripts/               make_snapshot.py, warmup.py
  tests/                 pytest
frontend/src/            React PWA: Brief, Card, Research, Watch (Settings), Appearance, theme
seed/finn_seed.db        snapshot fallback
```
