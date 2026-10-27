from finn import notify


def test_alerts_are_never_sent_twice(tmp_db):
    cards = [{"id": "a1", "alert": True}, {"id": "a2", "alert": True}, {"id": "b", "alert": False}]
    assert [c["id"] for c in notify.new_alerts(tmp_db, cards)] == ["a1", "a2"]
    notify.mark(tmp_db, ["a1"], "telegram")
    assert [c["id"] for c in notify.new_alerts(tmp_db, cards)] == ["a2"]
    notify.mark(tmp_db, ["a1", "a2"], "telegram")  # re-marking is harmless
    assert notify.new_alerts(tmp_db, cards) == []


def test_message_is_one_tight_line_plus_link():
    card = {"id": "px-LT-2026-10-27", "kind": "move", "symbol": "LT", "why": "Unusual move: volume 2.3x 20d avg",
            "move": {"pct": -4.2, "volume_x": 2.3, "close": 3612.5}}
    msg = notify.format_alert(card)
    assert msg.count("\n") == 2 and "LT down 4.2%, 2.3× volume" in msg and "/?story=px-LT-2026-10-27" in msg


def test_admin_refresh_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    monkeypatch.setattr(app_module, "_refresh", lambda: True)
    c = TestClient(app_module.app)
    monkeypatch.delenv("FINN_ADMIN_TOKEN", raising=False)
    assert c.post("/api/admin/refresh").status_code == 503
    monkeypatch.setenv("FINN_ADMIN_TOKEN", "s3cret")
    assert c.post("/api/admin/refresh").status_code == 401
    assert c.post("/api/admin/refresh", headers={"X-Admin-Token": "s3cret"}).json()["started"] is True
