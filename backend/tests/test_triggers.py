from finn.ingest.prices import move_stats


def hist(today_close, today_vol, prev_close=100, vols=None):
    vols = vols if vols is not None else [100] * 20
    return [{"close": today_close, "volume": today_vol}] + [{"close": prev_close, "volume": v} for v in vols]


def test_price_move_is_against_previous_close():
    pct, _ = move_stats(hist(106, 100))
    assert round(pct, 1) == 6.0


def test_volume_multiple_excludes_today():
    _, vx = move_stats(hist(100, 300))
    assert round(vx, 2) == 3.0  # 300 vs a 100 average; today not in the average


def test_zero_volume_days_do_not_drag_the_average():
    vols = [0 if i % 2 else 100 for i in range(20)]  # holidays / data gaps
    _, vx = move_stats(hist(100, 300, vols=vols))
    assert round(vx, 2) == 3.0  # would read 6.0 if zeros were averaged in


def test_all_zero_average_cannot_trigger():
    assert move_stats(hist(100, 300, vols=[0] * 20)) is None


def test_too_little_history():
    assert move_stats([{"close": 1, "volume": 1}]) is None
