"""``wq add``: create a task at the end of the queue."""

import argparse
import re
from datetime import date

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import NewTask, add_task
from worqueue.store.paths import data_dir
from worqueue.store.task import KINDS

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CREATABLE_STATUSES = ("todo", "doing", "waiting")


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq add`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser("add", help="タスクを作り、キューの末尾に入れる", description="タスクを作り、キューの末尾に入れる")
    parser.add_argument("title", metavar="<タイトル>", help="1 行のタイトル")
    parser.add_argument("--kind", required=True, choices=KINDS, help="manage（管理）か implement（実装）")
    parser.add_argument("--assignee", default="me", metavar="<名前>", help="担当。既定は me（自分）")
    parser.add_argument("--due", type=_parse_date, metavar="<YYYY-MM-DD>", help="期限")
    parser.add_argument(
        "--depends-on", type=int, action="append", default=[], metavar="<ID>", help="依存先のタスクの ID（繰り返し可）"
    )
    parser.add_argument("--status", default="todo", choices=CREATABLE_STATUSES, help="状態。既定は todo")
    parser.add_argument("--body", default="", metavar="<本文>", help="本文")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq add``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    new = NewTask(
        title=args.title,
        kind=args.kind,
        assignee=args.assignee,
        due=args.due,
        depends_on=tuple(args.depends_on),
        status=args.status,
        body=args.body,
    )
    task, position = add_task(data_dir(), new, now=clock.now())
    if args.json:
        print_json({"task": task.summary(position)})
    else:
        print(f"追加しました: {task.id} {task.title}（キューの {position} 番目）")


def _parse_date(text: str) -> date:
    """Parse ``--due``: a valid date in the ``YYYY-MM-DD`` form."""
    try:
        if _DATE.match(text):
            return date.fromisoformat(text)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(f"YYYY-MM-DD の形の日付にしてください: {text}")
