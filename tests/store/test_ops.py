"""Tests of the operations on data/: locking, writing, and committing."""

import inspect
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from filelock import FileLock

from worqueue.store.errors import WorqueueError
from worqueue.store.lock import write_lock
from worqueue.store.ops import NewTask, add_task, list_queue
from worqueue.store.queue import read_queue, write_queue

Git = Callable[..., str]


def add(data: Path, now: datetime, title: str = "タスク", **fields: object) -> int:
    """Create a task with ``add_task`` and return its ID."""
    task, _ = add_task(data, NewTask(title=title, kind=fields.pop("kind", "implement"), **fields), now)
    return task.id


def commit_count(git: Git, repo: Path) -> int:
    """Return the number of commits on HEAD."""
    return int(git(repo, "rev-list", "--count", "HEAD"))


def test_add_task_makes_data_a_repository_inside_another_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, now: datetime, git: Git
) -> None:
    """``add_task`` makes data a repository inside another repository."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q", "-b", "main")
    git(outer, "commit", "-q", "--allow-empty", "-m", "outer")
    data = outer / "data"

    add(data, now)

    assert (data / ".git").is_dir()
    assert (data / ".gitignore").read_bytes() == b".lock\n"
    assert commit_count(git, outer) == 1
    assert git(outer, "status", "--porcelain") == "?? data/\n"
    assert git(data, "status", "--porcelain") == ""
    assert git(data, "ls-files").split() == [".gitignore", "next_id", "queue.md", "tasks/1.md"]


def test_add_task_commits_only_the_files_it_wrote(data: Path, now: datetime, git: Git) -> None:
    """``add_task`` commits only the files it wrote."""
    add(data, now, "1 つ目")
    edited = data / "tasks" / "1.md"
    edited.write_bytes(edited.read_bytes() + "- 手で足した行\n".encode())

    add(data, now, "2 つ目")

    changed = git(data, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(changed) == ["next_id", "queue.md", "tasks/2.md"]
    assert git(data, "log", "-1", "--format=%s") == "add 2: 2 つ目\n"
    assert git(data, "status", "--porcelain") == " M tasks/1.md\n"


def test_add_task_does_not_reuse_a_deleted_id(data: Path, now: datetime) -> None:
    """``add_task`` does not reuse a deleted id."""
    add(data, now)
    add(data, now)
    # Deleting a task by hand means deleting its file and its line in queue.md;
    # a queued ID without a file is an error for every operation that reads the queue.
    (data / "tasks" / "2.md").unlink()
    write_queue(data, [1])

    assert add(data, now) == 3


def test_add_task_without_next_id_follows_the_task_files(data: Path, now: datetime) -> None:
    """``add_task`` without ``next_id`` follows the task files."""
    add(data, now)
    add(data, now)
    (data / "next_id").unlink()

    assert add(data, now) == 3
    assert (data / "next_id").read_text(encoding="utf-8") == "4\n"


def test_add_task_appends_to_the_queue_and_reports_the_shown_position(data: Path, now: datetime) -> None:
    """``add_task`` appends to the queue and reports the shown position."""
    add(data, now)
    add(data, now)
    done = data / "tasks" / "1.md"
    done.write_text(done.read_text(encoding="utf-8").replace("status: todo", "status: done"), encoding="utf-8")

    task, position = add_task(data, NewTask(title="3 つ目", kind="manage", depends_on=(1, 2, 1)), now)

    assert read_queue(data) == [1, 2, 3]
    assert position == 2
    assert task.depends_on == (1, 2)


def test_add_task_waits_for_the_lock_and_writes_nothing_on_timeout(data: Path, now: datetime) -> None:
    """``add_task`` waits for the lock and writes nothing on timeout."""
    add(data, now)
    with FileLock(data / ".lock"), pytest.raises(WorqueueError, match="ロック"):
        add_task(data, NewTask(title="待つ", kind="manage"), now, lock_timeout=0.1)

    assert sorted(p.name for p in (data / "tasks").iterdir()) == ["1.md"]
    assert read_queue(data) == [1]


def test_the_lock_waits_ten_seconds_by_default() -> None:
    """The lock waits ten seconds by default."""
    assert inspect.signature(add_task).parameters["lock_timeout"].default == 10
    assert inspect.signature(write_lock).parameters["timeout"].default == 10


def test_add_task_rejects_a_missing_dependency_without_writing(data: Path, now: datetime) -> None:
    """``add_task`` rejects a missing dependency without writing."""
    with pytest.raises(WorqueueError, match="タスク 99 がありません"):
        add(data, now, depends_on=(99,))

    assert not (data / "tasks").exists()
    assert not (data / ".git").exists()


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"title": "  "}, "タイトルが空です"),
        ({"title": "1 行目\n2 行目"}, "タイトルに改行"),
        ({"assignee": ""}, "担当が空です"),
        ({"kind": "other"}, "種別"),
        ({"status": "done"}, "状態"),
    ],
)
def test_add_task_rejects_bad_fields_without_writing(
    data: Path, now: datetime, fields: dict[str, str], message: str
) -> None:
    """``add_task`` rejects bad fields without writing."""
    with pytest.raises(WorqueueError, match=message):
        add(data, now, **fields)

    assert not data.exists()


def test_add_task_stops_before_writing_when_git_has_no_committer(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, now: datetime
) -> None:
    """``add_task`` stops before writing when git has no committer."""
    (tmp_path / "gitconfig").write_text("[user]\n\tuseConfigOnly = true\n", encoding="utf-8")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{role}_NAME")
        monkeypatch.delenv(f"GIT_{role}_EMAIL")

    with pytest.raises(WorqueueError, match="コミットする人"):
        add(data, now)

    assert not data.exists()


def test_add_task_stops_before_writing_without_git(
    data: Path, monkeypatch: pytest.MonkeyPatch, now: datetime
) -> None:
    """``add_task`` stops before writing without git."""
    monkeypatch.setenv("PATH", "")

    with pytest.raises(WorqueueError, match="git が見つかりません"):
        add(data, now)

    assert not data.exists()


def test_add_task_keeps_the_files_when_the_commit_fails(data: Path, now: datetime) -> None:
    """``add_task`` keeps the files when the commit fails."""
    add(data, now)
    hook = data / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    with pytest.raises(WorqueueError, match="ファイルは書きましたが、data/ の git にコミットできませんでした"):
        add(data, now, "2 つ目")

    assert (data / "tasks" / "2.md").is_file()
    assert read_queue(data) == [1, 2]


def test_list_queue_reads_without_creating_data(data: Path) -> None:
    """``list_queue`` reads without creating data."""
    assert list_queue(data) == []
    assert not data.exists()


def test_list_queue_reports_a_queued_task_without_a_file(data: Path, now: datetime) -> None:
    """``list_queue`` reports a queued task without a file."""
    add(data, now)
    (data / "tasks" / "1.md").unlink()

    with pytest.raises(WorqueueError, match="タスク 1 のファイルがありません"):
        list_queue(data)
