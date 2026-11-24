"""Setup for CLI tests: running ``wq`` in-process with a fixed clock."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, tzinfo

import pytest

from worqueue.cli import add as add_command
from worqueue.cli.app import run


@dataclass(frozen=True)
class Result:
    """What one ``wq`` run produced.

    Attributes
    ----------
    code : int
        Exit code.
    out : str
        Standard output.
    err : str
        Standard error.
    """

    code: int
    out: str
    err: str


@pytest.fixture
def wq(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, now: datetime) -> Callable[..., Result]:
    """Return a function that runs ``wq`` with the given arguments, with the clock fixed at ``now``."""
    fixed = now

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(add_command, "datetime", FixedDatetime)

    def call(*argv: str) -> Result:
        capsys.readouterr()
        try:
            code = run(list(argv))
        except SystemExit as e:
            code = int(e.code or 0)
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return call
