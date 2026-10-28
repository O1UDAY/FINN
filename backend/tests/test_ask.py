from finn import ask as A

PAGES = ["Board meeting outcome. The Company has allotted commercial paper of Rs 500 crores with a tenure of 90 days. "
         "The coupon is 6.12% and the paper is rated ICRA A1+ by the agency."]


def _setup(monkeypatch, answer):
    monkeypatch.setattr(A, "_docs", lambda symbol, aid: [{"label": "this filing", "url": "u"}])
    monkeypatch.setattr(A, "pages", lambda url: PAGES)
    monkeypatch.setattr(A.llm, "available", lambda: True)
    monkeypatch.setattr(A.llm, "complete_json", lambda *a, **k: answer)


def test_synonyms_widen_plain_words():
    t = A._terms("What amount is involved?")
    assert "amount" in t and "crore" in t and "is" not in t


def test_answer_kept_only_with_a_verbatim_quote(monkeypatch):
    _setup(monkeypatch, {"found": True, "answer": "Rs 500 crores.", "cites": [{"doc": 1, "page": 1, "quote": "commercial paper of Rs 500 crores"}]})
    r = A.ask("DMART", "What amount is involved?", "a1")
    assert r["found"] and r["cites"][0]["page"] == 1


def test_invented_quote_is_rejected(monkeypatch):
    _setup(monkeypatch, {"found": True, "answer": "Rs 900 crores.", "cites": [{"doc": 1, "page": 1, "quote": "a loan of Rs 900 crores from the bank"}]})
    r = A.ask("DMART", "What amount is involved?", "a1")
    assert not r["found"] and not r["cites"]


def test_unreadable_documents_say_so(monkeypatch):
    _setup(monkeypatch, None)
    monkeypatch.setattr(A, "pages", lambda url: [])
    r = A.ask("HDFCBANK", "What is this about?", "a1")
    assert not r["found"] and "Couldn't read" in r["answer"]


def test_cut_off_pdf_is_not_complete():
    from finn.pdftext import _complete
    assert _complete(b"%PDF-1.7 ... trailer\n%%EOF\n")
    assert not _complete(b"%PDF-1.7 ... 5 0 R/Resources 216 0 R/Rotate")


def test_visitor_key_wins_for_its_request_only():
    from finn import llm
    token = llm.USER_KEY.set("visitor-key-123")
    try:
        assert llm.gemini_key() == "visitor-key-123" and llm.provider() == "gemini"
    finally:
        llm.USER_KEY.reset(token)
    assert llm.gemini_key() != "visitor-key-123"


def test_key_format_picks_the_provider():
    from finn import llm
    assert llm.key_provider("sk-ant-api03-abc") == "anthropic"
    assert llm.key_provider("sk-proj-abc") == "openai"
    assert llm.key_provider("AIzaSyabc") == "gemini"
    token = llm.USER_KEY.set("sk-proj-abc")
    try:
        assert llm.provider() == "openai" and llm.key_for("openai") == "sk-proj-abc"
        assert llm.key_for("gemini") != "sk-proj-abc"  # never sent to the wrong service
    finally:
        llm.USER_KEY.reset(token)


def test_model_failure_is_not_reported_as_no_answer(monkeypatch):
    _setup(monkeypatch, None)
    r = A.ask("DMART", "What amount is involved?", "a1")
    assert not r["found"] and "couldn't answer" in r["answer"]
