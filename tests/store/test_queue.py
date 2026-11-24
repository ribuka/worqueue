"""Tests of reading and writing queue.md."""

from pathlib import Path

import pytest

from worqueue.store.errors import WorqueueError
from worqueue.store.queue import read_queue, write_queue


@pytest.fixture
def queue_file(data: Path) -> Path:
    """Return the path of queue.md in an existing data/."""
    data.mkdir()
    return data / "queue.md"


def test_write_queue_lists_ids_under_the_heading(data: Path, queue_file: Path) -> None:
    """``write_queue`` lists ids under the heading."""
    write_queue(data, [40, 42, 38])

    assert queue_file.read_bytes() == b"# Queue\n\n- 40\n- 42\n- 38\n"


def test_write_queue_of_nothing_writes_only_the_heading(data: Path, queue_file: Path) -> None:
    """``write_queue`` of nothing writes only the heading."""
    write_queue(data, [])

    assert queue_file.read_bytes() == b"# Queue\n"


def test_read_queue_skips_headings_and_blank_lines(data: Path, queue_file: Path) -> None:
    """``read_queue`` skips headings and blank lines."""
    queue_file.write_text("# Queue\n\n- 40\n## later\n- 42  \n\n- 38\n", encoding="utf-8")

    assert read_queue(data) == [40, 42, 38]


def test_read_queue_without_the_file_is_empty(data: Path) -> None:
    """``read_queue`` without the file is empty."""
    assert read_queue(data) == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# Queue\n\n- 40\n* 42\n", "queue.md の 4 行目を読めません"),
        ("# Queue\n\n- 40\n- x\n", "queue.md の 4 行目を読めません"),
        ("# Queue\n\n- 40\n- 42\n- 40\n", "queue.md の 5 行目: タスク 40 が 2 回あります"),
    ],
)
def test_read_queue_rejects_a_bad_line(data: Path, queue_file: Path, text: str, message: str) -> None:
    """``read_queue`` rejects a bad line."""
    queue_file.write_text(text, encoding="utf-8")

    with pytest.raises(WorqueueError, match=message):
        read_queue(data)
