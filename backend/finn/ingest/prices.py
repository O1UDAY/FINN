"""End-of-day price/volume from Yahoo Finance, plus unusual-move detection."""
import yfinance as yf


def fetch_prices(conn, symbols, period="6mo"):
    tickers = [f"{s}.NS" for s in symbols]
    df = yf.download(tickers, period=period, group_by="ticker", auto_adjust=False, progress=False, threads=True)
    rows = 0
    for s, t in zip(symbols, tickers):
        if t not in df.columns.get_level_values(0):
            continue
        sub = df[t].dropna(subset=["Close"])
        for date, r in sub.iterrows():
            conn.execute(
                "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                (s, date.strftime("%Y-%m-%d"), r["Open"], r["High"], r["Low"], r["Close"], int(r["Volume"])),
            )
            rows += 1
    conn.commit()
    return rows


def detect_moves(conn, symbols, volume_multiple=2.0, price_move_pct=5.0, lookback=20):
    """Return alerts for the latest session where volume or price crosses the user's thresholds."""
    alerts = []
    for s in symbols:
        hist = conn.execute(
            "SELECT date, close, volume FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?",
            (s, lookback + 2),
        ).fetchall()
        if len(hist) < lookback + 2:
            continue
        today, prev, window = hist[0], hist[1], hist[1:lookback + 1]
        avg_vol = sum(r["volume"] for r in window) / len(window)
        vol_x = today["volume"] / avg_vol if avg_vol else 0
        pct = (today["close"] / prev["close"] - 1) * 100
        reasons = []
        if vol_x >= volume_multiple:
            reasons.append(f"volume {vol_x:.1f}x 20d avg")
        if abs(pct) >= price_move_pct:
            reasons.append(f"price {pct:+.1f}%")
        if reasons:
            alerts.append({"symbol": s, "date": today["date"], "close": today["close"],
                           "pct": round(pct, 2), "volume_x": round(vol_x, 2), "reasons": reasons})
    return alerts
