"""Portfolio, research set and default alert thresholds."""
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "finn.db"

PORTFOLIO = [
    "RELIANCE", "HDFCBANK", "INFY", "TCS", "ITC", "BAJFINANCE", "TMPV",
    "SUNPHARMA", "LT", "ASIANPAINT", "DMART", "ETERNAL", "DIXON", "POLYCAB", "IRCTC",
]

RESEARCH = ["TRENT", "PERSISTENT", "KAYNES", "CDSL"]

DEFAULT_THRESHOLDS = {
    "volume_multiple": 2.0,   # volume vs 20-day average
    "price_move_pct": 5.0,    # absolute daily % change
    "categories": ["results", "M&A", "management_change", "fund_raise", "litigation", "credit_rating"],
}

# BSE scrip codes, for the announcements fallback when NSE refuses the server.
BSE_CODES = {
    "RELIANCE": "500325", "HDFCBANK": "500180", "INFY": "500209", "TCS": "532540", "ITC": "500875",
    "BAJFINANCE": "500034", "TMPV": "500570", "SUNPHARMA": "524715", "LT": "500510", "ASIANPAINT": "500820",
    "DMART": "540376", "ETERNAL": "543320", "DIXON": "540699", "POLYCAB": "542652", "IRCTC": "542830",
    "TRENT": "500251", "PERSISTENT": "533179", "KAYNES": "543664", "CDSL": "543256", "JUBLFOOD": "533155",
}
