"""The task type and reading and writing task files (``tasks/<ID>.md``)."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from worqueue.store.atomic import write_text_atomic
from worqueue.store.errors import WorqueueError

TASKS_DIR = "tasks"
STATUSES = ("todo", "doing", "waiting", "done")
OPEN_STATUSES = ("todo", "doing", "waiting")
KINDS = ("manage", "implement")
# The assignee of a task that is my own, not handed to a member.
MY_ASSIGNEE = "me"
HISTORY_HEADING = "## 履歴"
FIELD_NAMES = ("title", "status", "kind", "assignee", "due", "depends_on", "created")
FRONT_MATTER_FENCE = "---"
# A history entry's date; the time and the rest are free, so that lines written by hand count.
_HISTORY_DATE = re.compile(r"^- ([0-9]{4}-[0-9]{2}-[0-9]{2})(?:\s|$)")


@dataclass(frozen=True)
class Task:
    """A task: the front matter fields and the Markdown after them.

    Attributes
    ----------
    id : int
        Task ID, the stem of the file name.
    title : str
        One-line name.
    status : str
        One of ``STATUSES``.
    kind : str
        One of ``KINDS``.
    assignee : str
        ``me`` or a member's name.
    due : date or None
        Due date.
    depends_on : tuple of int
        IDs of the tasks this task waits for.
    created : str
        Creation time as an ISO 8601 string with a time zone.
    markdown : str
        Everything after the closing ``---`` of the front matter (body and history).
    """

    id: int
    title: str
    status: str
    kind: str
    assignee: str
    due: date | None
    depends_on: tuple[int, ...]
    created: str
    markdown: str

    def summary(self, position: int | None) -> dict[str, object]:
        """Return the task's JSON object for the CLI, without the body and history.

        Parameters
        ----------
        position : int or None
            1-based position among the tasks ``wq list`` shows, or None for a task
            it does not show (``done``, or not in the queue).

        Returns
        -------
        dict
            The fields in the order of the documented JSON shape.
        """
        return {
            "id": self.id,
            "position": position,
            "title": self.title,
            "status": self.status,
            "kind": self.kind,
            "assignee": self.assignee,
            "due": self.due.isoformat() if self.due else None,
            "depends_on": list(self.depends_on),
            "created": self.created,
        }


def task_path(data: Path, task_id: int) -> Path:
    """Return the path of a task's file.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID.

    Returns
    -------
    Path
        ``data/tasks/<ID>.md``.
    """
    return data / TASKS_DIR / f"{task_id}.md"


def task_ids(data: Path) -> list[int]:
    """Return the IDs of the task files in ``data/tasks``.

    Parameters
    ----------
    data : Path
        The data/ directory.

    Returns
    -------
    list of int
        IDs of files named ``<digits>.md``, in no particular order.
    """
    tasks_dir = data / TASKS_DIR
    if not tasks_dir.is_dir():
        return []
    return [int(p.stem) for p in tasks_dir.glob("*.md") if p.stem.isdigit()]


def initial_markdown(body: str, created_at: datetime) -> str:
    """Return the Markdown of a new task: the body and a history with one entry.

    Parameters
    ----------
    body : str
        Description. Empty for none.
    created_at : datetime
        Creation time, written in local time.

    Returns
    -------
    str
        Markdown to put after the front matter.
    """
    body_part = f"{body}\n\n" if body else ""
    return f"\n{body_part}{HISTORY_HEADING}\n\n{history_line(created_at, '作成')}\n"


def history_line(at: datetime, content: str) -> str:
    """Return one history entry.

    Parameters
    ----------
    at : datetime
        Time of the entry, written in local time.
    content : str
        What happened.

    Returns
    -------
    str
        ``- <YYYY-MM-DD HH:MM> <content>``.
    """
    return f"- {at.astimezone().strftime('%Y-%m-%d %H:%M')} {content}"


def append_history(markdown: str, line: str) -> str:
    """Return ``markdown`` with one history entry added at its end.

    Parameters
    ----------
    markdown : str
        The Markdown after the front matter (body and history).
    line : str
        The entry, from ``history_line``.

    Returns
    -------
    str
        With a line that is just the history heading, the entry follows the last
        line (after a blank line when that line is the heading). Without one, a
        history heading and the entry are added after the Markdown.
    """
    stripped = markdown.rstrip("\n")
    lines = stripped.split("\n")
    if HISTORY_HEADING in lines:
        last = next(text for text in reversed(lines) if text.strip())
        separator = "\n\n" if last == HISTORY_HEADING else "\n"
        return f"{stripped}{separator}{line}\n"
    if not stripped:
        return f"\n{HISTORY_HEADING}\n\n{line}\n"
    return f"{stripped}\n\n{HISTORY_HEADING}\n\n{line}\n"


def history_dates(markdown: str) -> list[date]:
    """Return the dates of the history entries.

    Parameters
    ----------
    markdown : str
        The Markdown after the front matter (body and history).

    Returns
    -------
    list of date
        The date of each line after the first history heading line that starts with
        ``- <YYYY-MM-DD>``, in the order of the lines. Other lines, and dates that
        do not exist, are skipped. Empty without a history heading line.
    """
    _, history = _split_history(markdown)
    if history is None:
        return []
    dates: list[date] = []
    for line in history.split("\n"):
        match = _HISTORY_DATE.match(line)
        if match is None:
            continue
        try:
            dates.append(date.fromisoformat(match.group(1)))
        except ValueError:
            continue
    return dates


def body_of(markdown: str) -> str:
    """Return the body: the Markdown before the first history heading line.

    Parameters
    ----------
    markdown : str
        The Markdown after the front matter (body and history).

    Returns
    -------
    str
        The part before the first line that is just the history heading (all of
        ``markdown`` without one), stripped of surrounding whitespace.
    """
    body, _ = _split_history(markdown)
    return body.strip()


def replace_body(markdown: str, body: str) -> str:
    """Return ``markdown`` with its body replaced and its history kept as it is.

    Parameters
    ----------
    markdown : str
        The Markdown after the front matter (body and history).
    body : str
        The new body, already stripped. Empty for none.

    Returns
    -------
    str
        With a history heading line: a newline, the body and a blank line (if the
        body is not empty), and everything from the heading line on. Without one:
        the body between two newlines, or a single newline for an empty body.
    """
    _, history = _split_history(markdown)
    if history is None:
        return f"\n{body}\n" if body else "\n"
    body_part = f"{body}\n\n" if body else ""
    return f"\n{body_part}{history}"


def _split_history(markdown: str) -> tuple[str, str | None]:
    """Split ``markdown`` at its first history heading line: (before it, from it on, or None)."""
    lines = markdown.split("\n")
    if HISTORY_HEADING not in lines:
        return markdown, None
    at = lines.index(HISTORY_HEADING)
    return "\n".join(lines[:at]), "\n".join(lines[at:])


def write_task(data: Path, task: Task) -> Path:
    """Write a task's file.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task : Task
        Task to write.

    Returns
    -------
    Path
        The file written.
    """
    fields = {
        "title": task.title,
        "status": task.status,
        "kind": task.kind,
        "assignee": task.assignee,
        "due": task.due,
        "depends_on": list(task.depends_on),
        "created": task.created,
    }
    front_matter = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=None)
    path = task_path(data, task.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, f"{FRONT_MATTER_FENCE}\n{front_matter}{FRONT_MATTER_FENCE}\n{task.markdown}")
    return path


def read_task(data: Path, task_id: int) -> Task:
    """Read a task's file.

    Parameters
    ----------
    data : Path
        The data/ directory.
    task_id : int
        Task ID.

    Returns
    -------
    Task
        The task.

    Raises
    ------
    WorqueueError
        If the file is missing or malformed. The message names the file.
    """
    path = task_path(data, task_id)
    name = f"{TASKS_DIR}/{path.name}"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WorqueueError(f"タスク {task_id} のファイルがありません: {name}") from None
    except UnicodeDecodeError:
        raise WorqueueError(f"{name}: UTF-8 として読めません") from None
    try:
        return _parse_task(task_id, text)
    except _InvalidTaskError as e:
        raise WorqueueError(f"{name}: {e}") from None


class _InvalidTaskError(Exception):
    """A problem in a task file's text, reported with the file name by ``read_task``."""


