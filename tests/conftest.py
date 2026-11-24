"""Shared test setup: a temporary data/ and a git isolated from the user's configuration."""

import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from worqueue.store.paths import DATA_ENV


@pytest.fixture(autouse=True)
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``WORQUEUE_DATA`` at a temporary data/ and isolate git from the user's settings.

    Every test gets this, so no test can write to the real data/. The directory itself
    is not created: the code under test creates it when it writes.
    """
    data = tmp_path / "data"
    monkeypatch.setenv(DATA_ENV, str(data))
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    return data


@pytest.fixture
def now() -> datetime:
    """Return a fixed time in the local time zone, as the CLI passes ``datetime.now().astimezone()``."""
    return datetime(2026, 11, 24, 9, 10, 0).astimezone()


@pytest.fixture
def git() -> Callable[..., str]:
    """Return a function that runs git in a directory and returns its stdout."""

    def run(cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, encoding="utf-8", check=True
        )
        return result.stdout

    return run
