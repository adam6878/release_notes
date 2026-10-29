import os
import tempfile


DEFUALT_TEST_DATABASE_URL = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or DEFUALT_TEST_DATABASE_URL

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
