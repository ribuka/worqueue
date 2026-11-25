"""Tests of ``wq serve``, with the server and the browser replaced."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from worqueue.cli import serve


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace ``uvicorn.run`` and ``webbrowser.open`` with recorders, and return what they received."""
    calls: dict[str, list] = {"run": [], "open": []}
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **options: calls["run"].append((app, options)))
    monkeypatch.setattr(serve.webbrowser, "open", lambda url: calls["open"].append(url))
    return calls


def test_serve_listens_on_localhost_and_opens_the_browser(
    wq: Callable, started: dict[str, list]
) -> None:
    """``wq serve`` serves on 127.0.0.1:8765, opens the URL, and prints it."""
    result = wq("serve")

    assert result.code == 0
    assert result.out == "Worqueue: http://127.0.0.1:8765/ （Ctrl+C で止める）\n"
    [(app, options)] = started["run"]
    assert isinstance(app, FastAPI)
    assert options == {"host": "127.0.0.1", "port": 8765}
    assert started["open"] == ["http://127.0.0.1:8765/"]


def test_serve_takes_a_port_and_can_leave_the_browser_closed(
    wq: Callable, started: dict[str, list]
) -> None:
    """``--port`` changes the port and the URL; ``--no-browser`` opens nothing."""
    result = wq("serve", "--port", "9000", "--no-browser", "--json")

    assert result.code == 0
    assert json.loads(result.out) == {"url": "http://127.0.0.1:9000/"}
    assert started["run"][0][1] == {"host": "127.0.0.1", "port": 9000}
    assert started["open"] == []


def test_serve_rejects_a_port_that_is_not_a_number(wq: Callable, started: dict[str, list]) -> None:
    """A port that is not an integer is an argument error."""
    assert wq("serve", "--port", "abc").code == 2
    assert started["run"] == []


def test_serve_writes_to_data_with_the_clock_of_the_cli(
    wq: Callable, started: dict[str, list], data: Path
) -> None:
    """The app served writes to the data/ of ``WORQUEUE_DATA`` with the CLI's clock."""
    wq("serve", "--no-browser")
    [(app, _)] = started["run"]

    with TestClient(app, base_url="http://127.0.0.1") as client:
        created = client.post("/api/tasks", json={"title": "タスク", "kind": "manage"}).json()["task"]

    assert (data / "tasks" / "1.md").is_file()
    assert datetime.fromisoformat(created["created"]) == datetime(2026, 11, 24, 9, 10, 0).astimezone()
