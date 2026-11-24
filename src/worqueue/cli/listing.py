"""``wq list``: show the queue from the top."""

import argparse

from worqueue.cli.output import add_json_option, print_json
from worqueue.cli.table import render_table
from worqueue.store.ops import list_queue
from worqueue.store.paths import data_dir

HEADER = ["#", "ID", "STATUS", "KIND", "ASSIGNEE", "DUE", "TITLE"]
EMPTY_MESSAGE = "キューは空です"


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq list`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser("list", help="キューを上から表示する", description="キューを上から表示する")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq list``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    tasks = list_queue(data_dir())
    if args.json:
        print_json({"tasks": [task.summary(i) for i, task in enumerate(tasks, start=1)]})
    elif not tasks:
        print(EMPTY_MESSAGE)
    else:
        rows = [
            [str(i), str(t.id), t.status, t.kind, t.assignee, t.due.isoformat() if t.due else "-", t.title]
            for i, t in enumerate(tasks, start=1)
        ]
        print(render_table(HEADER, rows))
