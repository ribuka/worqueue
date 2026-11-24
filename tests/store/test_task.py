"""Tests of reading and writing task files."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from worqueue.store.errors import WorqueueError
from worqueue.store.task import (
    Task,
    append_history,
    body_of,
    initial_markdown,
    read_task,
    replace_body,
    task_ids,
    task_path,
    write_task,
)


def make_task(now: datetime, **changes: object) -> Task:
    """Return a task created at ``now`` with every field set, changed by ``changes``."""
    task = Task(
        id=42,
        title="API の設計をレビューする",
        status="todo",
        kind="manage",
        assignee="me",
        due=date(2026, 11, 27),
        depends_on=(38,),
        created="2026-11-24T09:10:00+09:00",
        markdown=initial_markdown("API のエンドポイントの命名をそろえる。", now),
    )
    return replace(task, **changes)


def test_write_task_writes_the_documented_form(data: Path, now: datetime) -> None:
    """``write_task`` writes the documented form."""
    write_task(data, make_task(now))

    stamp = now.strftime("%Y-%m-%d %H:%M")
    assert task_path(data, 42).read_bytes().decode("utf-8") == (
        "---\n"
        "title: API の設計をレビューする\n"
        "status: todo\n"
        "kind: manage\n"
        "assignee: me\n"
        "due: 2026-11-27\n"
        "depends_on: [38]\n"
        "created: '2026-11-24T09:10:00+09:00'\n"
        "---\n"
        "\n"
        "API のエンドポイントの命名をそろえる。\n"
        "\n"
        "## 履歴\n"
        "\n"
        f"- {stamp} 作成\n"
    )


def test_write_task_without_values_writes_null_and_empty_list(data: Path, now: datetime) -> None:
    """``write_task`` without values writes null and empty list."""
    write_task(data, make_task(now, due=None, depends_on=(), markdown=initial_markdown("", now)))

    text = task_path(data, 42).read_text(encoding="utf-8")
    assert "due: null\n" in text
    assert "depends_on: []\n" in text
    assert "---\n\n## 履歴\n\n- " in text


def test_read_task_returns_what_was_written(data: Path, now: datetime) -> None:
    """``read_task`` returns what was written."""
    task = make_task(now)
    write_task(data, task)

    assert read_task(data, 42) == task


def test_read_task_accepts_unquoted_created(data: Path, now: datetime) -> None:
    """``read_task`` accepts unquoted created."""
    write_task(data, make_task(now))
    path = task_path(data, 42)
    path.write_text(path.read_text(encoding="utf-8").replace("'2026-11-24T09:10:00+09:00'", "2026-11-24T09:10:00+09:00"), encoding="utf-8")

    assert read_task(data, 42).created == "2026-11-24T09:10:00+09:00"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("title: x\n", "front matter（先頭の ---）がありません"),
        ("---\ntitle: x\n", "front matter が閉じていません"),
        ("---\ntitle: x\n---\n", "キーがありません: status, kind, assignee, due, depends_on, created"),
    ],
)
def test_read_task_rejects_a_broken_front_matter(data: Path, text: str, message: str) -> None:
    """``read_task`` rejects a broken front matter."""
    path = task_path(data, 1)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(WorqueueError, match=r"^tasks/1\.md: ") as excinfo:
        read_task(data, 1)
    assert message in str(excinfo.value)


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("status: todo", "status: done!", "status"),
        ("kind: manage", "kind: other", "kind"),
        ("depends_on: [38]", "depends_on: [a]", "depends_on"),
        ("depends_on: [38]", "depends_on: 38", "depends_on"),
        ("due: 2026-11-27", "due: tomorrow", "due"),
        ("due: 2026-11-27", "due: 2026-11-31", "YAML"),
        ("title: API の設計をレビューする", "title: ''", "title"),
        ("created: '2026-11-24T09:10:00+09:00'", "created: '2026-11-24T09:10:00'", "created"),
        ("assignee: me", "assignee: me\nowner: me", "未知のキー"),
    ],
)
def test_read_task_rejects_an_invalid_value(data: Path, now: datetime, old: str, new: str, key: str) -> None:
    """``read_task`` rejects an invalid value."""
    write_task(data, make_task(now))
    path = task_path(data, 42)
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(WorqueueError, match=r"^tasks/42\.md: ") as excinfo:
        read_task(data, 42)
    assert key in str(excinfo.value)


def test_read_task_reports_a_missing_file(data: Path) -> None:
    """``read_task`` reports a missing file."""
    with pytest.raises(WorqueueError, match=r"タスク 7 のファイルがありません: tasks/7\.md"):
        read_task(data, 7)


def test_task_ids_lists_numbered_files_only(data: Path, now: datetime) -> None:
    """``task_ids`` lists numbered files only."""
    write_task(data, make_task(now, id=3))
    write_task(data, make_task(now, id=10))
    (data / "tasks" / "notes.md").write_text("", encoding="utf-8")

    assert sorted(task_ids(data)) == [3, 10]


LINE = "- 2026-11-25 10:00 足した"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        (
            "\n本文\n\n## 履歴\n\n- 2026-11-24 09:10 作成\n",
            f"\n本文\n\n## 履歴\n\n- 2026-11-24 09:10 作成\n{LINE}\n",
        ),
        ("\n## 履歴\n\n- 2026-11-24 09:10 作成\n\n\n", f"\n## 履歴\n\n- 2026-11-24 09:10 作成\n{LINE}\n"),
        ("\n本文\n\n## 履歴\n", f"\n本文\n\n## 履歴\n\n{LINE}\n"),
        ("\n本文\n\n## 履歴\n\n", f"\n本文\n\n## 履歴\n\n{LINE}\n"),
        ("\n## 履歴\n\n- 作成\n\n### メモ\n\n手の行\n", f"\n## 履歴\n\n- 作成\n\n### メモ\n\n手の行\n{LINE}\n"),
        ("\n本文\n", f"\n本文\n\n## 履歴\n\n{LINE}\n"),
        ("\n本文の ## 履歴 は見出しでない", f"\n本文の ## 履歴 は見出しでない\n\n## 履歴\n\n{LINE}\n"),
        ("\n", f"\n## 履歴\n\n{LINE}\n"),
        ("", f"\n## 履歴\n\n{LINE}\n"),
    ],
    ids=[
        "after-entries",
        "trailing-blank-lines",
        "heading-last",
        "heading-last-with-blank",
        "after-other-text",
        "no-heading",
        "heading-text-inside-a-line",
        "empty-newline",
        "empty",
    ],
)
def test_append_history_adds_one_line_at_the_end(markdown: str, expected: str) -> None:
    """``append_history`` adds one line at the end."""
    assert append_history(markdown, LINE) == expected


HISTORY = "## 履歴\n\n- 2026-11-24 09:10 作成\n"


@pytest.mark.parametrize(
    ("markdown", "body", "expected"),
    [
        (f"\n古い本文\n\n{HISTORY}", "新しい本文", f"\n新しい本文\n\n{HISTORY}"),
        (f"\n古い本文\n\n{HISTORY}", "", f"\n{HISTORY}"),
        (f"\n{HISTORY}", "新しい本文", f"\n新しい本文\n\n{HISTORY}"),
        (
            f"\n古い\n\n{HISTORY}\n### メモ\n\n手の行\n",
            "新しい\n2 行目",
            f"\n新しい\n2 行目\n\n{HISTORY}\n### メモ\n\n手の行\n",
        ),
        ("\n古い本文\n", "新しい本文", "\n新しい本文\n"),
        ("\n古い本文\n", "", "\n"),
    ],
    ids=["replace", "to-empty", "from-empty", "keeps-text-after-history", "no-heading", "no-heading-to-empty"],
)
def test_replace_body_replaces_only_the_part_before_the_history(markdown: str, body: str, expected: str) -> None:
    """``replace_body`` replaces the part before the history heading and keeps the rest as it is."""
    assert replace_body(markdown, body) == expected
    assert body_of(expected) == body


@pytest.mark.parametrize(
    ("markdown", "body"),
    [
        (f"\n  本文\n\n2 段落目\n\n{HISTORY}", "本文\n\n2 段落目"),
        (f"\n{HISTORY}", ""),
        ("\n本文だけ\n", "本文だけ"),
        (f"\n本文\n\n{HISTORY}\n## 履歴\n\n- 手の行\n", "本文"),
    ],
    ids=["with-history", "empty", "no-heading", "second-heading"],
)
def test_body_of_returns_the_part_before_the_first_history_heading(markdown: str, body: str) -> None:
    """``body_of`` returns the stripped part before the first history heading."""
    assert body_of(markdown) == body


def test_summary_accepts_no_position(now: datetime) -> None:
    """``summary`` accepts no position."""
    assert make_task(now).summary(None)["position"] is None
