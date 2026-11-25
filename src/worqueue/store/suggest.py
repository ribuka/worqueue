"""Judging which tasks of the queue should perhaps move up. Reads and writes no files."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from typing import ClassVar

from worqueue.store.config import SuggestConfig
from worqueue.store.task import MY_ASSIGNEE, Task, history_dates


@dataclass(frozen=True)
class DueSoon:
    """The due date is near or past, but the task is not near the top.

    Attributes
    ----------
    days_left : int
        Days from today to the due date. 0 for today, negative when past.
    """

    kind: ClassVar[str] = "due_soon"
    days_left: int

    def summary(self) -> dict[str, object]:
        """Return the reason's JSON object.

        Returns
        -------
        dict
            ``kind`` and ``days_left``.
        """
        return {"kind": self.kind, "days_left": self.days_left}


@dataclass(frozen=True)
class Unblocked:
    """Every task this task waited for is ``done``."""

    kind: ClassVar[str] = "unblocked"

    def summary(self) -> dict[str, object]:
        """Return the reason's JSON object.

        Returns
        -------
        dict
            ``kind`` only.
        """
        return {"kind": self.kind}


@dataclass(frozen=True)
class Stale:
    """A task handed to a member has had no history entry for a while.

    Attributes
    ----------
    days : int
        Days from ``since`` to today.
    since : date
        Date of the latest history entry, or of the task's creation without one.
    """

    kind: ClassVar[str] = "stale"
    days: int
    since: date

    def summary(self) -> dict[str, object]:
        """Return the reason's JSON object.

        Returns
        -------
        dict
            ``kind``, ``days``, and ``since``.
        """
        return {"kind": self.kind, "days": self.days, "since": self.since.isoformat()}


@dataclass(frozen=True)
class Blocking:
    """Tasks above this one wait for it.

    Attributes
    ----------
    blocked_ids : tuple of int
        IDs of the tasks above that depend on this one, in queue order.
    """

    kind: ClassVar[str] = "blocking"
    blocked_ids: tuple[int, ...]

    def summary(self) -> dict[str, object]:
        """Return the reason's JSON object.

        Returns
        -------
        dict
            ``kind`` and ``blocked_ids``.
        """
        return {"kind": self.kind, "blocked_ids": list(self.blocked_ids)}


Reason = DueSoon | Unblocked | Stale | Blocking


@dataclass(frozen=True)
class Suggestion:
    """A task with the reasons to look at its place in the queue.

    Attributes
    ----------
    task : Task
        The task.
    position : int
        Its 1-based position in the queue.
    reasons : tuple of Reason
        At least one, in the order ``due_soon``, ``unblocked``, ``stale``, ``blocking``.
    """

    task: Task
    position: int
    reasons: tuple[Reason, ...]


def judge_queue(
    queue: list[Task], done_ids: Collection[int], config: SuggestConfig, today: date
) -> list[Suggestion]:
    """Return the suggestions for the tasks of the queue.

    Parameters
    ----------
    queue : list of Task
        The tasks of the queue from the top, without ``done`` ones.
    done_ids : collection of int
        IDs of the ``done`` tasks among the dependencies of ``queue``.
    config : SuggestConfig
        The thresholds.
    today : date
        Today in local time.

    Returns
    -------
    list of Suggestion
        One per task with at least one reason, in queue order.
    """
    suggestions: list[Suggestion] = []
    for position, task in enumerate(queue, start=1):
        candidates = (
            _due_soon(task, position, config, today),
            _unblocked(task, done_ids),
            _stale(task, config, today),
            _blocking(task, queue[: position - 1]),
        )
        reasons = tuple(reason for reason in candidates if reason is not None)
        if reasons:
            suggestions.append(Suggestion(task, position, reasons))
    return suggestions


def _due_soon(task: Task, position: int, config: SuggestConfig, today: date) -> DueSoon | None:
    """Judge a task due within ``due_within_days`` days (or past) and below the top ``top_n``."""
    if task.due is None or position <= config.top_n:
        return None
    days_left = (task.due - today).days
    return DueSoon(days_left) if days_left <= config.due_within_days else None


def _unblocked(task: Task, done_ids: Collection[int]) -> Unblocked | None:
    """Judge a task whose dependencies are all ``done`` and that I am not already doing."""
    if not task.depends_on or (task.assignee == MY_ASSIGNEE and task.status == "doing"):
        return None
    return Unblocked() if all(i in done_ids for i in task.depends_on) else None


def _stale(task: Task, config: SuggestConfig, today: date) -> Stale | None:
    """Judge a member's task without a history entry for ``stale_days`` days."""
    if task.assignee == MY_ASSIGNEE:
        return None
    since = max(history_dates(task.markdown), default=None)
    if since is None:
        since = datetime.fromisoformat(task.created).astimezone().date()
    days = (today - since).days
    return Stale(days, since) if days >= config.stale_days else None


def _blocking(task: Task, above: list[Task]) -> Blocking | None:
    """Judge a task that tasks above it depend on."""
    blocked_ids = tuple(other.id for other in above if task.id in other.depends_on)
    return Blocking(blocked_ids) if blocked_ids else None
