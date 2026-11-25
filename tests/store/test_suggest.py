"""Tests of the judging of the reorder suggestions and of the history dates it uses."""

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from worqueue.store.config import SuggestConfig
from worqueue.store.suggest import (
    Blocking,
    DueSoon,
    Reason,
    Stale,
    Unblocked,
    judge_queue,
)
from worqueue.store.task import Task, history_dates

TODAY = date(2026, 11, 26)
CONFIG = SuggestConfig(due_within_days=3, top_n=2, stale_days=7)
CREATED = datetime(2026, 11, 1, 9, 0).astimezone().isoformat()


def task(task_id: int, **fields: object) -> Task:
    """Return a task of mine that no condition matches unless ``fields`` say so."""
    base = Task(
        id=task_id,
        title=f"タスク {task_id}",
        status="todo",
        kind="implement",
        assignee="me",
        due=None,
        depends_on=(),
        created=CREATED,
        markdown="\n",
    )
    return replace(base, **fields)


def history(*lines: str) -> str:
    """Return Markdown with a history of ``lines``."""
    return "\n## 履歴\n\n" + "".join(f"{line}\n" for line in lines)


def entry(days_ago: int) -> str:
    """Return a history line written ``days_ago`` days before ``TODAY``."""
    return f"- {TODAY - timedelta(days=days_ago)} 09:00 連絡した"


def reasons_of(queue: list[Task], task_id: int, done_ids: tuple[int, ...] = ()) -> tuple[Reason, ...]:
    """Return the reasons ``judge_queue`` gives the task ``task_id``, or none."""
    suggestions = judge_queue(queue, done_ids, CONFIG, TODAY)
    return next((s.reasons for s in suggestions if s.task.id == task_id), ())


def below_the_top(target: Task) -> list[Task]:
    """Return a queue with ``target`` just below the top ``CONFIG.top_n``."""
    return [task(101), task(102), target]


@pytest.mark.parametrize("days_left", [3, 1, 0, -1, -30])
def test_a_task_due_soon_below_the_top_is_suggested(days_left: int) -> None:
    """A task due within ``due_within_days`` days, today, or in the past, below the top, is due soon."""
    target = task(1, due=TODAY + timedelta(days=days_left))

    assert reasons_of(below_the_top(target), 1) == (DueSoon(days_left),)


@pytest.mark.parametrize("due", [TODAY + timedelta(days=4), None])
def test_a_task_not_due_soon_is_not_suggested(due: date | None) -> None:
    """A task due later than ``due_within_days`` days, or without a due date, is not due soon."""
    assert reasons_of(below_the_top(task(1, due=due)), 1) == ()


def test_a_task_in_the_top_is_not_due_soon() -> None:
    """The task at position ``top_n`` is not due soon; the one at ``top_n + 1`` is."""
    queue = [task(1), task(2, due=TODAY), task(3, due=TODAY)]

    assert reasons_of(queue, 2) == ()
    assert reasons_of(queue, 3) == (DueSoon(0),)


@pytest.mark.parametrize(
    ("assignee", "status"),
    [("me", "todo"), ("me", "waiting"), ("佐藤", "doing"), ("佐藤", "waiting")],
)
def test_a_task_whose_dependencies_are_all_done_is_unblocked(assignee: str, status: str) -> None:
    """A task whose dependencies are all ``done`` is unblocked, unless I am doing it."""
    target = task(1, assignee=assignee, status=status, depends_on=(8, 9), markdown=history(entry(0)))

    assert reasons_of([target], 1, (8, 9)) == (Unblocked(),)


def test_a_task_i_am_doing_is_not_unblocked() -> None:
    """A task of mine that is ``doing`` is not unblocked."""
    assert reasons_of([task(1, status="doing", depends_on=(8,))], 1, (8,)) == ()


@pytest.mark.parametrize("depends_on", [(), (8, 9)], ids=["no-dependencies", "one-not-done"])
def test_a_task_without_all_dependencies_done_is_not_unblocked(depends_on: tuple[int, ...]) -> None:
    """A task without dependencies, or with one that is not ``done``, is not unblocked."""
    assert reasons_of([task(1, depends_on=depends_on)], 1, (8,)) == ()


