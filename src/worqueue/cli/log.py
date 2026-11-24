"""``wq log``: add one entry to a task's history."""

import argparse

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import log_task
from worqueue.store.paths import data_dir


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq log`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser("log", help="履歴に追記する", description="履歴に追記する")
    parser.add_argument("id", type=int, metavar="<ID>", help="タスクの ID")
    parser.add_argument("content", metavar="<内容>", help="履歴に書く 1 行")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq log``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    task, position = log_task(data_dir(), args.id, args.content, now=clock.now())
    if args.json:
        print_json({"task": task.summary(position)})
    else:
        print(f"履歴に書きました: {task.id} {task.title}")
