import os
import tempfile

# Settings are read when `app` is imported, so the test database must be set first.
# A real environment variable wins over .env, so a developer's .env is never touched.
# TEST_DATABASE_URL (CI sets it to a throwaway PostgreSQL) runs the same suite against the
# production database engine. It is a separate variable on purpose: the fixture deletes all
# rows, so the suite must never pick up a real DATABASE_URL from someone's shell.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest
from fastapi.testclient import TestClient

from app import engine, releases
from app.main import app


@pytest.fixture
def client():
    # The context manager runs the app's startup (table creation), like uvicorn does.
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        conn.execute(releases.delete())


def release(version="1.0.0", **overrides):
    return {"version": version, "title": "A release", "author": "adam", "notes": "Fixed things", **overrides}
