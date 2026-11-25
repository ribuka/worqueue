"""File versions: telling whether a file changed after a caller (the Web UI) read it."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from worqueue.store.errors import StaleError

MISSING_VERSION = "none"


@dataclass(frozen=True)
class FileVersion:
    """The version of a file a caller read, to check before writing.

    Attributes
    ----------
    path : Path
        The file, under data/.
    version : str
        Its version when the caller read it, from ``file_version``.
    """

    path: Path
    version: str


def file_version(path: Path) -> str:
    """Return the version of a file: the SHA-256 of its bytes.

    Parameters
    ----------
    path : Path
        The file.

    Returns
    -------
    str
        The hexadecimal SHA-256 of its bytes, or ``"none"`` if it does not exist.
    """
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return MISSING_VERSION
    return hashlib.sha256(content).hexdigest()


def check_versions(data: Path, expected: tuple[FileVersion, ...]) -> None:
    """Raise if a file's version differs from the one expected.

    Parameters
    ----------
    data : Path
        The data/ directory, to name the file relative to it.
    expected : tuple of FileVersion
        Versions to check, in order.

    Raises
    ------
    StaleError
        For the first file whose version differs.
    """
    for item in expected:
        if file_version(item.path) != item.version:
            name = item.path.relative_to(data).as_posix()
            raise StaleError(f"{name} は画面を読み込んだ後に変わりました。読み込み直してください")
