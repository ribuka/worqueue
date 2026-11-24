"""``wq edit``: change a task's fields or body."""

import argparse

from worqueue.cli import clock
from worqueue.cli.args import parse_date
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import TaskEdit, edit_task
from worqueue.store.paths import data_dir
from worqueue.store.task import KINDS, OPEN_STATUSES

# Options that change something; ``wq edit`` needs at least one of them.
_EDIT_OPTIONS = (
    "title",
    "status",
    "kind",
    "assignee",
    "due",
    "no_due",
    "add_depends_on",
    "remove_depends_on",
    "clear_depends_on",
    "body",
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq edit`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser("edit", help="項目を変える", description="タスクの項目や本文を変える")
    parser.add_argument("id", type=int, metavar="<ID>", help="タスクの ID")
    parser.add_argument("--title", metavar="<タイトル>", help="タイトル")
    parser.add_argument("--status", choices=OPEN_STATUSES, help="状態（done にするのは wq done）")
    parser.add_argument("--kind", choices=KINDS, help="manage（管理）か implement（実装）")
    parser.add_argument("--assignee", metavar="<名前>", help="担当")
    due = parser.add_mutually_exclusive_group()
    due.add_argument("--due", type=parse_date, metavar="<YYYY-MM-DD>", help="期限")
    due.add_argument("--no-due", action="store_true", help="期限を消す")
    parser.add_argument(
        "--add-depends-on", type=int, action="append", default=[], metavar="<ID>", help="依存先に足す（繰り返し可）"
    )
    removal = parser.add_mutually_exclusive_group()
    removal.add_argument(
        "--remove-depends-on", type=int, action="append", default=[], metavar="<ID>", help="依存先から外す（繰り返し可）"
    )
    removal.add_argument("--clear-depends-on", action="store_true", help="依存先を空にする（--add-depends-on と一緒なら置き換え）")
    parser.add_argument("--body", metavar="<本文>", help="本文を置き換える（履歴は残す）")
    parser.add_argument("--reason", metavar="<理由>", help="変えたときに履歴に書く理由")
    add_json_option(parser)
    parser.set_defaults(run=lambda args: run(parser, args))


def run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Carry out ``wq edit``.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser of ``wq edit``, to report a call that changes nothing.
    args : argparse.Namespace
        Parsed arguments.
    """
    if not any(getattr(args, name) not in (None, False, []) for name in _EDIT_OPTIONS):
        parser.error("変える項目を 1 つ以上指定してください")
    edit = TaskEdit(
        title=args.title,
        status=args.status,
        kind=args.kind,
        assignee=args.assignee,
        due=args.due,
        clear_due=args.no_due,
        add_depends_on=tuple(args.add_depends_on),
        remove_depends_on=tuple(args.remove_depends_on),
        clear_depends_on=args.clear_depends_on,
        body=args.body,
    )
    result = edit_task(data_dir(), args.id, edit, args.reason, now=clock.now())
    task = result.task
    if args.json:
        print_json({"task": task.summary(result.position), "changed": list(result.changed)})
    elif result.changed:
        print(f"変えました: {task.id} {task.title}（{result.description}）")
    else:
        print(f"変えませんでした: {task.id} {task.title}（どの項目も今と同じ）")
