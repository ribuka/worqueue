"""Tests of reading config.toml."""

from pathlib import Path

import pytest

from worqueue.store.config import Config, SuggestConfig, load_config
from worqueue.store.errors import WorqueueError


def write_config(data: Path, text: str) -> None:
    """Write ``data/config.toml``."""
    data.mkdir(exist_ok=True)
    (data / "config.toml").write_text(text, encoding="utf-8")


def test_load_config_without_the_file_uses_the_defaults(data: Path) -> None:
    """``load_config`` without the file uses the defaults."""
    assert load_config(data) == Config(suggest=SuggestConfig(due_within_days=3, top_n=5, stale_days=7))


def test_load_config_overrides_only_the_keys_given(data: Path) -> None:
    """``load_config`` overrides only the keys given."""
    write_config(data, "[suggest]\ntop_n = 10\n")

    assert load_config(data).suggest == SuggestConfig(due_within_days=3, top_n=10, stale_days=7)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[suggest]\nlimit = 3\n", "suggest.limit"),
        ("[other]\nx = 1\n", "other"),
        ("[suggest]\ntop_n = 0\n", "suggest.top_n"),
        ("[suggest]\ntop_n = true\n", "suggest.top_n"),
        ("[suggest]\ntop_n = '5'\n", "suggest.top_n"),
        ("suggest = 3\n", "suggest"),
        ("[suggest\n", "config.toml を読めません"),
    ],
)
def test_load_config_rejects_bad_settings(data: Path, text: str, message: str) -> None:
    """``load_config`` rejects bad settings."""
    write_config(data, text)

    with pytest.raises(WorqueueError, match=message):
        load_config(data)
