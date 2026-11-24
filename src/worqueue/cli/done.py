"""``wq done``: mark a task ``done`` and take it out of the queue."""

import argparse

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import done_task
from worqueue.store.paths import data_dir


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq done`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser("done", help="done にしてキューから外す", description="done にしてキューから外す")
    parser.add_argument("id", type=int, metavar="<ID>", help="タスクの ID")
    parser.add_argument("--reason", metavar="<理由>", help="履歴に書く理由（やめたタスクなら、やめた理由）")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq done``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    task = done_task(data_dir(), args.id, args.reason, now=clock.now())
    if args.json:
        print_json({"task": task.summary(None)})
    else:
        print(f"完了にしました: {task.id} {task.title}")
