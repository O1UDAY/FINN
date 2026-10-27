from finn.enrich import derive_ebitda, results_headline
from finn.screener import _row


def test_ebitda_derivation_matches_lt_q2_fy27():
    # L&T consolidated, Q2 FY27 / Q1 FY27 / Q2 FY26, figures as printed in the results filing (₹ crore)
    pbt = [7641.06, 6922.26, 6336.11]
    finance_costs = [472.94, 538.67, 762.81]
    depreciation = [1036.91, 1032.28, 1091.77]
    other_income = [2306.26, 2376.73, 1384.28]
    assert derive_ebitda(pbt, finance_costs, depreciation, other_income) == [6844.65, 6116.48, 6806.41]


def test_qoq_yoy_math():
    r = _row("Revenue", 78749.94, 67941.74, 67983.53)
    assert (r["qoq"], r["yoy"]) == (15.9, 15.8)
    r = _row("PAT", 5202.10, 4122.85, 3926.09)
    assert (r["qoq"], r["yoy"]) == (26.2, 32.5)


def test_growth_undefined_on_negative_or_zero_base():
    assert _row("EBITDA", 100, -50, 0)["qoq"] is None
    assert _row("EBITDA", 100, -50, 0)["yoy"] is None


def test_results_headline_is_computed_and_honest():
    rows = [{"metric": "Revenue", "yoy": 15.8}, {"metric": "EBITDA", "yoy": 0.6}, {"metric": "PAT", "yoy": 32.5}]
    assert results_headline(rows) == "Revenue up 16% on last year, EBITDA flat, PAT up 33%"
