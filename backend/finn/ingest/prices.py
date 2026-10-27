"""End-of-day price/volume from Yahoo Finance (.NS first, .BO when NSE has nothing), plus unusual-move detection."""
import yfinance as yf


def _history(ticker, period):
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    except Exception:
        return None
    return df.dropna(subset=["Close"]) if df is not None and not df.empty else None


def resolve_ticker(symbol, period="5d"):
    """'TITAN' -> 'TITAN.NS' if Yahoo has NSE data, else 'TITAN.BO', else None (not listed / typo)."""
    for t in (f"{symbol}.NS", f"{symbol}.BO"):
        if _history(t, period) is not None:
            return t
    return None


def _store(conn, symbol, df):
    for date, r in df.iterrows():
        conn.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                     (symbol, date.strftime("%Y-%m-%d"), r["Open"], r["High"], r["Low"], r["Close"], int(r["Volume"])))
    return len(df)


def fetch_prices(conn, symbols, period="6mo"):
    tickers = [f"{s}.NS" for s in symbols]
    df = yf.download(tickers, period=period, group_by="ticker", auto_adjust=False, progress=False, threads=True)
    rows, missing = 0, []
    for s, t in zip(symbols, tickers):
        sub = df[t].dropna(subset=["Close"]) if t in df.columns.get_level_values(0) else None
        if sub is None or sub.empty:
            missing.append(s)
            continue
        rows += _store(conn, s, sub)
    for s in missing:  # BSE-only or NSE gap: try the .BO listing
        sub = _history(f"{s}.BO", period)
        if sub is not None:
            rows += _store(conn, s, sub)
            print(f"prices: {s} from .BO")
    conn.commit()
    return rows


def move_stats(history, lookback=20):
    """history: newest first, dicts with close and volume. Returns (pct vs previous close, volume multiple) or None.
    The average excludes today and zero-volume days (holidays, data gaps), which would otherwise drag it down
    and make normal volume look like a spike."""
    if len(history) < 2:
        return None
    today, prev = history[0], history[1]
    window = [r["volume"] for r in history[1:lookback + 1] if r["volume"]]
    if len(window) < 5 or not prev["close"]:
        return None
    avg_vol = sum(window) / len(window)
    vol_x = today["volume"] / avg_vol if avg_vol else 0
    pct = (today["close"] / prev["close"] - 1) * 100
    return pct, vol_x


def detect_moves(conn, symbols, volume_multiple=2.0, price_move_pct=5.0, lookback=20):
    """Return alerts for the latest session where volume or price crosses the user's thresholds."""
    alerts = []
    for s in symbols:
        hist = conn.execute("SELECT date, close, volume FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?",
                            (s, lookback + 10)).fetchall()
        stats = move_stats([dict(r) for r in hist], lookback)
        if not stats:
            continue
        pct, vol_x = stats
        reasons = []
        if vol_x >= volume_multiple:
            reasons.append(f"volume {vol_x:.1f}x 20d avg")
        if abs(pct) >= price_move_pct:
            reasons.append(f"price {pct:+.1f}%")
        if reasons:
            alerts.append({"symbol": s, "date": hist[0]["date"], "close": hist[0]["close"],
                           "pct": round(pct, 2), "volume_x": round(vol_x, 2), "reasons": reasons})
    return alerts
