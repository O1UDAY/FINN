from finn.research import _grounded, attach_facts, quarter_trend


def test_trend_labels_acceleration_in_code():
    cols = [f"Q{i}" for i in range(8)]
    sales = [100, 100, 100, 100, 110, 110, 110, 125]  # YoY 10, 10, 10, then 25
    t = quarter_trend(cols, sales, None, None)
    assert t[0]["text"].startswith("Revenue YoY accelerating: +25.0%")


def test_low_base_is_not_called_a_trend():
    t = quarter_trend(list("abcdefgh"), None, [10, 10, 10, 10, 40, 12, 12, 12], None)
    assert "low base" in t[0]["text"]


def test_kpi_quote_must_be_in_document():
    pages = ["We added net 76 new stores during the quarter, taking the total to 3,480."]
    assert _grounded("added net 76 new stores during the quarter", pages)
    assert not _grounded("added net 90 new stores during the quarter", pages)


def test_case_points_resolve_citations():
    j = {"bull": [{"point": "Growth", "cites": ["F1", "P2"]}, {"point": "Vibes", "cites": []}], "bear": ["old string"]}
    attach_facts(j, {"F1": "Revenue 3y CAGR 22.6%"})
    assert j["bull"][0]["facts"] == [{"id": "F1", "text": "Revenue 3y CAGR 22.6%"}] and j["bull"][0]["promises"] == ["P2"]
    assert j["bull"][1]["uncited"] and j["bear"][0]["uncited"]
