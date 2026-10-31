from http import HTTPStatus

import pytest
from conftest import release
from fastapi.testclient import TestClient


def test_created_release_is_returned_and_listed(client: TestClient) -> None:
    res = client.post("/api/releases", json=release())

    assert res.status_code == HTTPStatus.CREATED
    body = res.json()
    assert body["version"] == "1.0.0"
    assert body["id"] and body["created_at"]
    assert client.get("/api/releases").json() == [body]


def test_list_is_newest_first(client: TestClient) -> None:
    for version in ["1.0.0", "1.1.0", "2.0.0"]:
        client.post("/api/releases", json=release(version))

    versions = [r["version"] for r in client.get("/api/releases").json()]

    assert versions == ["2.0.0", "1.1.0", "1.0.0"]


def test_duplicate_version_is_rejected_and_original_kept(client: TestClient) -> None:
    client.post("/api/releases", json=release(title="Original"))

    res = client.post("/api/releases", json=release(title="Duplicate"))

    assert res.status_code == HTTPStatus.CONFLICT
    assert [r["title"] for r in client.get("/api/releases").json()] == ["Original"]


def test_notes_are_optional(client: TestClient) -> None:
    payload = release()
    del payload["notes"]

    res = client.post("/api/releases", json=payload)

    assert res.status_code == HTTPStatus.CREATED
    assert res.json()["notes"] == ""


@pytest.mark.parametrize("invalid_input", [
    {"version": ""},
    {"version": "x" * 51},
    {"version": "1.2"},
    {"version": "v1.2.3"},
    {"version": "1.2.3\n"},
    {"title": ""},
    {"author": "a" * 101},
    {"notes": "n" * 501},
])
def test_invalid_input_is_rejected_and_not_stored(client: TestClient, invalid_input: dict[str, str]) -> None:
    res = client.post("/api/releases", json=release(**invalid_input))

    assert res.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert client.get("/api/releases").json() == []


def test_missing_field_is_rejected(client: TestClient) -> None:
    payload = release()
    del payload["title"]

    assert client.post("/api/releases", json=payload).status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_version_is_reported(client: TestClient) -> None:
    assert client.get("/api/version").json() == {"version": "dev"}
