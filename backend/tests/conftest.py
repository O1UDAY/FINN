import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("FINN_AUTO_REFRESH", "0")


import pytest  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """A throwaway SQLite database, so tests never touch data/finn.db."""
    import finn.db as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    return db.connect()
