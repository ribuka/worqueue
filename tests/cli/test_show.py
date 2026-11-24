"""Tests of ``wq show``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

Git = Callable[..., str]


@pytest.fixture
def tasks(wq: Callable) -> None:
    """Create two dependencies, a task with a body, due date, and both dependencies, and a bare task."""
    wq("add", "仕様を書く", "--kind", "implement")
    wq("add", "見積もる", "--kind", "implement")
    wq("add", "API の設計をレビューする", "--kind", "manage", "--assignee", "佐藤", "--status", "waiting",
       "--due", "2026-11-27", "--depends-on", "1", "--depends-on", "2", "--body", "命名をそろえる。")  # fmt: skip
    wq("add", "空のタスク", "--kind", "implement")


def test_show_prints_the_fields_body_and_history(wq: Callable, tasks: None, now: datetime) -> None:
    """``wq show`` prints the fields, the body, and the history."""
    result = wq("show", "3")

    assert result.code == 0
    assert result.out == (
        "ID:         3\n"
        "TITLE:      API の設計をレビューする\n"
        "STATUS:     waiting\n"
        "KIND:       manage\n"
        "ASSIGNEE:   佐藤\n"
        "DUE:        2026-11-27\n"
        "DEPENDS_ON: 1, 2\n"
        f"CREATED:    {now.isoformat()}\n"
        "POSITION:   3\n"
        "\n"
        "命名をそろえる。\n"
        "\n"
        "## 履歴\n"
        "\n"
        f"- {now.strftime('%Y-%m-%d %H:%M')} 作成\n"
    )


def test_show_prints_dashes_for_missing_values(wq: Callable, tasks: None, now: datetime) -> None:
    """``wq show`` prints dashes for missing values."""
    result = wq("show", "4")

    assert result.code == 0
    assert result.out == (
        "ID:         4\n"
        "TITLE:      空のタスク\n"
        "STATUS:     todo\n"
        "KIND:       implement\n"
        "ASSIGNEE:   me\n"
        "DUE:        -\n"
        "DEPENDS_ON: -\n"
        f"CREATED:    {now.isoformat()}\n"
        "POSITION:   4\n"
        "\n"
        "## 履歴\n"
        "\n"
        f"- {now.strftime('%Y-%m-%d %H:%M')} 作成\n"
    )


def test_show_prints_no_blank_line_without_markdown(wq: Callable, tasks: None, data: Path) -> None:
    """``wq show`` prints no blank line when the Markdown is empty."""
    path = data / "tasks" / "4.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.index("---\n", 4) + 4] + "\n\n", encoding="utf-8")

    result = wq("show", "4")

    assert result.code == 0
    assert result.out.endswith("POSITION:   4\n")


def test_show_json_prints_the_task_with_its_markdown(wq: Callable, tasks: None, now: datetime) -> None:
    """``wq show --json`` prints the task with its Markdown."""
    result = wq("show", "3", "--json")

    assert result.code == 0
    assert json.loads(result.out) == {
        "task": {
            "id": 3,
            "position": 3,
            "title": "API の設計をレビューする",
            "status": "waiting",
            "kind": "manage",
            "assignee": "佐藤",
            "due": "2026-11-27",
            "depends_on": [1, 2],
            "created": now.isoformat(),
            "markdown": f"命名をそろえる。\n\n## 履歴\n\n- {now.strftime('%Y-%m-%d %H:%M')} 作成",
        }
    }


def test_show_has_no_position_for_a_done_task(wq: Callable, tasks: None) -> None:
    """``wq show`` has no position for a ``done`` task."""
    wq("done", "1")

    human = wq("show", "1")
    as_json = wq("show", "1", "--json")

    assert "STATUS:     done\n" in human.out
    assert "POSITION:   -\n" in human.out
    assert json.loads(as_json.out)["task"]["position"] is None
    assert json.loads(wq("show", "3", "--json").out)["task"]["position"] == 2


def test_show_writes_nothing(wq: Callable, tasks: None, data: Path, git: Git) -> None:
    """``wq show`` writes nothing."""
    commits = git(data, "rev-list", "--count", "HEAD")

    assert wq("show", "3").code == 0
    assert wq("show", "3", "--json").code == 0

    assert git(data, "status", "--porcelain") == ""
    assert git(data, "rev-list", "--count", "HEAD") == commits


def test_show_reports_a_missing_task(wq: Callable, data: Path) -> None:
    """``wq show`` reports a missing task with exit code 1 and creates nothing."""
    result = wq("show", "99")

    assert (result.code, result.out, result.err) == (1, "", "タスク 99 がありません\n")
    assert not data.exists()


def test_show_rejects_a_non_integer_id(wq: Callable) -> None:
    """``wq show`` rejects an ID that is not an integer with exit code 2."""
    assert wq("show", "abc").code == 2
