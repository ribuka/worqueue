"""The git repository of data/: checking git, creating the repository, and committing."""

import os
import subprocess
import tempfile
from pathlib import Path

from worqueue.store.atomic import write_text_atomic
from worqueue.store.errors import WorqueueError
from worqueue.store.lock import LOCK_FILE

GITIGNORE_FILE = ".gitignore"


def check_git(data: Path) -> None:
    """Check that git can run and knows who commits, before anything is written.

    The identity is checked with the settings the commit will use: those of the
    data/ repository when it exists; otherwise only the global and system settings,
    since a repository created by ``ensure_repo`` does not inherit the local
    settings of a repository around data/.

    Parameters
    ----------
    data : Path
        The data/ directory.

    Raises
    ------
    WorqueueError
        If git is missing or the committer identity is not set.
    """
    try:
        version = _run(["git", "--version"], None)
    except FileNotFoundError:
        raise WorqueueError("git が見つかりません。git をインストールしてください") from None
    if version.returncode != 0:
        raise WorqueueError(f"git を実行できません: {version.stderr.strip()}")
    if (data / ".git").exists():
        ident = _run(["git", "-C", str(data), "var", "GIT_COMMITTER_IDENT"], None)
    else:
        ident = _committer_ident_outside_repositories()
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


def _committer_ident_outside_repositories() -> subprocess.CompletedProcess[str]:
    """Run ``git var GIT_COMMITTER_IDENT`` where no repository's local settings apply.

    It runs in an empty temporary directory with ``GIT_CEILING_DIRECTORIES`` at its
    parent, so git finds no repository even if the temporary directory is inside one.
    """
    with tempfile.TemporaryDirectory() as empty:
        env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(empty).parent)}
        return _run(["git", "var", "GIT_COMMITTER_IDENT"], Path(empty), env)


def _run(
    args: list[str], cwd: Path | None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a git command and capture its output as UTF-8."""
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
