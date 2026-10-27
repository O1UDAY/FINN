from finn.brief import GENERIC, fallback_headline, is_generic


def test_fallback_never_returns_the_raw_subject():
    subject = "Action(s) initiated or orders passed"
    detail = "Avenue Supermarts Limited has informed the Exchange about Action(s) initiated or orders passed"
    h = fallback_headline("DMART", "litigation", subject, detail, 0.5575)
    assert h.lower() != subject.lower()
    assert h == "DMART: legal matter, ₹55.75 lakh (details in filing)"


def test_fallback_uses_an_informative_description():
    h = fallback_headline("HDFCBANK", "management_change", "Change in Management",
                          "HDFC Bank Limited has informed the Exchange regarding Change in Managing Director and Chief Executive Officer of the Bank")
    assert h.startswith("Change in Managing Director")


def test_every_generic_subject_is_rejected():
    for s in GENERIC:
        assert is_generic(s, s)
        assert fallback_headline("X", "other", s, s).lower() != s