def _parse_task(task_id: int, text: str) -> Task:
    """Parse a task file's text."""
    front_matter, markdown = _split_front_matter(text)
    try:
        fields = yaml.safe_load(front_matter)
    except (yaml.YAMLError, ValueError) as e:
        # Building a date or time that does not exist (due: 2026-11-31) raises ValueError.
        raise _InvalidTaskError(f"front matter の YAML を読めません: {e}") from None
    if not isinstance(fields, dict):
        raise _InvalidTaskError("front matter がキーと値の組ではありません")
    missing = [k for k in FIELD_NAMES if k not in fields]
    if missing:
        raise _InvalidTaskError(f"front matter にキーがありません: {', '.join(missing)}")
    unknown = [str(k) for k in fields if k not in FIELD_NAMES]
    if unknown:
        raise _InvalidTaskError(f"front matter に未知のキーがあります: {', '.join(unknown)}")
    return Task(
        id=task_id,
        title=_one_line(fields, "title"),
        status=_choice(fields, "status", STATUSES),
        kind=_choice(fields, "kind", KINDS),
        assignee=_one_line(fields, "assignee"),
        due=_due(fields["due"]),
        depends_on=_depends_on(fields["depends_on"]),
        created=_created(fields["created"]),
        markdown=markdown,
    )


