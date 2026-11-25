"""Argument types shared by the subcommands of ``wq``."""

import argparse
import re
from datetime import date

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(text: str) -> date:
    """Parse a date argument such as ``--due``: a valid date in the ``YYYY-MM-DD`` form.

    Parameters
    ----------
    text : str
        The argument.

    Returns
    -------
    date
        The date.

    Raises
    ------
    argparse.ArgumentTypeError
        If ``text`` is not a valid date in the ``YYYY-MM-DD`` form.
    """
    try:
        if _DATE.match(text):
            return date.fromisoformat(text)
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(f"YYYY-MM-DD の形の日付にしてください: {text}")
