"""Tests of ``wq done``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from worqueue.store.queue import write_queue

Git = Callable[..., str]


@pytest.fixture
def tasks(wq: Callable) -> None:
    """Create three tasks; the third depends on the first."""
    wq("add", "仕様を書く", "--kind", "implement")
    wq("add", "見積もる", "--kind", "implement")
    wq("add", "API の設計をレビューする", "--kind", "manage", "--depends-on", "1")


def changed_files(git: Git, data: Path) -> list[str]:
    """Return the files the last commit of data/ changed."""
    return sorted(git(data, "show", "--name-only", "--format=", "HEAD").split())


@pytest.mark.parametrize(
    ("args", "entry"),
    [([], "完了"), (["--reason", "  要らなくなった  "], "完了: 要らなくなった")],
    ids=["without-reason", "with-reason"],
)
def test_done_marks_the_task_done_and_takes_it_out_of_the_queue(
    wq: Callable, tasks: None, data: Path, now: datetime, git: Git, args: list[str], entry: str
) -> None:
    """``wq done`` marks the task done, writes the history, and takes it out of the queue in one commit."""
    dependent = (data / "tasks" / "3.md").read_bytes()

    result = wq("done", "1", *args)

    assert (result.code, result.out) == (0, "完了にしました: 1 仕様を書く\n")
    text = (data / "tasks" / "1.md").read_text(encoding="utf-8")
    assert "\nstatus: done\n" in text
    assert text.endswith(f"作成\n- {now.strftime('%Y-%m-%d %H:%M')} {entry}\n")
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 2\n- 3\n"
    assert [t["id"] for t in json.loads(wq("list", "--json").out)["tasks"]] == [2, 3]
    assert git(data, "log", "-1", "--format=%s") == "done 1: 仕様を書く\n"
    assert changed_files(git, data) == ["queue.md", "tasks/1.md"]
    assert (data / "tasks" / "3.md").read_bytes() == dependent


def test_done_json_prints_the_task_without_a_position(wq: Callable, tasks: None) -> None:
    """``wq done --json`` prints the task with a null position."""
    result = wq("done", "2", "--json")

    assert result.code == 0
    task = json.loads(result.out)["task"]
    assert (task["id"], task["status"], task["position"]) == (2, "done", None)


def test_done_rejects_a_task_already_done_without_writing(wq: Callable, tasks: None, data: Path, git: Git) -> None:
    """``wq done`` rejects a task already ``done`` with exit code 1 and writes nothing."""
    wq("done", "1")
    before = (data / "tasks" / "1.md").read_bytes()

    result = wq("done", "1", "--reason", "2 回目")

    assert (result.code, result.err) == (1, "タスク 1 はもう done です\n")
    assert (data / "tasks" / "1.md").read_bytes() == before
    assert git(data, "rev-list", "--count", "HEAD") == "4\n"


def test_done_out_of_the_queue_leaves_queue_md(wq: Callable, tasks: None, data: Path, git: Git) -> None:
    """``wq done`` on a task not in the queue leaves queue.md and commits only the task file."""
    write_queue(data, [1, 3])
    git(data, "commit", "-q", "-am", "手で外した")

    result = wq("done", "2")

    assert result.code == 0
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 1\n- 3\n"
    assert changed_files(git, data) == ["tasks/2.md"]


def test_done_reports_a_missing_task(wq: Callable) -> None:
    """``wq done`` reports a missing task with exit code 1."""
    result = wq("done", "99")

    assert (result.code, result.err) == (1, "タスク 99 がありません\n")
