"""Tests of the operations on data/: locking, writing, and committing."""

import inspect
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from filelock import FileLock

from worqueue.store.errors import WorqueueError
from worqueue.store.lock import write_lock
from worqueue.store.ops import (
    MoveTarget,
    NewTask,
    add_task,
    done_task,
    list_queue,
    log_task,
    move_task,
    show_task,
)
from worqueue.store.queue import read_queue, write_queue
from worqueue.store.task import read_task, write_task

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


@pytest.fixture
def no_global_committer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave git without a committer unless a repository's local settings give one."""
    (tmp_path / "gitconfig").write_text("[user]\n\tuseConfigOnly = true\n", encoding="utf-8")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{role}_NAME")
        monkeypatch.delenv(f"GIT_{role}_EMAIL")


def set_local_committer(git: Git, repo: Path) -> None:
    """Set the committer in a repository's local settings."""
    git(repo, "config", "user.name", "Local")
    git(repo, "config", "user.email", "local@example.com")


def test_add_task_stops_before_writing_when_git_has_no_committer(
    data: Path, now: datetime, no_global_committer: None
) -> None:
    """``add_task`` stops before writing when git has no committer."""
    with pytest.raises(WorqueueError, match="コミットする人"):
        add(data, now)

    assert not data.exists()


@pytest.mark.parametrize("data_exists", [False, True])
def test_add_task_ignores_the_committer_of_a_repository_around_a_new_data(
    tmp_path: Path, now: datetime, git: Git, no_global_committer: None, data_exists: bool
) -> None:
    """``add_task`` ignores the committer of a repository around a new data/, which it would not inherit."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q", "-b", "main")
    set_local_committer(git, outer)
    data = outer / "data"
    if data_exists:
        data.mkdir()

    with pytest.raises(WorqueueError, match="コミットする人"):
        add(data, now)

    assert not (data / "tasks").exists()
    assert not (data / ".git").exists()


def test_add_task_uses_the_committer_of_the_data_repository(
    data: Path, now: datetime, git: Git, no_global_committer: None
) -> None:
    """``add_task`` uses the committer set in the data/ repository's local settings."""
    data.mkdir()
    git(data, "init", "-q", "-b", "main")
    set_local_committer(git, data)

    add(data, now)

    assert git(data, "log", "--format=%cn") == "Local\n"


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


def mark_done_by_hand(data: Path, task_id: int) -> None:
    """Set a task's status to ``done`` in its file, leaving it in ``queue.md``."""
    write_task(data, replace(read_task(data, task_id), status="done"))


@pytest.mark.parametrize(
    "operation",
    [
        lambda data, now: move_task(data, 1, MoveTarget("bottom"), "理由", now, lock_timeout=0.1),
        lambda data, now: done_task(data, 1, "理由", now, lock_timeout=0.1),
        lambda data, now: log_task(data, 1, "内容", now, lock_timeout=0.1),
    ],
    ids=["move", "done", "log"],
)
def test_writing_operations_write_nothing_without_the_lock(
    data: Path, now: datetime, git: Git, operation: Callable[[Path, datetime], object]
) -> None:
    """Writing operations write nothing without the lock."""
    add(data, now)
    add(data, now)
    files = {p.name: p.read_bytes() for p in (data / "tasks").iterdir()}
    queue = (data / "queue.md").read_bytes()

    with FileLock(data / ".lock"), pytest.raises(WorqueueError, match="ロック"):
        operation(data, now)

    assert {p.name: p.read_bytes() for p in (data / "tasks").iterdir()} == files
    assert (data / "queue.md").read_bytes() == queue
    assert commit_count(git, data) == 2


def test_writing_operations_default_to_the_ten_second_lock() -> None:
    """Writing operations default to the ten-second lock."""
    for operation in (move_task, done_task, log_task):
        assert inspect.signature(operation).parameters["lock_timeout"].default == 10


def test_show_task_has_no_position_for_a_done_task_or_one_out_of_the_queue(data: Path, now: datetime) -> None:
    """``show_task`` has no position for a done task or one out of the queue."""
    for _ in range(3):
        add(data, now)
    mark_done_by_hand(data, 1)
    write_queue(data, [1, 2])

    assert [show_task(data, task_id)[1] for task_id in (1, 2, 3)] == [None, 1, None]


@pytest.mark.parametrize(
    ("task_id", "target", "positions", "queue"),
    [
        (4, MoveTarget("top"), (3, 1), [4, 1, 2, 3, 5]),
        (1, MoveTarget("bottom"), (1, 4), [2, 3, 4, 5, 1]),
        (1, MoveTarget("to", 2), (1, 2), [2, 3, 1, 4, 5]),
        (5, MoveTarget("before", 3), (4, 2), [1, 2, 5, 3, 4]),
        (1, MoveTarget("after", 3), (1, 2), [2, 3, 1, 4, 5]),
    ],
    ids=["top", "bottom", "to", "before", "after"],
)
def test_move_task_counts_positions_without_done_tasks_and_keeps_their_lines(
    data: Path,
    now: datetime,
    task_id: int,
    target: MoveTarget,
    positions: tuple[int, int],
    queue: list[int],
) -> None:
    """``move_task`` counts positions without done tasks and keeps their lines."""
    for _ in range(5):
        add(data, now)
    mark_done_by_hand(data, 2)

    _, start, end = move_task(data, task_id, target, None, now)

    assert (start, end) == positions
    assert read_queue(data) == queue
    assert [t.id for t in list_queue(data)] == [i for i in queue if i != 2]


def test_move_task_to_the_same_position_writes_and_commits_nothing(data: Path, now: datetime, git: Git) -> None:
    """``move_task`` to the same position writes and commits nothing."""
    add(data, now)
    add(data, now)
    before = (data / "tasks" / "2.md").read_bytes()

    task, start, end = move_task(data, 2, MoveTarget("bottom"), "理由", now)

    assert (task.id, start, end) == (2, 2, 2)
    assert (data / "tasks" / "2.md").read_bytes() == before
    assert read_queue(data) == [1, 2]
    assert commit_count(git, data) == 2
    assert git(data, "status", "--porcelain") == ""
