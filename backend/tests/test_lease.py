from finn.research import lease_flag, margin_series


def test_jubilant_like_lease_heavy_is_flagged():
    flag, reason = lease_flag(["Restaurants"], [3.1, 3.9, 3.4], 0.64, 0.3, lease_to_equity=1.38)
    assert flag and "64%" in reason


def test_small_office_lease_is_not_flagged():
    # Persistent: all of its small debt is leases, but leases are 7% of equity
    flag, _ = lease_flag(["IT - Software"], [1.0, 0.9, 1.1], 1.0, 0.02, lease_to_equity=0.07)
    assert not flag


def test_sustained_cfo_above_150pct_is_flagged_without_line_items():
    flag, reason = lease_flag([], [1.6, 1.8, 1.7, 1.2, 1.9], None, None)
    assert flag and "150%" in reason


def test_margins_are_computed_to_one_decimal():
    assert margin_series([1119, 911], [5755, 5028]) == [19.4, 18.1]
