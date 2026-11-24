"""The ``--json`` option and how subcommands print JSON and errors."""

import argparse
import json
import sys


def add_json_option(parser: argparse.ArgumentParser) -> None:
    """Add ``--json`` to a subcommand's parser.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The subcommand's parser.
    """
    parser.add_argument("--json", action="store_true", help="JSON で出力する")


def print_json(value: object) -> None:
    """Print ``value`` to stdout as indented JSON with non-ASCII characters as they are.

    Parameters
    ----------
    value : object
        A JSON-serializable value.
    """
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_error(message: str, as_json: bool) -> None:
    """Print an error message to stderr.

    Parameters
    ----------
    message : str
        The message.
    as_json : bool
        Print ``{"error": <message>}`` instead of the bare message.
    """
    text = json.dumps({"error": message}, ensure_ascii=False) if as_json else message
    print(text, file=sys.stderr)
