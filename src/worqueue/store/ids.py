"""Allocating task IDs (``next_id``) so that an ID is never reused."""

from pathlib import Path

from worqueue.store.atomic import write_text_atomic
from worqueue.store.errors import WorqueueError
from worqueue.store.task import task_ids

NEXT_ID_FILE = "next_id"


def next_id(data: Path) -> int:
    """Return the ID for the next task.

    Parameters
    ----------
    data : Path
        The data/ directory.

    Returns
    -------
    int
        The larger of the value in ``next_id`` and the largest ID in ``tasks/`` plus one;
        1 when neither exists.

    Raises
    ------
    WorqueueError
        If ``next_id`` does not hold a positive integer.
    """
    after_tasks = max(task_ids(data), default=0) + 1
    path = data / NEXT_ID_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return after_tasks
    except UnicodeDecodeError:
        raise WorqueueError(f"{NEXT_ID_FILE}: UTF-8 として読めません") from None
    value = text.strip()
    if not value.isdigit() or int(value) < 1:
        raise WorqueueError(f"{NEXT_ID_FILE} が 1 以上の整数ではありません: {value!r}")
    return max(after_tasks, int(value))


def write_next_id(data: Path, value: int) -> Path:
    """Write the ID for the next task.

    Parameters
    ----------
    data : Path
        The data/ directory.
    value : int
        The next ID.

    Returns
    -------
    Path
        The file written.
    """
    path = data / NEXT_ID_FILE
    write_text_atomic(path, f"{value}\n")
    return path
