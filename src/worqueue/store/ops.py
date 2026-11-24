"""Operations on data/ (add, list, show, log, done, move): lock, read, write, and commit as one step."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from worqueue.store.errors import WorqueueError
from worqueue.store.ids import next_id, write_next_id
from worqueue.store.lock import LOCK_TIMEOUT_SECONDS, write_lock
from worqueue.store.queue import read_queue, write_queue
from worqueue.store.repo import check_git, commit, ensure_repo
from worqueue.store.task import (
    KINDS,
    STATUSES,
    Task,
    append_history,
    history_line,
    initial_markdown,
    read_task,
    task_path,
    write_task,
)


@dataclass(frozen=True)
class NewTask:
    """What the caller gives to create a task.

    Attributes
    ----------
    title : str
        One-line name. Surrounding whitespace is removed.
    kind : str
        ``manage`` or ``implement``.
    assignee : str
        ``me`` or a member's name.
    due : date or None
        Due date.
    depends_on : tuple of int
        IDs of existing tasks this task waits for. Duplicates keep the first.
    status : str
        Initial status (``done`` is not allowed: it would not be in the queue).
    body : str
        Description. Empty for none.
    """

    title: str
    kind: str
    assignee: str = "me"
    due: date | None = None
    depends_on: tuple[int, ...] = ()
    status: str = "todo"
    body: str = ""


def add_task(
    data: Path, new: NewTask, now: datetime, lock_timeout: float = LOCK_TIMEOUT_SECONDS
) -> tuple[Task, int]:
    """Create a task at the end of the queue and commit it.

    Parameters
    ----------
    data : Path
        The data/ directory. Created, and made a git repository, if needed.
    new : NewTask
        The task to create.
    now : datetime
        Creation time.
    lock_timeout : float
        Seconds to wait for the write lock.

    Returns
    -------
    tuple of (Task, int)
        The task created and its position among the tasks ``list_queue`` returns.

    Raises
    ------
    WorqueueError
        If the title is invalid, a dependency does not exist, data/ is malformed,
        git is unusable, the lock is not acquired, or the commit fails.
    """
    title = _one_line("タイトル", new.title)
    assignee = _one_line("担当", new.assignee)
    if new.kind not in KINDS:
        raise WorqueueError(f"種別は {', '.join(KINDS)} のどれかにしてください: {new.kind}")
    if new.status not in STATUSES or new.status == "done":
        raise WorqueueError(f"作るタスクの状態は todo, doing, waiting のどれかにしてください: {new.status}")
    def prepare() -> tuple[tuple[Task, int], _Change]:
        depends_on = tuple(dict.fromkeys(new.depends_on))
        for dependency in depends_on:
            if not task_path(data, dependency).is_file():
                raise WorqueueError(f"タスク {dependency} がありません")
        queue = read_queue(data)
        position = len(_shown_tasks(data, queue)) + 1
        task = Task(
            id=next_id(data),
            title=title,
            status=new.status,
            kind=new.kind,
            assignee=assignee,
            due=new.due,
            depends_on=depends_on,
            created=now.astimezone().replace(microsecond=0).isoformat(),
            markdown=initial_markdown(new.body.strip(), now),
        )

        def write() -> list[Path]:
            return [
                write_task(data, task),
                write_next_id(data, task.id + 1),
                write_queue(data, [*queue, task.id]),
            ]

        return (task, position), _Change(write, f"add {task.id}: {task.title}")

    return _write_locked(data, lock_timeout, prepare)


def list_queue(data: Path) -> list[Task]:
    """Return the tasks in the queue from the top, leaving out ``done`` ones.

    Reads only: takes no lock and creates nothing.

    Parameters
    ----------
    data : Path
        The data/ directory. It may not exist.

    Returns
    -------
    list of Task
        Tasks in queue order. A task's position is its index plus one.

    Raises
    ------
    WorqueueError
        If ``queue.md`` or a task file in it is malformed or missing.
    """
    return _shown_tasks(data, read_queue(data))


def show_task(data: Path, task_id: int) -> tuple[Task, int | None]:
    """Return a task and its position.

    Reads only: takes no lock and creates nothing.

    Parameters
    ----------
    data : Path
        The data/ directory. It may not exist.
    task_id : int
        Task ID.

    Returns
    -------
    tuple of (Task, int or None)
        The task, and its position among the tasks ``list_queue`` returns, or None
        if it is not among them (``done``, or not in the queue).

    Raises
    ------
    WorqueueError
        If the task does not exist, or its file, ``queue.md``, or a task file in the
        queue is malformed or missing.
    """
    task = _existing_task(data, task_id)
    return task, _position(_shown_ids(data, read_queue(data)), task_id)


def log_task(
    data: Path, task_id: int, content: str, now: datetime, lock_timeout: float = LOCK_TIMEOUT_SECONDS
) -> tuple[Task, int | None]:
    """Add one entry to a task's history and commit it.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID. A ``done`` task is accepted.
    content : str
        The entry. Surrounding whitespace is removed.
    now : datetime
        Time of the entry.
    lock_timeout : float
        Seconds to wait for the write lock.

    Returns
    -------
    tuple of (Task, int or None)
        The task written and its position, as ``show_task`` returns.

    Raises
    ------
    WorqueueError
        If the content is empty or spans lines, the task does not exist, data/ is
        malformed, git is unusable, the lock is not acquired, or the commit fails.
    """
    content = _one_line("内容", content)

    def prepare() -> tuple[tuple[Task, int | None], _Change]:
        task = _with_history(_existing_task(data, task_id), now, content)
        position = _position(_shown_ids(data, read_queue(data)), task_id)
        return (task, position), _Change(lambda: [write_task(data, task)], f"log {task_id}: {content}")

    return _write_locked(data, lock_timeout, prepare)


def done_task(
    data: Path, task_id: int, reason: str | None, now: datetime, lock_timeout: float = LOCK_TIMEOUT_SECONDS
) -> Task:
    """Mark a task ``done``, take it out of the queue, and commit it.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID.
    reason : str or None
        Why, written in the history. Surrounding whitespace is removed.
    now : datetime
        Time of the history entry.
    lock_timeout : float
        Seconds to wait for the write lock.

    Returns
    -------
    Task
        The task written.

    Raises
    ------
    WorqueueError
        If the reason is empty or spans lines, the task does not exist or is already
        ``done``, data/ is malformed, git is unusable, the lock is not acquired, or
        the commit fails.
    """
    reason = None if reason is None else _one_line("理由", reason)

    def prepare() -> tuple[Task, _Change]:
        task = _existing_task(data, task_id)
        if task.status == "done":
            raise WorqueueError(f"タスク {task_id} はもう done です")
        queue = read_queue(data)
        task = _with_history(replace(task, status="done"), now, "完了" if reason is None else f"完了: {reason}")

        def write() -> list[Path]:
            written = [write_task(data, task)]
            if task_id in queue:
                written.append(write_queue(data, [i for i in queue if i != task_id]))
            return written

        return task, _Change(write, f"done {task_id}: {task.title}")

    return _write_locked(data, lock_timeout, prepare)


@dataclass(frozen=True)
class MoveTarget:
    """Where ``move_task`` puts a task.

    Attributes
    ----------
    where : {"to", "top", "bottom", "before", "after"}
        ``to``: position ``value``. ``top``, ``bottom``: the first or last position.
        ``before``, ``after``: just before or after task ``value``.
    value : int or None
        The position or task ID for ``to``, ``before``, and ``after``; None otherwise.
    """

    where: Literal["to", "top", "bottom", "before", "after"]
    value: int | None = None


def move_task(
    data: Path,
    task_id: int,
    target: MoveTarget,
    reason: str | None,
    now: datetime,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
) -> tuple[Task, int, int]:
    """Move a task within the queue and commit it.

    Positions count the tasks ``list_queue`` returns. Lines of ``done`` tasks left in
    ``queue.md`` keep their order relative to the other lines. Moving a task to where
    it is writes and commits nothing.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID.
    target : MoveTarget
        Where to move it.
    reason : str or None
        Why, written in the history when the task moves. Surrounding whitespace is
        removed.
    now : datetime
        Time of the history entry.
    lock_timeout : float
        Seconds to wait for the write lock.

    Returns
    -------
    tuple of (Task, int, int)
        The task, its position before the move, and its position after it.

    Raises
    ------
    WorqueueError
        If the reason is empty or spans lines, a task does not exist or has no
        position, the target is out of range or the task itself, data/ is malformed,
        git is unusable, the lock is not acquired, or the commit fails.
    """
    reason = None if reason is None else _one_line("理由", reason)

    def prepare() -> tuple[tuple[Task, int, int], _Change | None]:
        task = _existing_task(data, task_id)
        queue = read_queue(data)
        shown = _shown_ids(data, queue)
        if task_id not in shown:
            raise WorqueueError(f"タスク {task_id} はキューにありません")
        others = [i for i in shown if i != task_id]
        index = _target_index(data, task_id, target, shown, others)
        start, end = shown.index(task_id) + 1, index + 1
        if start == end:
            return (task, start, end), None
        rest = [i for i in queue if i != task_id]
        at = rest.index(others[index]) if index < len(others) else len(rest)
        new_queue = [*rest[:at], task_id, *rest[at:]]
        if reason is not None:
            task = _with_history(task, now, f"移動 {start} → {end}: {reason}")

        def write() -> list[Path]:
            written = [write_task(data, task)] if reason is not None else []
            written.append(write_queue(data, new_queue))
            return written

        return (task, start, end), _Change(write, f"move {task_id}: {start} → {end}")

    return _write_locked(data, lock_timeout, prepare)


def _target_index(data: Path, task_id: int, target: MoveTarget, shown: list[int], others: list[int]) -> int:
    """Return the index in ``others`` (``shown`` without the task) to move the task to."""
    if target.where == "top":
        return 0
    if target.where == "bottom":
        return len(others)
    value = target.value
    if value is None:
        raise ValueError(f"MoveTarget({target.where!r}) needs a value")
    if target.where == "to":
        if not 1 <= value <= len(shown):
            raise WorqueueError(f"位置は 1 から {len(shown)} までにしてください: {value}")
        return value - 1
    if not task_path(data, value).is_file():
        raise WorqueueError(f"タスク {value} がありません")
    if value not in shown:
        raise WorqueueError(f"タスク {value} はキューにありません")
    if value == task_id:
        raise WorqueueError(f"タスク {task_id} 自身の前後には動かせません")
    return others.index(value) + (1 if target.where == "after" else 0)


def _existing_task(data: Path, task_id: int) -> Task:
    """Read a task, or raise ``タスク <ID> がありません`` if its file does not exist."""
    if not task_path(data, task_id).is_file():
        raise WorqueueError(f"タスク {task_id} がありません")
    return read_task(data, task_id)


def _with_history(task: Task, at: datetime, content: str) -> Task:
    """Return ``task`` with one history entry added."""
    return replace(task, markdown=append_history(task.markdown, history_line(at, content)))


def _position(shown: list[int], task_id: int) -> int | None:
    """Return the 1-based position of ``task_id`` in ``shown``, or None."""
    return shown.index(task_id) + 1 if task_id in shown else None


def _shown_ids(data: Path, queue: list[int]) -> list[int]:
    """Return the IDs of the tasks of ``queue`` that are not ``done``."""
    return [task.id for task in _shown_tasks(data, queue)]


@dataclass(frozen=True)
class _Change:
    """The files an operation writes and the message of its commit.

    Attributes
    ----------
    write : Callable[[], list[Path]]
        Writes the files, in order, and returns their paths.
    message : str
        Commit message.
    """

    write: Callable[[], list[Path]]
    message: str


def _write_locked[T](data: Path, lock_timeout: float, prepare: Callable[[], tuple[T, _Change | None]]) -> T:
    """Run one write operation: check git, lock, prepare, write, and commit.

    ``prepare`` runs under the lock. It reads the files again and checks the input,
    raising before anything is written, and returns the operation's result with the
    change to make, or ``None`` to write and commit nothing.
    """
    check_git(data)
    data.mkdir(parents=True, exist_ok=True)
    with write_lock(data, lock_timeout):
        result, change = prepare()
        if change is not None:
            written = ensure_repo(data)
            written.extend(change.write())
            commit(data, written, change.message)
    return result


def _one_line(label: str, value: str) -> str:
    """Return ``value`` stripped, or raise if it is empty or spans lines."""
    stripped = value.strip()
    if not stripped:
        raise WorqueueError(f"{label}が空です")
    if "\n" in stripped or "\r" in stripped:
        raise WorqueueError(f"{label}に改行は入れられません")
    return stripped


def _shown_tasks(data: Path, queue: list[int]) -> list[Task]:
    """Read the tasks of ``queue`` and keep those that are not ``done``."""
    tasks = [read_task(data, task_id) for task_id in queue]
    return [task for task in tasks if task.status != "done"]
