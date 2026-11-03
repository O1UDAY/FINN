from finn import notify


def test_start_subscribes_and_stop_leaves(monkeypatch, tmp_path):
    import sqlite3
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    monkeypatch.setattr(notify, "connect", lambda: conn)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    sent, queue = [], [[{"update_id": 1, "message": {"chat": {"id": 42, "first_name": "A"}, "text": "/start"}}],
                        [{"update_id": 2, "message": {"chat": {"id": 42}, "text": "/stop"}}]]

    def api(method, **body):
        if method == "getUpdates":
            return queue.pop(0)
        sent.append((body["chat_id"], body["text"][:20]))
    monkeypatch.setattr(notify, "_api", api)
    notify.poll_subscribers()
    assert notify.recipients(conn) == ["42"] and "subscribed" in sent[0][1]
    notify.poll_subscribers()
    assert notify.recipients(conn) == [] and sent[1][1].startswith("Unsubscribed")
