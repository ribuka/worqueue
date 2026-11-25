"""Operations on data/ (add, list, list_done, show, log, done, move, edit): lock, read, write, and commit as one step."""

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
    HISTORY_HEADING,
    KINDS,
    MY_ASSIGNEE,
    OPEN_STATUSES,
    Task,
    append_history,
    body_of,
    history_line,
    initial_markdown,
    read_task,
    replace_body,
    task_ids,
    task_path,
    write_task,
)
from worqueue.store.versions import FileVersion, check_versions


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
    assignee: str = MY_ASSIGNEE
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
    if new.status not in OPEN_STATUSES:
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


def list_done(data: Path) -> list[Task]:
    """Return the ``done`` tasks, the largest ID first.

    Reads only: takes no lock and creates nothing.

    Parameters
    ----------
    data : Path
        The data/ directory. It may not exist.

    Returns
    -------
    list of Task
        Every task in ``tasks/`` whose status is ``done``, in or out of the queue.

    Raises
    ------
    WorqueueError
        If a task file (of any status) is malformed.
    """
    tasks = [read_task(data, task_id) for task_id in sorted(task_ids(data), reverse=True)]
    return [task for task in tasks if task.status == "done"]


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
    data: Path,
    task_id: int,
    content: str,
    now: datetime,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
    *,
    expected: tuple[FileVersion, ...] = (),
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
    expected : tuple of FileVersion
        Versions of the files the caller read, checked under the lock before
        anything is read or written.

    Returns
    -------
    tuple of (Task, int or None)
        The task written and its position, as ``show_task`` returns.

    Raises
    ------
    WorqueueError
        If the content is empty or spans lines, the task does not exist, data/ is
        malformed, git is unusable, the lock is not acquired, or the commit fails.
        ``StaleError`` (a subclass) if a file of ``expected`` changed.
    """
    content = _one_line("内容", content)

    def prepare() -> tuple[tuple[Task, int | None], _Change]:
        task = _with_history(_existing_task(data, task_id), now, content)
        position = _position(_shown_ids(data, read_queue(data)), task_id)
        return (task, position), _Change(lambda: [write_task(data, task)], f"log {task_id}: {content}")

    return _write_locked(data, lock_timeout, prepare, expected)


def done_task(
    data: Path,
    task_id: int,
    reason: str | None,
    now: datetime,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
    *,
    expected: tuple[FileVersion, ...] = (),
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
    expected : tuple of FileVersion
        Versions of the files the caller read, checked under the lock before
        anything is read or written.

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
        ``StaleError`` (a subclass) if a file of ``expected`` changed.
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

    return _write_locked(data, lock_timeout, prepare, expected)


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
    *,
    expected: tuple[FileVersion, ...] = (),
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
    expected : tuple of FileVersion
        Versions of the files the caller read, checked under the lock before
        anything is read or written.

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
        ``StaleError`` (a subclass) if a file of ``expected`` changed.
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

    return _write_locked(data, lock_timeout, prepare, expected)


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


@dataclass(frozen=True)
class TaskEdit:
    """What ``edit_task`` changes. Fields left at their defaults keep the task's value.

    Attributes
    ----------
    title : str or None
        New title. Surrounding whitespace is removed.
    status : str or None
        New status, one of ``OPEN_STATUSES`` (``wq done`` makes a task ``done``).
    kind : str or None
        New kind, one of ``KINDS``.
    assignee : str or None
        New assignee. Surrounding whitespace is removed.
    due : date or None
        New due date.
    clear_due : bool
        Remove the due date. Not with ``due``.
    add_depends_on : tuple of int
        IDs to add to the end of the dependencies, in order, unless already there.
    remove_depends_on : tuple of int
        IDs to take out of the dependencies. Not with ``clear_depends_on``.
    clear_depends_on : bool
        Start the dependencies from none (then ``add_depends_on`` replaces them).
    depends_on : tuple of int or None
        The whole new list of dependencies, resolved against the file read under the
        lock: IDs not in it are removed, and IDs not yet there are added (and
        checked) in order. Not with ``add_depends_on``, ``remove_depends_on``, or
        ``clear_depends_on``.
    body : str or None
        New body, replacing the Markdown before the history. Surrounding whitespace
        is removed; empty for none.
    """

    title: str | None = None
    status: str | None = None
    kind: str | None = None
    assignee: str | None = None
    due: date | None = None
    clear_due: bool = False
    add_depends_on: tuple[int, ...] = ()
    remove_depends_on: tuple[int, ...] = ()
    clear_depends_on: bool = False
    depends_on: tuple[int, ...] | None = None
    body: str | None = None


EDIT_FIELDS = ("title", "status", "kind", "assignee", "due", "depends_on", "body")


@dataclass(frozen=True)
class EditResult:
    """What ``edit_task`` did.

    Attributes
    ----------
    task : Task
        The task after the edit.
    position : int or None
        Its position, as ``show_task`` returns.
    changed : tuple of str
        Names of the changed fields in the order of ``EDIT_FIELDS``. Empty when
        nothing changed.
    description : str
        How the fields changed, as written in the history (without the reason) and
        the commit message. Empty when nothing changed.
    """

    task: Task
    position: int | None
    changed: tuple[str, ...]
    description: str
_FIELD_LABELS = {
    "title": "タイトル",
    "status": "状態",
    "kind": "種別",
    "assignee": "担当",
    "due": "期限",
    "depends_on": "依存先",
}


def edit_task(
    data: Path,
    task_id: int,
    edit: TaskEdit,
    reason: str | None,
    now: datetime,
    lock_timeout: float = LOCK_TIMEOUT_SECONDS,
    *,
    expected: tuple[FileVersion, ...] = (),
) -> EditResult:
    """Change a task's fields or body, write what changed in its history, and commit it.

    Changing nothing (every new value equals the current one) writes and commits
    nothing. Changing a ``done`` task to another status appends it to the queue
    unless ``queue.md`` already has it.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID. A ``done`` task, or one out of the queue, is accepted.
    edit : TaskEdit
        What to change.
    reason : str or None
        Why, written at the end of the history entry when something changes.
        Surrounding whitespace is removed.
    now : datetime
        Time of the history entry.
    lock_timeout : float
        Seconds to wait for the write lock.
    expected : tuple of FileVersion
        Versions of the files the caller read, checked under the lock before
        anything is read or written.

    Returns
    -------
    EditResult
        The task after the edit, its position, the changed fields, and how they
        changed.

    Raises
    ------
    WorqueueError
        If a value is invalid, a dependency to add is the task itself, does not
        exist, or makes a cycle, the task does not exist, data/ is malformed, git is
        unusable, the lock is not acquired, or the commit fails.
        ``StaleError`` (a subclass) if a file of ``expected`` changed.
    ValueError
        If ``edit`` sets both ``due`` and ``clear_due``, both ``remove_depends_on``
        and ``clear_depends_on``, or ``depends_on`` with another dependency option.
    """
    edit = replace(
        edit,
        title=_optional_one_line("タイトル", edit.title),
        assignee=_optional_one_line("担当", edit.assignee),
    )
    reason = _optional_one_line("理由", reason)
    edit = replace(edit, body=_checked_body(edit.body))
    _check_edit_options(edit)

    def prepare() -> tuple[EditResult, _Change | None]:
        task = _existing_task(data, task_id)
        resolved = _resolved_dependencies(edit, task.depends_on)
        _check_new_dependencies(data, task_id, resolved.add_depends_on)
        edited = _edited(task, resolved)
        changed = tuple(name for name in EDIT_FIELDS if _field_value(task, name) != _field_value(edited, name))
        queue = read_queue(data)
        if not changed:
            return EditResult(task, _position(_shown_ids(data, queue, task), task_id), (), ""), None
        description = "、".join(_describe_change(name, task, edited) for name in changed)
        edited = _with_history(edited, now, description if reason is None else f"{description}: {reason}")
        reopened = task.status == "done" and edited.status != "done" and task_id not in queue
        new_queue = [*queue, task_id] if reopened else queue
        position = _position(_shown_ids(data, new_queue, edited), task_id)

        def write() -> list[Path]:
            written = [write_task(data, edited)]
            if reopened:
                written.append(write_queue(data, new_queue))
            return written

        result = EditResult(edited, position, changed, description)
        return result, _Change(write, f"edit {task_id}: {description}")

    return _write_locked(data, lock_timeout, prepare, expected)


def _checked_body(body: str | None) -> str | None:
    """Return ``body`` with LF line ends and stripped, or raise if it has a history heading line.

    CRLF and CR become LF first: files are written with LF and read with universal
    newlines, so a heading ending with CR would otherwise pass here and split the
    body when the file is read again.
    """
    if body is None:
        return None
    stripped = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    if HISTORY_HEADING in stripped.split("\n"):
        raise WorqueueError(f"本文に「{HISTORY_HEADING}」の行は入れられません")
    return stripped


def _check_edit_options(edit: TaskEdit) -> None:
    """Raise if ``edit`` has an invalid status or kind, or contradicting options."""
    if edit.due is not None and edit.clear_due:
        raise ValueError("TaskEdit cannot set both due and clear_due")
    if edit.remove_depends_on and edit.clear_depends_on:
        raise ValueError("TaskEdit cannot set both remove_depends_on and clear_depends_on")
    if edit.depends_on is not None and (edit.add_depends_on or edit.remove_depends_on or edit.clear_depends_on):
        raise ValueError("TaskEdit cannot set depends_on with another dependency option")
    if edit.status is not None and edit.status not in OPEN_STATUSES:
        raise WorqueueError(f"状態は {', '.join(OPEN_STATUSES)} のどれかにしてください: {edit.status}")
    if edit.kind is not None and edit.kind not in KINDS:
        raise WorqueueError(f"種別は {', '.join(KINDS)} のどれかにしてください: {edit.kind}")
    for dependency in edit.add_depends_on:
        if dependency in edit.remove_depends_on:
            raise WorqueueError(f"タスク {dependency} を依存先に足しつつ外すことはできません")


def _check_new_dependencies(data: Path, task_id: int, dependencies: tuple[int, ...]) -> None:
    """Raise if a dependency to add is the task itself, does not exist, or leads back to the task."""
    for dependency in dependencies:
        if dependency == task_id:
            raise WorqueueError(f"タスク {task_id} は自分自身に依存できません")
        if not task_path(data, dependency).is_file():
            raise WorqueueError(f"タスク {dependency} がありません")
        path = _dependency_path(data, dependency, task_id, set())
        if path is not None:
            raise WorqueueError(f"依存が循環します: {' → '.join(str(i) for i in [task_id, *path])}")


def _dependency_path(data: Path, start: int, goal: int, seen: set[int]) -> list[int] | None:
    """Return the IDs from ``start`` to ``goal`` following ``depends_on`` depth first, or None.

    A task without a file is a dead end. ``seen`` holds the tasks already followed.
    """
    if start == goal:
        return [start]
    if start in seen or not task_path(data, start).is_file():
        return None
    seen.add(start)
    for dependency in read_task(data, start).depends_on:
        rest = _dependency_path(data, dependency, goal, seen)
        if rest is not None:
            return [start, *rest]
    return None


def _edited(task: Task, edit: TaskEdit) -> Task:
    """Return ``task`` with the values of ``edit``, before the history entry."""
    markdown = task.markdown
    if edit.body is not None and edit.body != body_of(markdown):
        markdown = replace_body(markdown, edit.body)
    return replace(
        task,
        title=task.title if edit.title is None else edit.title,
        status=task.status if edit.status is None else edit.status,
        kind=task.kind if edit.kind is None else edit.kind,
        assignee=task.assignee if edit.assignee is None else edit.assignee,
        due=None if edit.clear_due else task.due if edit.due is None else edit.due,
        depends_on=_edited_dependencies(task.depends_on, edit),
        markdown=markdown,
    )


def _resolved_dependencies(edit: TaskEdit, current: tuple[int, ...]) -> TaskEdit:
    """Return ``edit`` with ``depends_on`` turned into the IDs to remove from and add to ``current``."""
    if edit.depends_on is None:
        return edit
    return replace(
        edit,
        depends_on=None,
        add_depends_on=tuple(i for i in edit.depends_on if i not in current),
        remove_depends_on=tuple(i for i in current if i not in edit.depends_on),
    )


def _edited_dependencies(depends_on: tuple[int, ...], edit: TaskEdit) -> tuple[int, ...]:
    """Return the dependencies after ``edit``: clear, remove, then add the missing ones in order."""
    if not (edit.clear_depends_on or edit.remove_depends_on or edit.add_depends_on):
        return depends_on
    kept = () if edit.clear_depends_on else tuple(i for i in depends_on if i not in edit.remove_depends_on)
    return kept + tuple(dict.fromkeys(i for i in edit.add_depends_on if i not in kept))


def _field_value(task: Task, name: str) -> object:
    """Return the value of one of ``EDIT_FIELDS``; the body is the Markdown."""
    return task.markdown if name == "body" else getattr(task, name)


def _describe_change(name: str, before: Task, after: Task) -> str:
    """Return how one field changed, as written in the history and the commit message."""
    if name == "body":
        return "本文を変更"
    return f"{_FIELD_LABELS[name]} {_field_text(getattr(before, name))} → {_field_text(getattr(after, name))}"


def _field_text(value: object) -> str:
    """Return a field's value as text: ``なし`` for none, IDs joined by ``, ``."""
    if value is None or value == ():
        return "なし"
    if isinstance(value, tuple):
        return ", ".join(str(v) for v in value)
    return str(value)


