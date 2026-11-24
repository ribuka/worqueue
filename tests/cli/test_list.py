"""Tests of ``wq list``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def three_tasks(wq: Callable, data: Path) -> None:
    """Create three tasks and mark the second ``done`` by hand, leaving it in queue.md."""
    wq("add", "リリースの判断", "--kind", "manage", "--status", "doing", "--due", "2026-11-24")
    wq("add", "終わった仕事", "--kind", "implement")
    wq("add", "API の設計をレビューする", "--kind", "manage", "--assignee", "佐藤", "--status", "waiting",
       "--due", "2026-11-27", "--depends-on", "1")  # fmt: skip
    path = data / "tasks" / "2.md"
    path.write_text(path.read_text(encoding="utf-8").replace("status: todo", "status: done"), encoding="utf-8")


def test_list_prints_the_queue_as_an_aligned_table(wq: Callable, three_tasks: None) -> None:
    """``wq list`` prints the queue as an aligned table."""
    result = wq("list")

    assert result.code == 0
    assert result.out == (
        "#  ID  STATUS   KIND    ASSIGNEE  DUE         TITLE\n"
        "1  1   doing    manage  me        2026-11-24  リリースの判断\n"
        "2  3   waiting  manage  佐藤      2026-11-27  API の設計をレビューする\n"
    )


def test_list_json_prints_the_shown_tasks(wq: Callable, three_tasks: None, now: datetime) -> None:
    """``wq list --json`` prints the shown tasks."""
    result = wq("list", "--json")

    assert result.code == 0
    assert json.loads(result.out) == {
        "tasks": [
            {
                "id": 1,
                "position": 1,
                "title": "リリースの判断",
                "status": "doing",
                "kind": "manage",
                "assignee": "me",
                "due": "2026-11-24",
                "depends_on": [],
                "created": now.isoformat(),
            },
            {
                "id": 3,
                "position": 2,
                "title": "API の設計をレビューする",
                "status": "waiting",
                "kind": "manage",
                "assignee": "佐藤",
                "due": "2026-11-27",
                "depends_on": [1],
                "created": now.isoformat(),
            },
        ]
    }


def test_list_does_not_write(wq: Callable, three_tasks: None, data: Path, git: Callable[..., str]) -> None:
    """``wq list`` does not write."""
    before = git(data, "status", "--porcelain")

    wq("list")

    assert git(data, "status", "--porcelain") == before
    assert git(data, "rev-list", "--count", "HEAD") == "3\n"


@pytest.mark.parametrize("args", [[], ["--json"]])
def test_list_without_data_is_empty_and_creates_nothing(wq: Callable, data: Path, args: list[str]) -> None:
    """``wq list`` without data is empty and creates nothing."""
    result = wq("list", *args)

    assert result.code == 0
    assert result.out == ("キューは空です\n" if not args else '{\n  "tasks": []\n}\n')
    assert not data.exists()


def test_list_reports_a_broken_task_file(wq: Callable, three_tasks: None, data: Path) -> None:
    """``wq list`` reports a broken task file."""
    (data / "tasks" / "3.md").write_text("壊れた\n", encoding="utf-8")

    result = wq("list", "--json")

    assert result.code == 1
    assert "tasks/3.md" in json.loads(result.err)["error"]


def test_list_reports_a_bad_queue_line(wq: Callable, three_tasks: None, data: Path) -> None:
    """``wq list`` reports a bad queue line."""
    queue = data / "queue.md"
    queue.write_text(queue.read_text(encoding="utf-8") + "* 4\n", encoding="utf-8")

    result = wq("list")

    assert result.code == 1
    assert "queue.md の 6 行目" in result.err


def test_list_reports_a_queued_task_without_a_file(wq: Callable, three_tasks: None, data: Path) -> None:
    """``wq list`` reports a queued task without a file."""
    (data / "tasks" / "3.md").unlink()

    result = wq("list")

    assert result.code == 1
    assert "タスク 3" in result.err