@pytest.mark.parametrize("status", ["todo", "doing", "waiting"])
def test_a_members_task_without_an_entry_for_stale_days_is_stale(status: str) -> None:
    """A member's task whose latest entry is ``stale_days`` days old is stale."""
    target = task(1, assignee="佐藤", status=status, markdown=history(entry(7)))

    assert reasons_of([target], 1) == (Stale(7, TODAY - timedelta(days=7)),)


@pytest.mark.parametrize(("assignee", "days_ago"), [("佐藤", 6), ("佐藤", -1), ("me", 30)])
def test_a_recent_or_own_task_is_not_stale(assignee: str, days_ago: int) -> None:
    """A task with a newer entry, or one of mine, is not stale."""
    assert reasons_of([task(1, assignee=assignee, markdown=history(entry(days_ago)))], 1) == ()


def test_staleness_counts_from_the_latest_entry_in_any_order() -> None:
    """The latest date counts, wherever its line is."""
    target = task(1, assignee="佐藤", markdown=history(entry(20), entry(8), entry(15)))

    assert reasons_of([target], 1) == (Stale(8, TODAY - timedelta(days=8)),)


@pytest.mark.parametrize(
    "markdown",
    ["\n", "\n- 2026-11-26 本文の日付\n", history("- 電話した")],
    ids=["no-history", "date-in-body", "no-dated-line"],
)
def test_staleness_counts_from_creation_without_a_dated_entry(markdown: str) -> None:
    """Without a dated history line, the local date of creation counts."""
    target = task(1, assignee="佐藤", markdown=markdown)

    assert reasons_of([target], 1) == (Stale(25, date(2026, 11, 1)),)


@pytest.mark.parametrize(("days_ago", "stale"), [(7, True), (6, False)])
def test_staleness_from_creation_uses_the_same_threshold(days_ago: int, stale: bool) -> None:
    """A task without history is stale from ``stale_days`` days after its creation."""
    created = datetime(2026, 11, 26, 23, 59).astimezone() - timedelta(days=days_ago)
    target = task(1, assignee="佐藤", created=created.isoformat())

    assert bool(reasons_of([target], 1)) is stale


def test_history_dates_reads_only_dated_lines_after_the_heading() -> None:
    """Only existing dates at the start of top-level history lines are read."""
    markdown = "- 2026-01-01 本文\n" + history(
        "- 2026-11-20 09:00 依頼した",
        "- 2026-11-21 時刻なし",
        "- 2026-11-22",
        "- 2026-11-23　全角の空白",
        "- 2026-11-31 無い日付",
        "- 2026-11-24に電話",
        "  - 2026-11-25 字下げ",
        "* 2026-11-25 別の記号",
        "2026-11-25 記号なし",
        "",
        "## メモ",
        "- 2026-11-19 後の見出しの下",
    )

    assert history_dates(markdown) == [date(2026, 11, day) for day in (20, 21, 22, 23, 19)]


def test_a_task_that_tasks_above_wait_for_is_blocking() -> None:
    """The IDs of the waiting tasks above come in queue order; those below do not count."""
    queue = [task(5, depends_on=(1,)), task(3, depends_on=(1,)), task(1), task(4, depends_on=(1,))]

    assert reasons_of(queue, 1) == (Blocking((5, 3)),)


def test_a_task_only_tasks_below_wait_for_is_not_blocking() -> None:
    """A task is not blocking when only tasks below it wait for it."""
    assert reasons_of([task(1), task(2, depends_on=(1,))], 1) == ()


def test_a_task_depending_on_itself_is_not_blocking() -> None:
    """A task that lists itself as a dependency does not wait above itself."""
    assert reasons_of([task(1, depends_on=(1,))], 1) == ()


def test_every_reason_of_a_task_comes_in_order_and_tasks_in_queue_order() -> None:
    """All matching reasons are given in the documented order, and tasks in queue order."""
    target = task(1, assignee="佐藤", due=TODAY, depends_on=(8,), markdown=history(entry(9)))
    queue = [task(2, depends_on=(1,)), task(3, depends_on=(8,)), target]

    suggestions = judge_queue(queue, (8,), CONFIG, TODAY)

    assert [(s.task.id, s.position) for s in suggestions] == [(3, 2), (1, 3)]
    assert suggestions[1].reasons == (
        DueSoon(0),
        Unblocked(),
        Stale(9, TODAY - timedelta(days=9)),
        Blocking((2,)),
    )
