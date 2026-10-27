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
