"""``wq show``: show one task's fields, body, and history."""

import argparse

from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import show_task
from worqueue.store.paths import data_dir
from worqueue.store.task import Task

LABEL_WIDTH = len("DEPENDS_ON: ")


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq show`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser(
        "show", help="1 件の項目・本文・履歴を表示する", description="1 件の項目・本文・履歴を表示する"
    )
    parser.add_argument("id", type=int, metavar="<ID>", help="タスクの ID")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq show``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    task, position = show_task(data_dir(), args.id)
    markdown = task.markdown.strip("\n")
    if args.json:
        print_json({"task": {**task.summary(position), "markdown": markdown}})
        return
    print(render_fields(task, position))
    if markdown:
        print()
        print(markdown)


def render_fields(task: Task, position: int | None) -> str:
    """Return the lines of a task's fields, each ``<NAME>:`` padded to one width.

    Parameters
    ----------
    task : Task
        The task.
    position : int or None
        Its position, or None for none.

    Returns
    -------
    str
        The lines, without a trailing newline.
    """
    fields = [
        ("ID", str(task.id)),
        ("TITLE", task.title),
        ("STATUS", task.status),
        ("KIND", task.kind),
        ("ASSIGNEE", task.assignee),
        ("DUE", task.due.isoformat() if task.due else "-"),
        ("DEPENDS_ON", ", ".join(map(str, task.depends_on)) or "-"),
        ("CREATED", task.created),
        ("POSITION", "-" if position is None else str(position)),
    ]
    return "\n".join(f"{name + ':':<{LABEL_WIDTH}}{value}" for name, value in fields)
