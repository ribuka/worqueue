"""Tests of file versions."""

from pathlib import Path

import pytest

from worqueue.store.errors import StaleError
from worqueue.store.versions import (
    MISSING_VERSION,
    FileVersion,
    check_versions,
    file_version,
)


def test_file_version_follows_the_bytes(tmp_path: Path) -> None:
    """The version changes with the bytes and is ``none`` for a missing file."""
    path = tmp_path / "a.md"
    assert file_version(path) == MISSING_VERSION

    path.write_bytes(b"one")
    first = file_version(path)
    path.write_bytes(b"two")

    assert first != file_version(path)
    path.write_bytes(b"one")
    assert file_version(path) == first


def test_check_versions_names_the_first_changed_file(tmp_path: Path) -> None:
    """``check_versions`` passes matching versions and names the first stale file relative to data/."""
    (tmp_path / "tasks").mkdir()
    task = tmp_path / "tasks" / "1.md"
    queue = tmp_path / "queue.md"
    task.write_bytes(b"task")
    queue.write_bytes(b"queue")
    check_versions(tmp_path, (FileVersion(task, file_version(task)), FileVersion(queue, file_version(queue))))

    with pytest.raises(StaleError, match=r"^tasks/1\.md は画面を読み込んだ後に変わりました。読み込み直してください$"):
        check_versions(tmp_path, (FileVersion(task, "old"), FileVersion(queue, "old")))
