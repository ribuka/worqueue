"""Atomic replacement of text files, so that readers never see a half-written file."""

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` as UTF-8 with LF line endings, replacing it atomically.

    Parameters
    ----------
    path : Path
        File to write. Its parent directory must exist.
    text : str
        Content to write.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
