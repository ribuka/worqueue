"""Location of the data/ directory."""

import os
from pathlib import Path

import worqueue

DATA_ENV = "WORQUEUE_DATA"


def data_dir() -> Path:
    """Return the data/ directory.

    Returns
    -------
    Path
        ``$WORQUEUE_DATA`` when it is set and not empty; otherwise ``data/``
        at the root of the repository that holds this package.
    """
    override = os.environ.get(DATA_ENV, "")
    if override:
        return Path(override)
    return Path(worqueue.__file__).resolve().parents[2] / "data"
