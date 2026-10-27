from finn.brief import red_flag


def test_red_flags_match_real_risk():
    assert red_flag("Corporate Insolvency Resolution Process", "petition filed under Section 9 of IBC") == "insolvency petition"
    assert red_flag("Resignation", "Resignation of Statutory Auditor M/s ABC") == "auditor resignation"
    assert red_flag("Change in Management", "Mr X has resigned as Chief Financial Officer") == "KMP resignation"
    assert red_flag("Disclosure", "Invocation of pledge on promoter shares") == "pledge"


def test_boilerplate_is_not_a_red_flag():
    assert red_flag("Press Release", "pursuant to Regulation 30 of SEBI (LODR) Regulations, 2015") is None
    assert red_flag("Outcome of Board Meeting", "approved the financial results; no default") is None
    assert red_flag("Analyst Meet", "MD and CEO will attend the conference") is None
