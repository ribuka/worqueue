"""Plain-text tables for people, aligned by East Asian display width."""

import unicodedata

COLUMN_GAP = "  "


def display_width(text: str) -> int:
    """Return the number of terminal columns ``text`` takes.

    Parameters
    ----------
    text : str
        Text to measure.

    Returns
    -------
    int
        Characters whose East Asian width is ``W`` or ``F`` count as 2, others as 1.
    """
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def render_table(header: list[str], rows: list[list[str]]) -> str:
    """Return a table whose columns are left-aligned and separated by two spaces.

    The last column is not padded, so a long value there does not widen the table.

    Parameters
    ----------
    header : list of str
        Column names.
    rows : list of list of str
        Cells, one list per row, as many as ``header``.

    Returns
    -------
    str
        The lines of the table joined by newlines, without a trailing newline.
    """
    lines = [header, *rows]
    widths = [max(display_width(line[i]) for line in lines) for i in range(len(header) - 1)]
    return "\n".join(
        COLUMN_GAP.join([*(_pad(cell, width) for cell, width in zip(line, widths, strict=False)), line[-1]])
        for line in lines
    )


def _pad(text: str, width: int) -> str:
    """Pad ``text`` with spaces to ``width`` display columns."""
    return text + " " * (width - display_width(text))
