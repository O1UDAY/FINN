"""Rule-first announcement classifier. Rules are free; an LLM only sees what they can't place."""
import re

# Order matters: first match wins, so specific patterns go before general ones.
RULES = [
    # Routine paperwork first: its boilerplate mentions SEBI/regulations and would otherwise look like litigation.
    ("unclassified", r"trading window|depositories and participants|allotment of securities|esop|esos|compliance certificate|esg rating|\besg\b"),
    ("press_release", r"bagging|receiving of orders|order win|contract"),
    ("M&A", r"initial public offer|red herring"),
    ("agm_egm", r"sc?rutini[sz]er|voting results"),  # filings misspell it "Srutinizer"
    ("agm_egm", r"scrutini[sz]er"),
    ("earnings_call", r"earnings call|conference call|concall|analysts?/institutional investor meet.*(transcript|audio|recording)|transcript"),
    ("results", r"financial results|outcome of board meeting.*result|quarterly results|audited results|unaudited|results"),
    ("management_change", r"resign|appointment|cessation|change in (director|management|kmp)|chief (executive|financial)|\bceo\b|\bcfo\b|managing director|re-appoint"),
    ("M&A", r"acqui|merger|amalgamation|demerger|joint venture|scheme of arrangement|stake|subsidiary"),
    ("fund_raise", r"rights issue|\bqip\b|preferential|buy ?back|commercial paper|non-convertible|debenture|fund rais|allotment of (ncd|bonds)"),
    ("credit_rating", r"credit rating|rating"),
    ("litigation", r"litigation|penalt|show cause|orders passed|tribunal|nclt|insolvency|\bfine[ds]?\b|dispute|demand notice|tax demand"),
    ("insider_trading", r"insider trading|sast|reg(ulation)? ?7|disclosure under.*(29|31)|acquisition of shares by promoter"),
    ("pledging", r"pledge|encumbrance"),
    ("dividend", r"dividend|record date"),
    ("bonus_split", r"bonus|split|sub-division"),
    ("capex", r"capex|capacity expansion|new plant|commissioning|greenfield|brownfield"),
    ("investor_meetings", r"investor meet|analyst meet|schedule of (analyst|investor)|one-on-one|investor conference"),
    ("postal_ballot", r"postal ballot"),
    ("agm_egm", r"\bagm\b|\begm\b|general meeting"),
    ("press_release", r"press release|order win|bags|wins|launch|partnership|clarification|media release"),
    ("unclassified", r"esop|esos|trading window|compliance certificate|reg(ulation)? ?74|newspaper|loss of share|duplicate share|esg|brsr|certificate"),
]
COMPILED = [(c, re.compile(p, re.I)) for c, p in RULES]
NOTICE = re.compile(r"to announce|is scheduled|scheduled on|to consider and approve|intimation of board meeting|will be held|prior intimation", re.I)

# Within-category judgement: the same category can be headline news or paperwork. First match wins.
ADJUST = [(c, re.compile(p, re.I), imp) for c, p, imp in [
    ("management_change", r"managing director|\bmd\b|chief executive|\bceo\b|chief financial|\bcfo\b|chairman|whole[- ]time director|independent director|additional director", 80),
    ("management_change", r".", 50),  # senior management personnel, CISO, company secretary: worth a line, not a lead
    ("credit_rating", r"upgrad|downgrad|watch|outlook (revised|changed)|negative|withdraw", 75),
    ("credit_rating", r"reaffirm|assign", 40),
    ("M&A", r"incorporat|wholly[- ]owned subsidiary|step[- ]down subsidiary|investment in subsidiary|capital infusion", 45),
    ("press_release", r"foundation|award|recogni[sz]|csr|sustainab|felicitat|ranked", 30),
    ("press_release", r"bagging|receiving of orders|order|contract|wins|launch", 55),
    ("fund_raise", r"allotment|monitoring agency|commercial paper|employee stock option|\besop", 40),
]]

# 0-100: how much a category typically deserves an investor's attention.
IMPORTANCE = {
    "results": 90, "M&A": 85, "management_change": 80, "fund_raise": 75, "litigation": 70,
    "credit_rating": 65, "pledging": 65, "insider_trading": 55, "capex": 60, "bonus_split": 50,
    "dividend": 40, "press_release": 45, "earnings_call": 35, "investor_meetings": 20,
    "agm_egm": 20, "postal_ballot": 15, "unclassified": 5,
}


def classify(subject: str, detail: str = "") -> tuple[str | None, int]:
    text = f"{subject} {detail}"
    for cat, rx in COMPILED:
        if rx.search(text):
            # A board-meeting date for results is a calendar entry, not news; rank it like routine scheduling.
            if cat == "results" and NOTICE.search(text):
                return cat, 25
            for c, rx, imp in ADJUST:
                if c == cat and rx.search(text):
                    return cat, imp
            return cat, IMPORTANCE[cat]
    return None, 30


def rescore(cat: str, text: str, current: int) -> int:
    """Re-apply the within-category rules to richer text (the enrichment), which often says what the NSE line hides,
    e.g. that a 'Credit Rating' filing is a reaffirmation."""
    for c, rx, imp in ADJUST:
        if c == cat and rx.search(text or ""):
            return imp
    return current  # unknown: candidate for LLM fallback
