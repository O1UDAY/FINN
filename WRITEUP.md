# FINN — covering note (draft)

**What I built.** FINN is a mobile PWA with two jobs. The **Brief** is a ranked queue of what changed across a 15-stock portfolio: results cards with QoQ/YoY tables, management changes with who the person is, and unusual moves against thresholds the investor sets. Routine filings are folded away, and you swipe cards until it says "All clear". **Interrogate** takes any NSE ticker and checks management against their own words: it pulls promises from the last four concalls and gives each a verdict (delivered / partial / missed / pending) against the reported numbers, with the quote and source link.

**Key decisions.**
- *A queue, not a chat.* An investor's morning is triage, so the core interaction is clearing a list. Research is one tap away from any card.
- *Numbers in code, judgement in the model.* Every ratio, growth rate and signal is computed deterministically. The LLM never does arithmetic. It extracts and judges.
- *A cost funnel.* Rules → regex pre-filter → cheap extraction → one strong judging call → cache. Rule-based classification handles most filings for free, and transcripts are cut about 20× before any model reads them.
- *Graceful without a key.* The whole app runs rules-only, so the demo can't break because of a quota.

**Trade-offs and what I left out.** End-of-day data only (no intraday). No real push notifications (the in-app Brief plays that role). No user accounts. Annual reports are linked but not parsed: they're 300-page PDFs, so I put the effort into transcripts, where the guidance is. Screener's tables stand in for parsing every financial statement myself.

**Next.** Web push for alerts that fire. Parse annual-report notes for related-party and contingent-liability changes. Track the promise ledger across years, not just four quarters. Voice mode for the Brief on the commute.
