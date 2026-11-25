"""Tests of ``wq suggest``."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from worqueue.cli import clock

# The ``now`` fixture is 2026-11-24, when the tasks and their history lines are written.
LATER = timedelta(days=9)


@pytest.fixture
def queue(wq: Callable, monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Create a queue that meets every condition, then move the clock ``LATER``.

    From the top: task 2 (waits for 3), task 3, and task 4 (a member's, due
    2026-12-05, waiting for the ``done`` task 1).
    """
    wq("add", "終わった仕事", "--kind", "implement")
    wq("add", "API を作る", "--kind", "implement")
    wq("add", "仕様を書く", "--kind", "implement")
    wq("add", "API の設計をレビューする", "--kind", "manage", "--assignee", "佐藤", "--due", "2026-12-05",
       "--depends-on", "1")  # fmt: skip
    wq("edit", "2", "--add-depends-on", "3")
    wq("done", "1")
    monkeypatch.setattr(clock, "now", lambda: now + LATER)


def configure(data: Path, body: str) -> None:
    """Write ``config.toml`` with the ``[suggest]`` keys of ``body``."""
    (data / "config.toml").write_text(f"[suggest]\n{body}", encoding="utf-8")


def take_out_of_queue(data: Path, task_id: int) -> None:
    """Remove a task's line from ``queue.md`` by hand."""
    path = data / "queue.md"
    path.write_text(path.read_text(encoding="utf-8").replace(f"- {task_id}\n", ""), encoding="utf-8")


def kinds(wq: Callable) -> dict[int, list[str]]:
    """Return the kinds of ``wq suggest --json`` by task ID."""
    result = wq("suggest", "--json")
    assert result.code == 0
    return {s["task"]["id"]: [r["kind"] for r in s["reasons"]] for s in json.loads(result.out)["suggestions"]}


def test_suggest_prints_one_row_per_reason(wq: Callable, data: Path, queue: None) -> None:
    """``wq suggest`` prints an aligned table with one row per reason, in queue order."""
    configure(data, "top_n = 2\n")

    result = wq("suggest")

    assert result.code == 0
    assert result.out == (
        "#  ID  ASSIGNEE  REASON                              TITLE\n"
        "2  3   me        上の 2 が待っている                 仕様を書く\n"
        "3  4   佐藤      期限まで 2 日（2026-12-05）         API の設計をレビューする\n"
        "3  4   佐藤      着手できる（依存先がすべて done）   API の設計をレビューする\n"
        "3  4   佐藤      追記が 9 日ない（2026-11-24 から）  API の設計をレビューする\n"
    )


def test_suggest_json_prints_each_task_with_its_reasons(
    wq: Callable, data: Path, queue: None, now: datetime
) -> None:
    """``wq suggest --json`` prints the task JSON and the reasons of each suggested task."""
    configure(data, "top_n = 2\n")

    result = wq("suggest", "--json")

    assert result.code == 0
    assert json.loads(result.out) == {
        "suggestions": [
            {
                "task": {
                    "id": 3,
                    "position": 2,
                    "title": "仕様を書く",
                    "status": "todo",
                    "kind": "implement",
                    "assignee": "me",
                    "due": None,
                    "depends_on": [],
                    "created": now.isoformat(),
                },
                "reasons": [{"kind": "blocking", "blocked_ids": [2]}],
            },
            {
                "task": {
                    "id": 4,
                    "position": 3,
                    "title": "API の設計をレビューする",
                    "status": "todo",
                    "kind": "manage",
                    "assignee": "佐藤",
                    "due": "2026-12-05",
                    "depends_on": [1],
                    "created": now.isoformat(),
                },
                "reasons": [
                    {"kind": "due_soon", "days_left": 2},
                    {"kind": "unblocked"},
                    {"kind": "stale", "days": 9, "since": "2026-11-24"},
                ],
            },
        ]
    }


@pytest.mark.parametrize(
    ("due", "text"),
    [
        ("2026-12-04", "期限まで 1 日（2026-12-04）"),
        ("2026-12-03", "期限は今日（2026-12-03）"),
        ("2026-12-01", "期限を 2 日過ぎた（2026-12-01）"),
    ],
)
def test_suggest_words_the_due_date(wq: Callable, data: Path, queue: None, due: str, text: str) -> None:
    """The reason says whether the due date is ahead, today, or past."""
    wq("edit", "4", "--due", due)
    configure(data, "top_n = 2\n")

    assert text in wq("suggest").out


