"""Size-aware materiality for legal and regulatory filings.

A ₹55 lakh penalty is news for a small cap and noise for a ₹2.5 lakh crore company. The rule is a pure function so it
can be tested; the amount comes from the filing itself (regex, no model), the market cap from screener's page cache.
"""
import re

IMMATERIAL_SHARE = 1e-4  # 0.01% of market cap
SIZE_CHECKED = {"litigation"}

_AMT = re.compile(
    r"(?:₹|rs\.?|inr|rupees)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|million|mn|billion|bn)?"
    r"|([\d,]+(?:\.\d+)?)\s*(crores?|lakhs?|lacs?)\b",
    re.I)
_UNIT = {"crore": 1, "cr": 1, "lakh": 0.01, "lac": 0.01, "million": 0.1, "mn": 0.1, "billion": 100, "bn": 100}


CLAIM = re.compile(r"penalt|fine|demand|claim|debt|dues|default|levied|imposed|liabilit|damages|sought|amounting|sum of|amount of|interest of|tax of", re.I)
CONTEXT = re.compile(r"revenue|turnover|market capitali|net[- ]worth|net cash|working capital|limits|dividend|taxes aggregat|profit", re.I)


def parse_amount_cr(text: str) -> float | None:
    """Largest *claimed* rupee amount, in ₹ crore: only figures that follow claim words (penalty, demand, debt...).
    Filings also quote the company's revenue, net worth and market cap as context; taking the largest figure overall
    turned a ₹2.79 crore claim into ₹1 lakh crore. Bare rupee figures (Rs. 55,75,000) are converted from rupees."""
    best = None
    text = re.sub(r"\s+", " ", text or "")
    for m in _AMT.finditer(text):
        before = text[max(0, m.start() - 70):m.start()]
        if not CLAIM.search(before) or CONTEXT.search(before[-40:]):
            continue
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if unit:
            key = unit.lower().rstrip(".").rstrip("s")
            v *= _UNIT.get(key, 1)
        else:
            if v < 1000:  # "Rs. 5" with no unit is a page number or a share price, not a penalty
                continue
            v /= 1e7
        best = v if best is None else max(best, v)
    return best


def materiality(amount_cr: float | None, mcap_cr: float | None, share=IMMATERIAL_SHARE):
    """(is_material, share_of_mcap). None when it can't be judged, so the item keeps its category score."""
    if not amount_cr or not mcap_cr or mcap_cr <= 0:
        return None, None
    ratio = amount_cr / mcap_cr
    return ratio >= share, ratio


def fmt_cr(v: float) -> str:
    if v < 1:
        return f"₹{v * 100:,.2f} lakh"
    return f"₹{v:,.2f} cr" if v < 100 else f"₹{v:,.0f} cr"


def immaterial_line(amount_cr, mcap_cr):
    return f"Immaterial vs size: {fmt_cr(amount_cr)} vs ₹{mcap_cr:,.0f} cr market cap"


def check_filing(conn, ann: dict) -> dict:
    """Parse the amount from the filing, compare with market cap, persist the result on the announcement row."""
    from .pdftext import pages
    from .screener import company
    text = (ann.get("detail") or "") + "\n" + "\n".join(pages(ann.get("attachment") or "")[:3])
    amount = parse_amount_cr(text)
    mcap = None
    if amount:
        try:
            mcap = company(ann["symbol"])["ratios"].get("Market Cap")
        except Exception:
            mcap = None
    material, _ = materiality(amount, mcap)
    conn.execute("UPDATE announcements SET amount_cr=?, mcap_cr=?, material=? WHERE id=?",
                 (amount, mcap, None if material is None else int(material), ann["id"]))
    conn.commit()
    return {"amount_cr": amount, "mcap_cr": mcap, "material": material}
