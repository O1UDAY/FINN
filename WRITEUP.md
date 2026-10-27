# FINN — covering note

**What I built.** FINN is a mobile PWA with two jobs. The **Brief** is a morning paper for a 15-stock portfolio: results with Revenue, EBITDA, PBT and PAT against last quarter and last year (copied from the filing, derived and checked in code), management changes with the incoming person's background, and price/volume moves against thresholds the investor sets. Each story says why it's there; routine paperwork and legally trivial items are folded away, and you swipe stories until you're done. **Research** takes any NSE ticker and holds management to its word: it pulls commitments from the last four calls, finds what management later reported (in later calls and investor presentations), and gives each a verdict with the quarter, page and link.

**Key decisions.**
- *A paper you finish, not a chat.* An investor's morning is triage, so the core interaction is clearing a short list. Research is one tap from any story.
- *Numbers in code, judgement in the model.* EBITDA, growth, margins, lease adjustments and every signal are computed deterministically. The model copies line items and judges; it never does arithmetic, and it is told which metrics are unreliable.
- *A cost funnel.* Rules → regex pre-filter → cheap extraction → one strong judging call → cache.
- *Degrade, don't die.* No key: rules-only. NSE blocked: BSE. Both empty: a committed snapshot, labelled as such. Model busy: retry, then the cheap model.

## What a strict review found and what I fixed

I reviewed FINN as ENAM's investment director would, ran it on a company I hadn't picked (Jubilant FoodWorks), and fixed what failed, measuring each change.