def test_suggest_lists_the_waiting_tasks_in_queue_order(wq: Callable, queue: None) -> None:
    """The reason of a blocking task names every task above that waits for it."""
    wq("edit", "4", "--add-depends-on", "3")
    wq("move", "3", "--bottom")

    assert "上の 2, 4 が待っている" in wq("suggest").out


def test_suggest_follows_the_config(wq: Callable, data: Path, queue: None) -> None:
    """Each threshold of ``config.toml`` changes the result."""
    # With the default top 5, no task of this queue is below the top.
    assert kinds(wq) == {3: ["blocking"], 4: ["unblocked", "stale"]}

    configure(data, "top_n = 2\n")
    assert kinds(wq)[4] == ["due_soon", "unblocked", "stale"]

    configure(data, "top_n = 2\ndue_within_days = 1\n")
    assert kinds(wq)[4] == ["unblocked", "stale"]

    configure(data, "stale_days = 10\n")
    assert kinds(wq)[4] == ["unblocked"]


def test_suggest_reports_a_bad_config(wq: Callable, data: Path, queue: None) -> None:
    """A bad ``config.toml`` is a JSON error naming the key."""
    configure(data, "limit = 3\n")

    result = wq("suggest", "--json")

    assert result.code == 1
    assert "suggest.limit" in json.loads(result.err)["error"]


@pytest.mark.parametrize("status", ["todo", "waiting"])
def test_suggest_reads_a_dependency_out_of_the_queue(
    wq: Callable, data: Path, queue: None, status: str
) -> None:
    """A dependency that is not ``done`` keeps a task blocked even when it is out of the queue."""
    wq("edit", "1", "--status", status)
    take_out_of_queue(data, 1)

    assert kinds(wq) == {3: ["blocking"], 4: ["stale"]}


def test_suggest_treats_a_dependency_without_a_file_as_not_done(wq: Callable, data: Path, queue: None) -> None:
    """A deleted dependency does not unblock a task and is not an error."""
    (data / "tasks" / "1.md").unlink()

    assert kinds(wq) == {3: ["blocking"], 4: ["stale"]}


def test_suggest_reports_a_broken_dependency_file(wq: Callable, data: Path, queue: None) -> None:
    """A dependency file that cannot be read is an error naming it."""
    (data / "tasks" / "1.md").write_text("壊れた\n", encoding="utf-8")

    result = wq("suggest")

    assert result.code == 1
    assert "tasks/1.md" in result.err


@pytest.mark.parametrize("leave", ["done", "out-of-queue"])
def test_suggest_ignores_a_waiting_task_without_a_position(
    wq: Callable, data: Path, queue: None, leave: str
) -> None:
    """A ``done`` task, or one out of the queue, does not make its dependency blocking."""
    if leave == "done":
        wq("done", "2")
    else:
        take_out_of_queue(data, 2)

    assert kinds(wq) == {4: ["unblocked", "stale"]}


def test_suggest_changes_nothing(wq: Callable, data: Path, queue: None, git: Callable[..., str]) -> None:
    """``wq suggest`` takes no lock, writes no file, and commits nothing."""
    configure(data, "top_n = 2\n")
    (data / ".lock").unlink(missing_ok=True)

    def snapshot() -> tuple[dict[str, bytes], str]:
        files = {
            str(path.relative_to(data)): path.read_bytes()
            for path in data.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        return files, git(data, "rev-parse", "HEAD")

    before = snapshot()

    assert wq("suggest").code == 0
    assert wq("suggest", "--json").code == 0

    assert snapshot() == before
    assert not (data / ".lock").exists()


@pytest.mark.parametrize(
    ("args", "out"),
    [([], "指摘はありません\n"), (["--json"], '{\n  "suggestions": []\n}\n')],
)
def test_suggest_without_data_is_empty_and_creates_nothing(
    wq: Callable, data: Path, args: list[str], out: str
) -> None:
    """``wq suggest`` without data has nothing to say and creates nothing."""
    result = wq("suggest", *args)

    assert result.code == 0
    assert result.out == out
    assert not data.exists()
