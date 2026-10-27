# FINN — Financial Investment Agent

A mobile-first investor agent built for the ENAM Holdings AI Engineer Build Challenge.

**Point of view:** an investor doesn't need another dashboard or another chatbot. They need a **queue they can clear** and a **research view that holds management to their word**.

| Tab | What it does |
|---|---|
| **Brief** (push) | Every filing and unusual move across the portfolio for a window you pick (24h / 3d / week / month), ranked by importance. Material items become cards; routine paperwork is folded into one line. Swipe right to clear a card. A progress bar shows how close you are to "All clear". |
| **Interrogate** (pull) | Type any NSE ticker. You get a snapshot, computed red/green signals, **Promised vs. Delivered** across the last four concalls, narrative vs. numbers, current guidance, bull/bear, trajectory, cash quality and balance sheet. Every claim links to its primary source. |
| **Watch** | You set what "unusual" means: volume ×, price ±%, which filing types alert you, and the portfolio. It also shows live LLM spend. |

## How the push cards are enriched
- **Results:** the cheap model reads the results filing and returns Revenue / EBITDA / PBT / PAT for this quarter, last quarter and the same quarter last year. **Growth is computed in code, not by the model.** If no LLM is set, it falls back to screener's quarterly table and warns when that table is older than the filing. For lenders, EBITDA is replaced by NPA.
- **Management change:** who the person is, their role, whether they're joining or leaving, and their background. The background comes from the profile annexure that SEBI requires in the filing, plus an optional web lookup (Tavily) for LinkedIn and other public profiles.
- **Unusual move:** a sparkline and volume bars, ranked by how far the move went past *your* threshold.
- **Everything else:** a one-line "so what" for mid-importance filings; routine filings go to the fold.

## Cost funnel (the efficiency story)
1. **Rules first.** ~85% of filings are classified by regex (`classify.py`) for free. Only the leftovers go to the cheap model, in **one batched call**.
2. **Numbers are deterministic.** CAGR, D/E, CFO/PAT, cash conversion cycle and the signals are computed from screener's tables. No LLM, so the numbers can't be hallucinated.
3. **Pre-filter before reading.** A regex keeps only forward-looking sentences with numbers, cutting a 60k-character transcript to about 3k.
4. **Cheap model extracts, strong model judges.** One cheap call per transcript structures the promises. **One** strong call (Sonnet / Gemini Flash) compares them with the reported numbers.
5. **Everything is cached.** LLM outputs are cached by `sha256(model+prompt)`, along with PDFs, card enrichments and research. Opening a card twice costs nothing.
6. **Runs with no key at all.** Rules-only mode still gives the brief, alerts, results tables, every number and the raw forward-looking quotes.

## Data sources
- End-of-day price and volume: Yahoo Finance (`yfinance`, `.NS`)
- Announcements: the NSE corporate-announcements API (filing PDFs from `nsearchives`)
- Fundamentals: screener.in tables (compiled from exchange filings), plus annual reports, concall transcripts and investor presentations (BSE / company IR). Companies that don't hold concalls (e.g. Trent) fall back to investor presentations.

The pull side uses primary sources only: no news, no broker notes, and the prompt forbids outside knowledge.

## Run locally
```bash
cd backend && pip install -r requirements.txt
cp ../.env.example ../.env      # optional: add ANTHROPIC_API_KEY or GEMINI_API_KEY (free tier)
python ingest.py --days 30 --docs
cd ../frontend && npm install && npm run build
cd .. && python -m uvicorn app:app --app-dir backend --port 8000
```
Open http://localhost:8000 on your phone (same Wi-Fi: `--host 0.0.0.0`). For frontend development, run `npm run dev` in `frontend/`; it proxies `/api` to :8000.

## Deploy
One Docker container (`Dockerfile`) serves both the API and the PWA. `render.yaml` deploys it to Render's free tier: connect the repo, then add a key in the dashboard. Data refreshes on boot and every 6h.

## Layout
```
backend/
  app.py                 FastAPI + static PWA + background refresh
  ingest.py              daily pipeline (prices → filings → classify → pre-enrich)
  finn/llm.py            two-tier router (Anthropic or Gemini), cache, cost log
  finn/brief.py          windowed digest, alert rules, settings
  finn/enrich.py         results / management / one-liner enrichment
  finn/research.py       numbers + promised-vs-delivered funnel
  finn/screener.py       tables + document links for any ticker
  finn/ingest/*          prices, NSE announcements, rule classifier
frontend/src/            React PWA: Brief, Card, Research, Watch
```
