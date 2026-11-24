"""The git repository of data/: checking git, creating the repository, and committing."""

import subprocess
from pathlib import Path

from worqueue.store.atomic import write_text_atomic
from worqueue.store.errors import WorqueueError
from worqueue.store.lock import LOCK_FILE

GITIGNORE_FILE = ".gitignore"


def check_git(data: Path) -> None:
    """Check that git can run and knows who commits, before anything is written.

    Parameters
    ----------
    data : Path
        The data/ directory. Used as the working directory when it exists.

    Raises
    ------
    WorqueueError
        If git is missing or the committer identity is not set.
    """
    cwd = data if data.is_dir() else None
    try:
        version = _run(["git", "--version"], cwd)
    except FileNotFoundError:
        raise WorqueueError("git が見つかりません。git をインストールしてください") from None
    if version.returncode != 0:
        raise WorqueueError(f"git を実行できません: {version.stderr.strip()}")
    ident = _run(["git", "var", "GIT_COMMITTER_IDENT"], cwd)
    if ident.returncode != 0:
        raise WorqueueError(
            "git のコミットする人が決まっていません（git config user.name と user.email を設定してください）: "
            f"{ident.stderr.strip()}"
        )


def ensure_repo(data: Path) -> list[Path]:
    """Make data/ a git repository if it is not one yet.

    Whether data/ is a repository is decided by ``data/.git`` existing, not by
    ``git rev-parse``, which would find the worqueue repository around data/.

    Parameters
    ----------
    data : Path
        The data/ directory. It must exist.

    Returns
    -------
    list of Path
        Files written (``.gitignore``) for the caller to commit; empty if the
        repository already existed.

    Raises
    ------
    WorqueueError
        If ``git init`` fails.
    """
    if (data / ".git").exists():
        return []
    result = _run(["git", "init", "-q", "-b", "main", str(data)], None)
    if result.returncode != 0:
        raise WorqueueError(f"data/ を git のリポジトリにできませんでした: {result.stderr.strip()}")
    gitignore = data / GITIGNORE_FILE
    write_text_atomic(gitignore, f"{LOCK_FILE}\n")
    return [gitignore]


def commit(data: Path, paths: list[Path], message: str) -> None:
    """Commit only ``paths``, leaving other uncommitted changes in data/ as they are.

    Parameters
    ----------
    data : Path
        The data/ directory, a git repository.
    paths : list of Path
        Files this operation wrote.
    message : str
        Commit message.

    Raises
    ------
    WorqueueError
        If ``git add`` or ``git commit`` fails. The files stay written.
    """
    relative = [path.relative_to(data).as_posix() for path in paths]
    for command in (["add", "--", *relative], ["commit", "-q", "-m", message, "--", *relative]):
        result = _run(["git", "-C", str(data), *command], None)
        if result.returncode != 0:
            raise WorqueueError(
                f"ファイルは書きましたが、data/ の git にコミットできませんでした: {result.stderr.strip()}"
            )


def _run(args: list[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    """Run a git command and capture its output as UTF-8."""
    return subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
