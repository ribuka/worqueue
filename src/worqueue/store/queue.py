"""Reading and writing the queue order (``queue.md``)."""

import re
from pathlib import Path

from worqueue.store.atomic import write_text_atomic
from worqueue.store.errors import WorqueueError

QUEUE_FILE = "queue.md"
HEADING = "# Queue"
_ENTRY = re.compile(r"^- (\d+)\s*$")


def read_queue(data: Path) -> list[int]:
    """Read the queue.

    Parameters
    ----------
    data : Path
        The data/ directory.

    Returns
    -------
    list of int
        Task IDs from the top of the queue. Empty if ``queue.md`` does not exist.

    Raises
    ------
    WorqueueError
        If a line is neither ``- <ID>``, a ``#`` line, nor blank, or an ID appears twice.
        The message names the line number.
    """
    path = data / QUEUE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except UnicodeDecodeError:
        raise WorqueueError(f"{QUEUE_FILE}: UTF-8 として読めません") from None
    ids: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        match = _ENTRY.match(line)
        if not match:
            raise WorqueueError(f"{QUEUE_FILE} の {number} 行目を読めません（- <ID> の形にしてください）: {line}")
        task_id = int(match.group(1))
        if task_id in ids:
            raise WorqueueError(f"{QUEUE_FILE} の {number} 行目: タスク {task_id} が 2 回あります")
        ids.append(task_id)
    return ids


def write_queue(data: Path, ids: list[int]) -> Path:
    """Write the queue.

    Parameters
    ----------
    data : Path
        The data/ directory.
    ids : list of int
        Task IDs from the top of the queue.

    Returns
    -------
    Path
        The file written.
    """
    entries = "".join(f"- {task_id}\n" for task_id in ids)
    path = data / QUEUE_FILE
    write_text_atomic(path, f"{HEADING}\n\n{entries}" if entries else f"{HEADING}\n")
    return path
