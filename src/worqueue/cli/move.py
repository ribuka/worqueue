"""``wq move``: change a task's position in the queue."""

import argparse

from worqueue.cli import clock
from worqueue.cli.output import add_json_option, print_json
from worqueue.store.ops import MoveTarget, move_task
from worqueue.store.paths import data_dir


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add ``wq move`` to the subcommands.

    Parameters
    ----------
    subparsers : argparse._SubParsersAction
        The subcommands of ``wq``.
    """
    parser = subparsers.add_parser(
        "move", help="キューの中の位置を変える。理由を渡すと履歴に書く", description="キューの中の位置を変える。理由を渡すと履歴に書く"
    )
    parser.add_argument("id", type=int, metavar="<ID>", help="タスクの ID")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--to", type=int, metavar="<N>", help="位置 N（wq list の #）へ")
    target.add_argument("--top", action="store_true", help="先頭へ")
    target.add_argument("--bottom", action="store_true", help="末尾へ")
    target.add_argument("--before", type=int, metavar="<ID2>", help="タスク ID2 の直前へ")
    target.add_argument("--after", type=int, metavar="<ID2>", help="タスク ID2 の直後へ")
    parser.add_argument("--reason", metavar="<理由>", help="履歴に書く理由")
    add_json_option(parser)
    parser.set_defaults(run=run)


def run(args: argparse.Namespace) -> None:
    """Carry out ``wq move``.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.
    """
    task, start, end = move_task(data_dir(), args.id, _target(args), args.reason, now=clock.now())
    if args.json:
        print_json({"task": task.summary(end), "from": start})
    elif start == end:
        print(f"動かしませんでした: {task.id} {task.title}（{start} 番目のまま）")
    else:
        print(f"動かしました: {task.id} {task.title}（{start} → {end} 番目）")


def _target(args: argparse.Namespace) -> MoveTarget:
    """Return the destination given by the one option of the group."""
    if args.top:
        return MoveTarget("top")
    if args.bottom:
        return MoveTarget("bottom")
    if args.to is not None:
        return MoveTarget("to", args.to)
    if args.before is not None:
        return MoveTarget("before", args.before)
    return MoveTarget("after", args.after)
