import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import engine, releases
from app.main import app

DEFAULT_TEST_DATABASE_URL = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or DEFAULT_TEST_DATABASE_URL


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(releases.delete())


def release(version: str = "1.0.0", **overrides: str) -> dict[str, str]:
    return {"version": version, "title": "A release", "author": "adam", "notes": "Fixed things", **overrides}
