"""The current time for the CLI, in one place so that tests can fix it."""

from datetime import datetime


def now() -> datetime:
    """Return the current time in the local time zone.

    Returns
    -------
    datetime
        ``datetime.now().astimezone()``.
    """
    return datetime.now().astimezone()
