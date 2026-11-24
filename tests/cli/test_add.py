"""Tests of ``wq add``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

Git = Callable[..., str]


def test_add_writes_the_task_queue_and_next_id_in_one_commit(
    wq: Callable, data: Path, now: datetime, git: Git
) -> None:
    """``wq add`` writes the task file, queue.md, and next_id in one commit."""
    result = wq(
        "add", "API の設計をレビューする", "--kind", "manage", "--assignee", "佐藤", "--due", "2026-11-27",
        "--body", "命名をそろえる",
    )  # fmt: skip

    assert result.code == 0
    assert result.out == "追加しました: 1 API の設計をレビューする（キューの 1 番目）\n"
    assert (data / "tasks" / "1.md").read_bytes().decode("utf-8") == (
        "---\n"
        "title: API の設計をレビューする\n"
        "status: todo\n"
        "kind: manage\n"
        "assignee: 佐藤\n"
        "due: 2026-11-27\n"
        "depends_on: []\n"
        f"created: '{now.isoformat()}'\n"
        "---\n"
        "\n"
        "命名をそろえる\n"
        "\n"
        "## 履歴\n"
        "\n"
        f"- {now.strftime('%Y-%m-%d %H:%M')} 作成\n"
    )
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 1\n"
    assert (data / "next_id").read_bytes() == b"2\n"
    assert git(data, "log", "--format=%s") == "add 1: API の設計をレビューする\n"


def test_add_json_prints_the_task(wq: Callable, now: datetime) -> None:
    """``wq add --json`` prints the task."""
    wq("add", "仕様を書く", "--kind", "implement")

    result = wq(
        "add", "API の設計をレビューする", "--kind", "manage", "--status", "waiting", "--depends-on", "1",
        "--depends-on", "1", "--json",
    )  # fmt: skip

    assert result.code == 0
    assert json.loads(result.out) == {
        "task": {
            "id": 2,
            "position": 2,
            "title": "API の設計をレビューする",
            "status": "waiting",
            "kind": "manage",
            "assignee": "me",
            "due": None,
            "depends_on": [1],
            "created": now.isoformat(),
        }
    }


@pytest.mark.parametrize(
    "args",
    [
        ["--kind", "other"],
        [],
        ["--kind", "manage", "--status", "done"],
        ["--kind", "manage", "--due", "2026-11-31"],
        ["--kind", "manage", "--due", "2026-1-5"],
        ["--kind", "manage", "--depends-on", "x"],
    ],
)
def test_add_rejects_bad_arguments_with_exit_code_2(wq: Callable, data: Path, args: list[str]) -> None:
    """``wq add`` rejects bad arguments with exit code 2."""
    result = wq("add", "タスク", *args)

    assert result.code == 2
    assert result.err
    assert not data.exists()


def test_add_reports_a_missing_dependency(wq: Callable) -> None:
    """``wq add`` reports a missing dependency."""
    result = wq("add", "タスク", "--kind", "manage", "--depends-on", "99")

    assert (result.code, result.out, result.err) == (1, "", "タスク 99 がありません\n")


def test_add_json_reports_an_error_as_json(wq: Callable) -> None:
    """``wq add --json`` reports an error as json."""
    result = wq("add", "タスク", "--kind", "manage", "--depends-on", "99", "--json")

    assert result.code == 1
    assert result.out == ""
    assert json.loads(result.err) == {"error": "タスク 99 がありません"}


@pytest.mark.parametrize(("title", "message"), [(" ", "タイトルが空です"), ("a\nb", "タイトルに改行")])
def test_add_rejects_a_bad_title_with_exit_code_1(wq: Callable, data: Path, title: str, message: str) -> None:
    """``wq add`` rejects a bad title with exit code 1."""
    result = wq("add", title, "--kind", "manage")

    assert result.code == 1
    assert message in result.err
    assert not data.exists()
