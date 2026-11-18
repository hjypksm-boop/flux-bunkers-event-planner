import os

import pytest


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """A freshly seeded database in a temp dir (never touches data/)."""
    monkeypatch.setenv("FLUX_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from db.database import init_db
    init_db(force_reseed=True)
    yield tmp_path / "test.db"
