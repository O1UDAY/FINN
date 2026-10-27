from finn.materiality import immaterial_line, materiality, parse_amount_cr


def test_dmart_penalty_is_immaterial():
    # ₹55.75 lakh penalty against ~₹2.09 lakh crore market cap (0.0003%)
    material, ratio = materiality(0.5575, 208872)
    assert material is False and ratio < 1e-4
    assert immaterial_line(0.5575, 208872) == "Immaterial vs size: ₹55.75 lakh vs ₹208,872 cr market cap"


def test_large_claim_is_material():
    material, ratio = materiality(500, 116300)  # 0.43% of market cap
    assert material is True and round(ratio * 100, 2) == 0.43


def test_no_amount_or_no_mcap_cannot_be_judged():
    assert materiality(None, 1000) == (None, None)
    assert materiality(10, None) == (None, None)


def test_parse_units():
    assert parse_amount_cr("a penalty of Rs. 55,75,000/-") == 0.5575
    assert parse_amount_cr("imposed a fine of ₹ 55.75 lakh") == 0.5575
    assert parse_amount_cr("alleged operational debt of ₹2.79 crore") == 2.79
    assert parse_amount_cr("tax demand of INR 12.5 million") == 1.25


def test_company_context_figures_are_not_claims():
    # Filings quote revenue, net worth and market cap; none of these is the amount in dispute.
    text = ("revenue was INR 2,81,851.77 million and a market capitalisation of INR 1,030.29 billion. "
            "net-worth of Rs.11,682 crores. alleged operational debt of ₹2.79 crore")
    assert parse_amount_cr(text) == 2.79
