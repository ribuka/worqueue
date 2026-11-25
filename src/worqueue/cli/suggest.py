"""``wq suggest``: show the tasks that should perhaps move up the queue."""

import argparse
from datetime import date
from typing import assert_never

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.cli.table import render_table
from worqueue.store.ops import suggest_queue
from worqueue.store.paths import data_dir
from worqueue.store.suggest import (
    Blocking,
    DueSoon,
    Reason,
    Stale,
    Suggestion,
    Unblocked,
)

HEADER = ["#", "ID", "ASSIGNEE", "REASON", "TITLE"]
EMPTY_MESSAGE = "指摘はありません"


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq suggest`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser(
        "suggest", help="並べ替えの指摘を表示する", description="並べ替えの指摘を表示する（キューは変えない）"
    )
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq suggest``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    suggestions = suggest_queue(data_dir(), clock.now())
    if args.json:
        print_json({"suggestions": [_summary(suggestion) for suggestion in suggestions]})
    elif not suggestions:
        print(EMPTY_MESSAGE)
    else:
        rows = [
            [str(s.position), str(s.task.id), s.task.assignee, reason_text(reason, s.task.due), s.task.title]
            for s in suggestions
            for reason in s.reasons
        ]
        print(render_table(HEADER, rows))


def reason_text(reason: Reason, due: date | None) -> str:
    """Return one reason as text for people.

    Parameters
    ----------
    reason : Reason
        The reason.
    due : date or None
        The task's due date, shown for a ``DueSoon`` reason.

    Returns
    -------
    str
        The text of the ``REASON`` column.
    """
    match reason:
        case DueSoon(days_left=days_left):
            if days_left > 0:
                return f"期限まで {days_left} 日（{due}）"
            if days_left == 0:
                return f"期限は今日（{due}）"
            return f"期限を {-days_left} 日過ぎた（{due}）"
        case Unblocked():
            return "着手できる（依存先がすべて done）"
        case Stale(days=days, since=since):
            return f"追記が {days} 日ない（{since} から）"
        case Blocking(blocked_ids=blocked_ids):
            return f"上の {', '.join(map(str, blocked_ids))} が待っている"
        case _:
            assert_never(reason)


def _summary(suggestion: Suggestion) -> dict[str, object]:
    """Return the JSON object of one suggestion: the task and its reasons."""
    return {
        "task": suggestion.task.summary(suggestion.position),
        "reasons": [reason.summary() for reason in suggestion.reasons],
    }
