"""Pre-compute everything a cold visitor would otherwise wait for: enrichment for every story in every window and
the research analysis for portfolio + RESEARCH tickers. Cached results are skipped, so re-running is cheap.

    python scripts/warmup.py              # all tickers
    python scripts/warmup.py TRENT LT     # just these
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finn import env  # noqa: F401,E402
from finn import llm  # noqa: E402
from finn.brief import build_brief, find_announcement, get_settings  # noqa: E402
from finn.config import RESEARCH  # noqa: E402
from finn.db import connect  # noqa: E402
from finn.enrich import enrich  # noqa: E402
from finn.research import analysis  # noqa: E402

start, spent = time.time(), llm.spend()["total_usd"]
done = {r["id"] for r in connect().execute("SELECT id FROM enrichments")}
ids = {c["id"] for h in (24, 72, 168, 720) for c in build_brief(h, enrich_missing=False)["cards"] if c["kind"] == "filing"}
for aid in ids - done:
    enrich(find_announcement(aid))
print(f"enriched {len(ids - done)} stories")

symbols = sys.argv[1:] or list(dict.fromkeys(get_settings()["portfolio"] + RESEARCH))
cached = {r["symbol"] for r in connect().execute("SELECT symbol FROM research")}
for s in symbols:
    if s in cached:
        print(f"{s}: cached")
        continue
    t = time.time()
    try:
        a = analysis(s)
        print(f"{s}: {len(a.get('promised_vs_delivered', []))} commitments judged in {time.time() - t:.0f}s")
    except Exception as e:
        print(f"{s}: failed ({e})")
print(f"warm-up done in {time.time() - start:.0f}s, LLM cost ${llm.spend()['total_usd'] - spent:.4f}")
