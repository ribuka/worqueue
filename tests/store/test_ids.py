"""Tests of allocating task IDs."""

from pathlib import Path

import pytest

from worqueue.store.errors import WorqueueError
from worqueue.store.ids import next_id, write_next_id


def make_task_file(data: Path, task_id: int) -> None:
    """Create an (empty) task file; ``next_id`` looks only at the names."""
    (data / "tasks").mkdir(parents=True, exist_ok=True)
    (data / "tasks" / f"{task_id}.md").write_text("", encoding="utf-8")


def test_next_id_starts_at_one(data: Path) -> None:
    """``next_id`` starts at one."""
    assert next_id(data) == 1


def test_next_id_uses_the_file(data: Path) -> None:
    """``next_id`` uses the file."""
    data.mkdir()
    write_next_id(data, 43)

    assert (data / "next_id").read_bytes() == b"43\n"
    assert next_id(data) == 43


def test_next_id_follows_task_files_without_the_file(data: Path) -> None:
    """``next_id`` follows task files without the file."""
    make_task_file(data, 5)

    assert next_id(data) == 6


@pytest.mark.parametrize(("stored", "expected"), [(3, 6), (9, 9)])
def test_next_id_takes_the_larger(data: Path, stored: int, expected: int) -> None:
    """``next_id`` takes the larger."""
    make_task_file(data, 5)
    write_next_id(data, stored)

    assert next_id(data) == expected


@pytest.mark.parametrize("text", ["", "abc\n", "0\n", "-1\n"])
def test_next_id_rejects_a_bad_file(data: Path, text: str) -> None:
    """``next_id`` rejects a bad file."""
    data.mkdir()
    (data / "next_id").write_text(text, encoding="utf-8")

    with pytest.raises(WorqueueError, match="next_id"):
        next_id(data)
