"""Operations on data/ (add, list): lock, read, write, and commit as one step."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from worqueue.store.errors import WorqueueError
from worqueue.store.ids import next_id, write_next_id
from worqueue.store.lock import LOCK_TIMEOUT_SECONDS, write_lock
from worqueue.store.queue import read_queue, write_queue
from worqueue.store.repo import check_git, commit, ensure_repo
from worqueue.store.task import (
    KINDS,
    STATUSES,
    Task,
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
