"""The write lock on data/ that makes writers take turns."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from worqueue.store.errors import WorqueueError

LOCK_FILE = ".lock"
LOCK_TIMEOUT_SECONDS = 10.0


@contextmanager
def write_lock(data: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> Generator[None]:
    """Hold the write lock on data/ for the duration of the ``with`` block.

    The lock is an OS file lock, so it is released when the process ends, even by a crash.

    Parameters
    ----------
    data : Path
        The data/ directory. It must exist.
    timeout : float
        Seconds to wait for the lock.

    Yields
    ------
    None
        While the lock is held.

    Raises
    ------
    WorqueueError
        If the lock is not acquired within ``timeout`` seconds.
    """
    lock = FileLock(data / LOCK_FILE, timeout=timeout)
    try:
        lock.acquire()
    except Timeout:
        raise WorqueueError(
            f"{timeout:g} 秒待っても data/ のロック（{LOCK_FILE}）を取れませんでした。"
            "他の書き込みが終わってから、もう一度実行してください"
        ) from None
    try:
        yield
    finally:
        lock.release()