def _split_front_matter(text: str) -> tuple[str, str]:
    """Split a task file into the front matter and the Markdown after it."""
    lines = text.split("\n")
    if lines[0] != FRONT_MATTER_FENCE:
        raise _InvalidTaskError("front matter（先頭の ---）がありません")
    for i, line in enumerate(lines[1:], start=1):
        if line == FRONT_MATTER_FENCE:
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    raise _InvalidTaskError("front matter が閉じていません（2 つ目の --- がありません）")


def _one_line(fields: dict, key: str) -> str:
    """Return a non-empty one-line string field."""
    value = fields[key]
    if not isinstance(value, str) or not value.strip() or "\n" in value:
        raise _InvalidTaskError(f"{key} は空でない 1 行の文字列にしてください: {value!r}")
    return value


def _choice(fields: dict, key: str, choices: tuple[str, ...]) -> str:
    """Return a field whose value must be one of ``choices``."""
    value = fields[key]
    if value not in choices:
        raise _InvalidTaskError(f"{key} は {', '.join(choices)} のどれかにしてください: {value!r}")
    return value


def _due(value: object) -> date | None:
    """Return the ``due`` field: a date or None."""
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise _InvalidTaskError(f"due は日付（YYYY-MM-DD）か null にしてください: {value!r}")
    return value


def _depends_on(value: object) -> tuple[int, ...]:
    """Return the ``depends_on`` field: a list of integers."""
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise _InvalidTaskError(f"depends_on は整数のリストにしてください: {value!r}")
    return tuple(value)


def _created(value: object) -> str:
    """Return the ``created`` field as an ISO 8601 string, whether YAML made it a datetime or not."""
    parsed = value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
    if not isinstance(parsed, datetime) or parsed.tzinfo is None:
        raise _InvalidTaskError(f"created はタイムゾーン付きの ISO 8601 の日時にしてください: {value!r}")
    return value if isinstance(value, str) else parsed.isoformat()
