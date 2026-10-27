# FINN — Financial Investment Agent

Mobile-first investor agent for the ENAM Holdings AI Engineer Build Challenge.

- **Push / The Brief** — a triage feed of what changed across the portfolio, ranked by importance; routine filings collapsed.
- **Pull / Interrogate** — on-demand research on any NSE ticker, grounded only in annual reports and concall transcripts. Centrepiece: *Promised vs. Delivered*.

## Backend (Day 1: data plumbing)
```
cd backend
pip install -r requirements.txt
python ingest.py --days 30
```
Sources: Yahoo Finance (EOD price/volume), NSE corporate-announcements API, screener.in (annual report + transcript links). Stored in SQLite (`backend/data/finn.db`).

Announcements are classified **rules-first** (`finn/ingest/classify.py`) — free and instant; only filings the rules can't place go to an LLM.
