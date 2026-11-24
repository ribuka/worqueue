"""Tests of ``wq log``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

Git = Callable[..., str]


def test_log_appends_lines_to_the_history_in_one_commit_each(
    wq: Callable, data: Path, now: datetime, git: Git
) -> None:
    """``wq log`` appends a line to the history and makes one commit each time."""
    wq("add", "API の設計をレビューする", "--kind", "manage", "--body", "命名をそろえる")

    first = wq("log", "1", "  佐藤さんに依頼  ")
    second = wq("log", "1", "38 番の仕様待ち")

    assert (first.code, first.out) == (0, "履歴に書きました: 1 API の設計をレビューする\n")
    assert second.code == 0
    stamp = now.strftime("%Y-%m-%d %H:%M")
    assert (data / "tasks" / "1.md").read_bytes().decode("utf-8") == (
        "---\n"
        "title: API の設計をレビューする\n"
        "status: todo\n"
        "kind: manage\n"
        "assignee: me\n"
        "due: null\n"
        "depends_on: []\n"
        f"created: '{now.isoformat()}'\n"
        "---\n"
        "\n"
        "命名をそろえる\n"
        "\n"
        "## 履歴\n"
        "\n"
        f"- {stamp} 作成\n"
        f"- {stamp} 佐藤さんに依頼\n"
        f"- {stamp} 38 番の仕様待ち\n"
    )
    assert git(data, "log", "--format=%s").splitlines() == [
        "log 1: 38 番の仕様待ち",
        "log 1: 佐藤さんに依頼",
        "add 1: API の設計をレビューする",
    ]
    assert git(data, "show", "--name-only", "--format=", "HEAD").split() == ["tasks/1.md"]


def test_log_json_prints_the_task_with_its_position(wq: Callable) -> None:
    """``wq log --json`` prints the task with its position."""
    wq("add", "仕様を書く", "--kind", "implement")
    wq("add", "見積もる", "--kind", "implement")

    result = wq("log", "2", "メモ", "--json")

    assert result.code == 0
    task = json.loads(result.out)["task"]
    assert (task["id"], task["position"], task["title"]) == (2, 2, "見積もる")


def test_log_writes_to_a_done_task(wq: Callable, data: Path) -> None:
    """``wq log`` writes to a ``done`` task, whose position is null."""
    wq("add", "仕様を書く", "--kind", "implement")
    wq("done", "1")

    result = wq("log", "1", "あとで見直した", "--json")

    assert result.code == 0
    assert json.loads(result.out)["task"]["position"] is None
    assert (data / "tasks" / "1.md").read_text(encoding="utf-8").endswith(" あとで見直した\n")


@pytest.mark.parametrize(
    ("content", "message"),
    [("  ", "内容が空です"), ("1 行目\n2 行目", "内容に改行は入れられません")],
    ids=["empty", "newline"],
)
def test_log_rejects_bad_content_without_writing(
    wq: Callable, data: Path, git: Git, content: str, message: str
) -> None:
    """``wq log`` rejects empty or multi-line content with exit code 1 and writes nothing."""
    wq("add", "仕様を書く", "--kind", "implement")
    before = (data / "tasks" / "1.md").read_bytes()

    result = wq("log", "1", content)

    assert (result.code, result.err) == (1, f"{message}\n")
    assert (data / "tasks" / "1.md").read_bytes() == before
    assert git(data, "rev-list", "--count", "HEAD") == "1\n"


def test_log_reports_a_missing_task(wq: Callable) -> None:
    """``wq log`` reports a missing task as JSON with exit code 1."""
    result = wq("log", "99", "メモ", "--json")

    assert (result.code, json.loads(result.err)) == (1, {"error": "タスク 99 がありません"})
