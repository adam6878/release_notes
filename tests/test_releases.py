import pytest
from conftest import release


def test_created_release_is_returned_and_listed(client):
    res = client.post("/api/releases", json=release())

    assert res.status_code == 201
    body = res.json()
    assert body["version"] == "1.0.0"
    assert body["id"] and body["created_at"]
    assert client.get("/api/releases").json() == [body]


def test_list_is_newest_first(client):
    for version in ["1.0.0", "1.1.0", "2.0.0"]:
        client.post("/api/releases", json=release(version))

    versions = [r["version"] for r in client.get("/api/releases").json()]

    assert versions == ["2.0.0", "1.1.0", "1.0.0"]


def test_duplicate_version_is_rejected_and_original_kept(client):
    client.post("/api/releases", json=release(title="Original"))

    res = client.post("/api/releases", json=release(title="Duplicate"))

    assert res.status_code == 409
    assert [r["title"] for r in client.get("/api/releases").json()] == ["Original"]


def test_notes_are_optional(client):
    payload = release()
    del payload["notes"]

    res = client.post("/api/releases", json=payload)

    assert res.status_code == 201
    assert res.json()["notes"] == ""


@pytest.mark.parametrize("bad", [
    {"version": ""},
    {"version": "x" * 51},
    {"title": ""},
    {"author": "a" * 101},
])
def test_invalid_input_is_rejected_and_not_stored(client, bad):
    res = client.post("/api/releases", json=release(**bad))

    assert res.status_code == 422
    assert client.get("/api/releases").json() == []


def test_missing_field_is_rejected(client):
    payload = release()
    del payload["title"]

    assert client.post("/api/releases", json=payload).status_code == 422
