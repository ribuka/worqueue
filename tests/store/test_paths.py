"""Tests of the location of data/."""

from pathlib import Path

import pytest

from worqueue.store.paths import DATA_ENV, data_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_data_dir_defaults_to_data_at_the_repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """``data_dir`` defaults to data at the repository root."""
    monkeypatch.delenv(DATA_ENV)

    assert (REPO_ROOT / "pyproject.toml").is_file()
    assert data_dir() == REPO_ROOT / "data"


def test_data_dir_ignores_an_empty_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """``data_dir`` ignores an empty variable."""
    monkeypatch.setenv(DATA_ENV, "")

    assert data_dir() == REPO_ROOT / "data"


def test_tests_get_a_temporary_data_dir(data: Path, tmp_path: Path) -> None:
    """The autouse fixture points ``data_dir`` at a temporary directory."""
    assert data_dir() == data
    assert data.is_relative_to(tmp_path)
    assert not data.resolve().is_relative_to(REPO_ROOT)