| Problem found | Fix | Before → after (measured) |
|---|---|---|
| The month view was barely filtered; summaries were missing | Routine cut-off 30 → 45; windows over 24h keep only strong or alert items; within-category re-scoring (senior vs minor management changes, rating reaffirmations, ESOP allotments); one story per company, category and day; every story enriched | Stories / folded: 24h 6/5 → 3/8 · 3 days 6/7 → 3/10 · week 18/18 → 6/30 · **month 101/89 → 22/165**. Raw NSE subject headlines **23 → 0**. Stories with a summary **7 of 101 → 22 of 22**. Enriching 23 stories cost $0.0037 |
| A ₹55.75 lakh DMart penalty was a top story | Claimed amount parsed from the filing (claim words only, not the company's revenue or net worth) vs market cap; under 0.01% folds as immaterial | DMart: "Immaterial vs size: ₹55.75 lakh vs ₹208,872 cr market cap". Polycab's insolvency petitions over a ₹2.79 cr claim also fold |
| No reason shown for a story's rank | "Why it's here" line on every story | 22 of 22 stories carry one ("Your alert: results", "Large vs size: x% of market cap", "Unusual move: …") |
| Whole-number margins gave false precision ("stagnant at 20.0%") | Operating margin computed as operating profit ÷ sales to one decimal | Jubilant FY24–Q1 FY27: 20%, 20%, 20% → 20.5%, 19.7%, 20.0%, 19.6% |
| Jubilant's CFO at 356% of profit was rated *good* (Ind AS 116) | Lease flag from screener's line items (lease liabilities share, material vs equity) or lease-heavy industry; CFO after lease payments; D/E excluding leases; plausibility bounds; judge told the flags | Cash quality "good" → **"needs adjustment": 356% as reported, 229% after lease payments**. D/E 2.14 → **0.76 excluding leases** (0.06 in FY22: real bank debt is rising). Trent: 123% → 87% after leases. Persistent and L&T unchanged |
| Promised vs delivered couldn't judge operating KPIs | For each promise, later calls **and investor presentations** are scanned for what management reported (ranked by specificity, analyst questions dropped, ~3k characters per document); cheap extraction; five-verdict judge; citations attached in code | Jubilant: 6 of 6 "pending", 4 "no metrics" → **1 delivered, 5 too early (deadlines FY27/FY28), 0 "no data"**. The 1,000-store promise is now evidenced by +114 (Q3 FY26), 351 (FY26), +76 (Q1 FY27), with page numbers. Extra cost ≈ $0.001 per company |
| A blocked NSE meant an empty demo | NSE retries → BSE fallback → committed snapshot with a visible label | Simulated NSE block: 7 filings fetched from BSE. Empty database: 2,963 rows loaded from the seed |
| A screener rate limit showed as "No listed company found" | Rate limits detected, retried with backoff, reported as "Data source busy, try again in a minute" | Simulated 429: 3 attempts, then the busy message (HTTP 503) |
| Cold research took ~60s on one request | Background job with step progress | TITAN (never seen before): job ran to completion, 7 commitments |
| Nothing actually reached out | Optional Telegram alerts, de-duplicated, capped at 10 per refresh, deep link into the story | Format and de-duplication covered by tests; not sent for real (no bot token) |
| Small tap targets; unvalidated holdings | 44px controls; Yahoo validation and immediate fetch; `.BO` fallback; zero-volume days excluded from the average | At 375px: **0 controls under 44×44**, no horizontal scroll. Fake 6.0× spike → correct 3.0× in the zero-volume test |
| Polycab's insolvency petitions were folded as "immaterial" | Red flags (insolvency/NCLT, fraud, regulator orders, auditor or KMP resignations, defaults, pledges) skip the size test | 6 Polycab filings now surface as "Red flag: insolvency petition"; 0 false matches across 193 filings. Month view 22 → 25 stories |
| The cheap model's KPI reading varied run to run | Each document read twice, results merged; a KPI is kept only if its quote is found verbatim in the document; one-reading KPIs are labelled "check the page" | Jubilant KPIs 6 → 11 (the two readings found 6 and 7, agreeing on 2): one pass was missing about half. 0 ungrounded quotes. +≈$0.002 per company |
| Bios were blank when the filing had no profile | Search the company's other recent filings (appointment intimations, board outcomes, postal-ballot notices) and cite the one used; otherwise say no profile exists | HDFC's new General Counsel: blank → "No profile in this or the company's other recent filings" (true for every HDFC filing held) |
| Story-vs-numbers and the case for/against were uncited prose | Numbered, code-computed facts passed to the judge; every point must cite a fact or promise id, resolved in code; uncited points are labelled "Opinion"; quarterly trend labelled in code, with low-base quarters and lender margins excluded | Jubilant: bull/bear 0 of 6 cited → 5 of 6 cited; story claims 2 of 2 cite a fact. Trend: "Revenue YoY slowing: +13.7% vs +17.3% avg of prior 3 quarters" |
| Readers couldn't see the method's limits | "Limits and method" box on every research page: data source, lease proxy, what code computes and what the model judges, this run's KPI agreement | Shown on all research pages |
| A strong-model fallback was cached as the strong answer, so later runs never retried | Fallback answers cached under the cheap model's key | Found while re-running Jubilant |
| No tests | pytest suite | 30 tests pass |

**Cost.** Measured over the whole build: $0.106 in model calls at Gemini list prices; the free tier makes it $0. A new company's first research run is about **$0.009–0.014** (including the second KPI reading); a cached one is free.

**Caveat on the Jubilant output above.** The latest Jubilant analysis was judged by the cheap model: the strong model's free-tier daily quota ran out (HTTP 429) and FINN fell back as designed. Its one uncited point (free cash flow, not lease-adjusted) is labelled "Opinion" on the page. A strong-model re-run is needed once the quota resets. A daily refresh (one batched classification call plus summaries for new stories) is about **$0.001–0.002**.

## Deliberately left out
- Intraday data. The brief asks for end of day, and intraday data would add cost without adding judgement.
- Reading annual reports in full. They're linked; the effort went into transcripts and presentations, where guidance and KPIs live.
- Web push and accounts. Telegram covers "reach out" without a login system.
- Tavily-based executive bios. The code path exists but is untested; bios come from exchange filings only (the filing, the one it references, then the company's other recent filings).
- Extra visual themes. They're built, but hidden behind a flag; the product ships one considered look plus dark mode.

## Next
- Track the promise ledger across years, not just four quarters.
- Read annual-report notes for related-party and contingent-liability changes.
- Scale materiality to other categories, such as orders as a share of revenue.
- A voice version of the Brief for the commute.
