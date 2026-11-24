"""The ``wq`` command: building the parser, reporting errors, and exit codes."""

import argparse
import sys

from worqueue.cli import add, listing
from worqueue.cli.output import print_error
from worqueue.store.errors import WorqueueError

EXIT_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of ``wq`` with every subcommand.

    Returns
    -------
    argparse.ArgumentParser
        Each subcommand sets ``run`` to the function that carries it out.
    """
    parser = argparse.ArgumentParser(prog="wq", description="Worqueue: 自分の仕事とチームに振った仕事の優先順位を並べる")
    subparsers = parser.add_subparsers(title="コマンド", metavar="<command>")
    add.register(subparsers)
    listing.register(subparsers)
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run ``wq`` with ``argv`` and return the exit code.

    Parameters
    ----------
    argv : list of str, optional
        Arguments after ``wq``; ``sys.argv[1:]`` when omitted.

    Returns
    -------
    int
        0 on success, 1 on an error from the data or the environment, 2 when no
        subcommand is given. Argument errors exit with 2 through argparse.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "run"):
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        args.run(args)
    except WorqueueError as e:
        print_error(str(e), as_json=args.json)
        return EXIT_ERROR
    return 0


def main() -> None:
    """Entry point of ``wq``: make the output UTF-8, run, and exit with the code."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.exit(run())
