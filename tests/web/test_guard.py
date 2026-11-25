"""Tests of the checks of Host and Content-Type."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8765", "localhost:8765"])
def test_a_local_host_is_served(client: TestClient, host: str) -> None:
    """``127.0.0.1`` and ``localhost``, with or without a port, are served."""
    assert client.get("/api/queue", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.evil.example"])
def test_another_host_is_forbidden(client: TestClient, host: str) -> None:
    """Another ``Host`` (as with DNS rebinding) is answered with 403, for the page too."""
    for path in ("/", "/api/queue"):
        response = client.get(path, headers={"Host": host})
        assert response.status_code == 403
        assert response.json() == {"error": "forbidden host"}


def test_a_write_that_is_not_json_is_refused(client: TestClient) -> None:
    """A POST that is not ``application/json`` (as a form of another site sends) is answered with 415."""
    response = client.post(
        "/api/tasks", content='{"title": "a", "kind": "manage"}', headers={"Content-Type": "text/plain"}
    )

    assert response.status_code == 415
    assert response.json() == {"error": "JSON で送ってください"}
    assert client.get("/api/queue").json()["tasks"] == []


def test_a_json_write_with_a_charset_is_accepted(client: TestClient) -> None:
    """``application/json; charset=utf-8`` is JSON."""
    response = client.post(
        "/api/tasks",
        content='{"title": "a", "kind": "manage"}',
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 201
