from http import HTTPStatus
from typing import Any

import pytest
from conftest import release
from fastapi.testclient import TestClient
from sqlalchemy import create_engine


def test_liveness_is_ok(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readiness_is_ok_when_database_is_reachable(client: TestClient) -> None:
    res = client.get("/readyz")

    assert res.status_code == HTTPStatus.OK
    assert res.json() == {"status": "ready"}


def test_readiness_fails_when_database_is_unreachable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # A real connection failure: SQLite cannot open a file in a directory that does not exist.
    monkeypatch.setattr("app.routers.health.engine", create_engine("sqlite:///no-such-dir/x.db"))

    assert client.get("/readyz").status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert client.get("/healthz").status_code == HTTPStatus.OK  # liveness must not depend on the database


def test_metrics_count_requests_by_route_and_status(client: TestClient) -> None:
    client.post("/api/releases", json=release())
    client.post("/api/releases", json=release())  # duplicate -> 409

    body = client.get("/metrics").text

    assert 'http_requests_total{method="POST",path="/api/releases",status="201"}' in body
    assert 'http_requests_total{method="POST",path="/api/releases",status="409"}' in body
    assert "http_request_duration_seconds_bucket" in body


def test_unknown_urls_do_not_create_new_metric_labels(client: TestClient) -> None:
    client.get("/no-such-page-7f3a")

    body = client.get("/metrics").text

    assert "no-such-page-7f3a" not in body
    assert 'path="other",status="404"' in body


def test_requests_are_logged_but_probes_are_not(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr("app.middleware.log.info", lambda msg, extra: logged.append(extra["fields"]))

    client.get("/healthz")
    client.get("/readyz")
    client.get("/metrics")
    client.post("/api/releases", json=release())

    assert [(f["method"], f["path"], f["status"]) for f in logged] == [("POST", "/api/releases", HTTPStatus.CREATED)]
    assert logged[0]["duration_ms"] >= 0
