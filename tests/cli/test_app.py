"""Tests of the ``wq`` command itself."""

from collections.abc import Callable

from worqueue.cli.table import display_width, render_table


def test_wq_without_a_command_prints_help_with_exit_code_2(wq: Callable) -> None:
    """``wq`` without a command prints help with exit code 2."""
    result = wq()

    assert result.code == 2
    assert "usage: wq" in result.err
    assert "add" in result.err
    assert "list" in result.err


def test_display_width_counts_wide_characters_as_two() -> None:
    """``display_width`` counts wide characters as two."""
    assert display_width("ab") == 2
    assert display_width("佐藤") == 4
    assert display_width("ＡＢ") == 4


def test_render_table_does_not_pad_the_last_column() -> None:
    """``render_table`` does not pad the last column."""
    assert render_table(["A", "B"], [["佐藤", "x"], ["a", "長い値"]]) == "A     B\n佐藤  x\na     長い値"
