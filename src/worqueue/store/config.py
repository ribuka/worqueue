"""Reading the settings in ``config.toml``, filled with the defaults."""

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from worqueue.store.errors import WorqueueError

CONFIG_FILE = "config.toml"


@dataclass(frozen=True)
class SuggestConfig:
    """Thresholds of the reorder suggestions (``[suggest]``).

    Attributes
    ----------
    due_within_days : int
        A task due within this many days should be near the top.
    top_n : int
        How many tasks from the top count as "near the top".
    stale_days : int
        A task handed to a member is stale after this many days without a history entry.
    """

    due_within_days: int = 3
    top_n: int = 5
    stale_days: int = 7


@dataclass(frozen=True)
class Config:
    """All settings.

    Attributes
    ----------
    suggest : SuggestConfig
        ``[suggest]``.
    """

    suggest: SuggestConfig = field(default_factory=SuggestConfig)


def load_config(data: Path) -> Config:
    """Read ``config.toml``, using the default for every value it does not set.

    Parameters
    ----------
    data : Path
        The data/ directory.

    Returns
    -------
    Config
        The settings. All defaults when the file does not exist.

    Raises
    ------
    WorqueueError
        On a TOML syntax error, an unknown table or key, or a value that is not an
        integer of 1 or more. The message names the key.
    """
    path = data / CONFIG_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    except UnicodeDecodeError:
        raise WorqueueError(f"{CONFIG_FILE}: UTF-8 として読めません") from None
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise WorqueueError(f"{CONFIG_FILE} を読めません: {e}") from None
    unknown = [name for name in document if name != "suggest"]
    if unknown:
        raise WorqueueError(f"{CONFIG_FILE} に未知のテーブルかキーがあります: {', '.join(unknown)}")
    return Config(suggest=_suggest(document.get("suggest", {})))


def _suggest(table: object) -> SuggestConfig:
    """Build ``[suggest]`` from its TOML table."""
    if not isinstance(table, dict):
        raise WorqueueError(f"{CONFIG_FILE} の suggest はテーブルにしてください")
    known = {f.name for f in fields(SuggestConfig)}
    unknown = [f"suggest.{key}" for key in table if key not in known]
    if unknown:
        raise WorqueueError(f"{CONFIG_FILE} に未知のキーがあります: {', '.join(unknown)}")
    for key, value in table.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise WorqueueError(f"{CONFIG_FILE} の suggest.{key} は 1 以上の整数にしてください: {value!r}")
    return SuggestConfig(**table)