def _optional_one_line(label: str, value: str | None) -> str | None:
    """Return None for None, else ``value`` checked as ``_one_line`` does."""
    return None if value is None else _one_line(label, value)


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


def _shown_ids(data: Path, queue: list[int], replacing: Task | None = None) -> list[int]:
    """Return the IDs of the tasks of ``queue`` that are not ``done``, as ``_shown_tasks`` reads them."""
    return [task.id for task in _shown_tasks(data, queue, replacing)]


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


def _write_locked[T](
    data: Path,
    lock_timeout: float,
    prepare: Callable[[], tuple[T, _Change | None]],
    expected: tuple[FileVersion, ...] = (),
) -> T:
    """Run one write operation: check git, lock, check the versions, prepare, write, and commit.

    ``expected`` is checked first under the lock, raising ``StaleError`` before
    anything is written. ``prepare`` runs under the lock after it. It reads the files
    again and checks the input, raising before anything is written, and returns the
    operation's result with the change to make, or ``None`` to write and commit nothing.
    """
    check_git(data)
    data.mkdir(parents=True, exist_ok=True)
    with write_lock(data, lock_timeout):
        check_versions(data, expected)
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


def _shown_tasks(data: Path, queue: list[int], replacing: Task | None = None) -> list[Task]:
    """Read the tasks of ``queue`` and keep those that are not ``done``.

    ``replacing``, when given, is used in place of the file of the task with its ID
    (a task about to be written).
    """
    tasks = [
        replacing if replacing is not None and task_id == replacing.id else read_task(data, task_id)
        for task_id in queue
    ]
    return [task for task in tasks if task.status != "done"]
