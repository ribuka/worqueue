"""Tests of ``wq edit``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

from worqueue.store.queue import write_queue

Git = Callable[..., str]


@pytest.fixture
def tasks(wq: Callable) -> None:
    """Create three tasks; the second has a body."""
    wq("add", "仕様を書く", "--kind", "implement")
    wq("add", "見積もる", "--kind", "manage", "--body", "古い本文")
    wq("add", "API の設計をレビューする", "--kind", "manage")


def changed_files(git: Git, data: Path) -> list[str]:
    """Return the files the last commit of data/ changed."""
    return sorted(git(data, "show", "--name-only", "--format=", "HEAD").split())


def commit_count(git: Git, data: Path) -> int:
    """Return the number of commits of data/."""
    return int(git(data, "rev-list", "--count", "HEAD"))


def stamp(now: datetime) -> str:
    """Return the time of a history entry written at ``now``."""
    return now.strftime("%Y-%m-%d %H:%M")


def front_matter(data: Path, task_id: int) -> str:
    """Return the front matter of a task's file, between the fences."""
    return (data / "tasks" / f"{task_id}.md").read_text(encoding="utf-8").split("---\n")[1]


def test_edit_changes_several_fields_in_one_commit(
    wq: Callable, tasks: None, data: Path, now: datetime, git: Git
) -> None:
    """``wq edit`` changes the given fields only, writes one history entry, and commits it."""
    result = wq(
        "edit", "2",
        "--title", "  見積もりを出す  ",
        "--status", "doing",
        "--kind", "implement",
        "--assignee", "佐藤",
        "--due", "2026-12-01",
        "--add-depends-on", "1",
        "--add-depends-on", "3",
        "--reason", "佐藤さんに依頼",
    )  # fmt: skip

    description = (
        "タイトル 見積もる → 見積もりを出す、状態 todo → doing、種別 manage → implement、"
        "担当 me → 佐藤、期限 なし → 2026-12-01、依存先 なし → 1, 3"
    )
    assert (result.code, result.err) == (0, "")
    assert result.out == f"変えました: 2 見積もりを出す（{description}）\n"
    created = now.astimezone().replace(microsecond=0).isoformat()
    assert front_matter(data, 2) == (
        "title: 見積もりを出す\nstatus: doing\nkind: implement\nassignee: 佐藤\ndue: 2026-12-01\n"
        f"depends_on: [1, 3]\ncreated: '{created}'\n"
    )
    text = (data / "tasks" / "2.md").read_text(encoding="utf-8")
    assert text.endswith(f"\n古い本文\n\n## 履歴\n\n- {stamp(now)} 作成\n- {stamp(now)} {description}: 佐藤さんに依頼\n")
    assert git(data, "log", "-1", "--format=%s") == f"edit 2: {description}\n"
    assert changed_files(git, data) == ["tasks/2.md"]


@pytest.mark.parametrize(
    ("args", "due", "depends_on", "entry"),
    [
        (["--no-due"], "null", "[2, 3]", "期限 2026-11-30 → なし"),
        (["--clear-depends-on"], "2026-11-30", "[]", "依存先 2, 3 → なし"),
        (["--remove-depends-on", "2"], "2026-11-30", "[3]", "依存先 2, 3 → 3"),
        (["--clear-depends-on", "--add-depends-on", "3", "--add-depends-on", "2"], "2026-11-30", "[3, 2]",
         "依存先 2, 3 → 3, 2"),
        (["--add-depends-on", "3", "--add-depends-on", "4", "--add-depends-on", "4"], "2026-11-30", "[2, 3, 4]",
         "依存先 2, 3 → 2, 3, 4"),
    ],
    ids=["no-due", "clear-depends-on", "remove", "clear-and-add", "add-present-and-twice"],
)  # fmt: skip
def test_edit_clears_and_changes_the_due_date_and_dependencies(
    wq: Callable, data: Path, now: datetime, args: list[str], due: str, depends_on: str, entry: str
) -> None:
    """``wq edit`` removes the due date and adds, removes, or replaces dependencies."""
    for title in ("a", "b", "c", "d"):
        wq("add", title, "--kind", "manage")
    wq("edit", "1", "--due", "2026-11-30", "--add-depends-on", "2", "--add-depends-on", "3")

    result = wq("edit", "1", *args)

    assert result.code == 0
    assert f"\ndue: {due}\ndepends_on: {depends_on}\n" in front_matter(data, 1)
    assert (data / "tasks" / "1.md").read_text(encoding="utf-8").endswith(f"- {stamp(now)} {entry}\n")


@pytest.mark.parametrize(
    "args",
    [
        ["--due", "2026-12-01", "--no-due"],
        ["--remove-depends-on", "1", "--clear-depends-on"],
        ["--status", "done"],
        ["--due", "2026-12-32"],
    ],
    ids=["due-and-no-due", "remove-and-clear", "done", "bad-date"],
)
def test_edit_rejects_bad_arguments_with_usage_error(
    wq: Callable, tasks: None, data: Path, git: Git, args: list[str]
) -> None:
    """Contradicting options, ``done``, and a malformed date are argument errors."""
    result = wq("edit", "2", *args)

    assert result.code == 2
    assert commit_count(git, data) == 3


@pytest.mark.parametrize("args", [[], ["--reason", "理由"], ["--json"]], ids=["nothing", "reason-only", "json-only"])
def test_edit_without_a_field_to_change_is_a_usage_error(
    wq: Callable, tasks: None, data: Path, git: Git, args: list[str]
) -> None:
    """``wq edit`` needs at least one option that changes something."""
    result = wq("edit", "1", *args)

    assert result.code == 2
    assert "変える項目を 1 つ以上指定してください" in result.err
    assert commit_count(git, data) == 3


@pytest.mark.parametrize(
    ("prepare", "args", "message"),
    [
        ([], ["--add-depends-on", "2"], "タスク 2 は自分自身に依存できません"),
        ([], ["--add-depends-on", "99"], "タスク 99 がありません"),
        ([["edit", "1", "--add-depends-on", "2"]], ["--add-depends-on", "1"], "依存が循環します: 2 → 1 → 2"),
        ([], ["--add-depends-on", "1", "--remove-depends-on", "1"], "タスク 1 を依存先に足しつつ外すことはできません"),
        ([], ["--title", "  "], "タイトルが空です"),
        ([], ["--assignee", "佐藤\n鈴木"], "担当に改行は入れられません"),
        ([], ["--status", "doing", "--reason", ""], "理由が空です"),
        ([], ["--body", "本文\n## 履歴\n- 偽の履歴"], "本文に「## 履歴」の行は入れられません"),
    ],
    ids=["self", "missing", "cycle", "add-and-remove", "empty-title", "assignee-newline", "empty-reason", "body-heading"],
)
def test_edit_rejects_bad_values_without_writing(
    wq: Callable, tasks: None, data: Path, git: Git, prepare: list[list[str]], args: list[str], message: str
) -> None:
    """``wq edit`` stops with exit code 1 and writes nothing when a value is invalid."""
    for argv in prepare:
        wq(*argv)
    count = commit_count(git, data)
    files = {p.name: p.read_bytes() for p in (data / "tasks").iterdir()}
    queue = (data / "queue.md").read_bytes()

    result = wq("edit", "2", *args)

    assert (result.code, result.out, result.err) == (1, "", f"{message}\n")
    assert {p.name: p.read_bytes() for p in (data / "tasks").iterdir()} == files
    assert (data / "queue.md").read_bytes() == queue
    assert commit_count(git, data) == count


def test_edit_reports_a_cycle_over_several_tasks(wq: Callable, tasks: None) -> None:
    """The cycle message lists the path from the task back to itself."""
    wq("edit", "3", "--add-depends-on", "2")
    wq("edit", "2", "--add-depends-on", "1")

    result = wq("edit", "1", "--add-depends-on", "3")

    assert (result.code, result.err) == (1, "依存が循環します: 1 → 3 → 2 → 1\n")


def test_edit_removes_a_dependency_whose_file_was_deleted(wq: Callable, tasks: None, data: Path) -> None:
    """A dependency on a task deleted by hand can be removed, and is a dead end for the cycle check."""
    wq("edit", "2", "--add-depends-on", "1")
    wq("edit", "3", "--add-depends-on", "1")
    (data / "tasks" / "1.md").unlink()
    write_queue(data, [2, 3])

    assert wq("edit", "2", "--add-depends-on", "3").code == 0
    result = wq("edit", "2", "--remove-depends-on", "1")

    assert result.code == 0
    assert "\ndepends_on: [3]\n" in front_matter(data, 2)


def test_edit_reopens_a_done_task_at_the_end_of_the_queue(
    wq: Callable, tasks: None, data: Path, now: datetime, git: Git
) -> None:
    """Changing a done task's status puts it back at the end of the queue."""
    wq("done", "1")

    result = wq("edit", "1", "--status", "todo", "--json")

    assert result.code == 0
    shown = json.loads(wq("show", "1", "--json").out)["task"]
    del shown["markdown"]
    assert json.loads(result.out) == {"task": shown, "changed": ["status"]}
    assert (shown["status"], shown["position"]) == ("todo", 3)
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 2\n- 3\n- 1\n"
    assert [t["id"] for t in json.loads(wq("list", "--json").out)["tasks"]] == [2, 3, 1]
    assert (data / "tasks" / "1.md").read_text(encoding="utf-8").endswith(f"- {stamp(now)} 状態 done → todo\n")
    assert changed_files(git, data) == ["queue.md", "tasks/1.md"]


def test_edit_reopens_a_done_task_left_in_the_queue_at_its_line(wq: Callable, tasks: None, data: Path, git: Git) -> None:
    """A done task left in ``queue.md`` by hand comes back where its line is."""
    wq("done", "2")
    write_queue(data, [1, 2, 3])
    git(data, "commit", "-qam", "手で戻す")

    result = wq("edit", "2", "--status", "waiting", "--json")

    assert json.loads(result.out)["task"]["position"] == 2
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 1\n- 2\n- 3\n"
    assert changed_files(git, data) == ["tasks/2.md"]


def test_edit_between_open_statuses_leaves_the_queue(wq: Callable, tasks: None, data: Path, git: Git) -> None:
    """Changing between open statuses does not write ``queue.md``."""
    result = wq("edit", "3", "--status", "waiting")

    assert result.code == 0
    assert (data / "queue.md").read_bytes() == b"# Queue\n\n- 1\n- 2\n- 3\n"
    assert changed_files(git, data) == ["tasks/3.md"]


def test_edit_body_replaces_only_the_body(wq: Callable, tasks: None, data: Path, now: datetime) -> None:
    """``--body`` replaces the body and keeps the history."""
    wq("log", "2", "相談した")

    result = wq("edit", "2", "--body", "  新しい本文\n\n2 段落目  ")

    assert result.out == "変えました: 2 見積もる（本文を変更）\n"
    text = (data / "tasks" / "2.md").read_text(encoding="utf-8")
    assert text.split("---\n", 2)[2] == (
        f"\n新しい本文\n\n2 段落目\n\n## 履歴\n\n- {stamp(now)} 作成\n- {stamp(now)} 相談した\n- {stamp(now)} 本文を変更\n"
    )


def test_edit_body_to_empty(wq: Callable, tasks: None, data: Path, now: datetime) -> None:
    """``--body ""`` empties the body."""
    result = wq("edit", "2", "--body", "")

    assert result.code == 0
    text = (data / "tasks" / "2.md").read_text(encoding="utf-8")
    assert text.split("---\n", 2)[2] == f"\n## 履歴\n\n- {stamp(now)} 作成\n- {stamp(now)} 本文を変更\n"


@pytest.mark.parametrize(
    "args",
    [
        ["--status", "todo", "--reason", "理由"],
        ["--title", " 見積もる ", "--body", "古い本文", "--remove-depends-on", "9", "--no-due"],
    ],
    ids=["status", "several"],
)
def test_edit_to_the_same_values_writes_and_commits_nothing(
    wq: Callable, tasks: None, data: Path, git: Git, args: list[str]
) -> None:
    """``wq edit`` with the current values succeeds without writing or committing."""
    before = (data / "tasks" / "2.md").read_bytes()

    result = wq("edit", "2", *args)
    as_json = wq("edit", "2", *args, "--json")

    assert (result.code, result.out) == (0, "変えませんでした: 2 見積もる（どの項目も今と同じ）\n")
    assert (as_json.code, json.loads(as_json.out)["changed"]) == (0, [])
    assert json.loads(as_json.out)["task"]["position"] == 2
    assert (data / "tasks" / "2.md").read_bytes() == before
    assert commit_count(git, data) == 3
    assert git(data, "status", "--porcelain") == ""


def test_edit_json_prints_the_task_and_the_changed_fields(wq: Callable, tasks: None) -> None:
    """``wq edit --json`` prints the task after the edit and the changed fields in order."""
    result = wq("edit", "3", "--assignee", "佐藤", "--status", "doing", "--json")

    assert result.code == 0
    printed = json.loads(result.out)
    assert printed["changed"] == ["status", "assignee"]
    assert {k: printed["task"][k] for k in ("id", "position", "status", "assignee")} == {
        "id": 3,
        "position": 3,
        "status": "doing",
        "assignee": "佐藤",
    }


def test_edit_json_has_no_position_for_a_task_out_of_the_queue(wq: Callable, tasks: None, data: Path) -> None:
    """A task out of the queue has a null position."""
    write_queue(data, [1, 2])

    result = wq("edit", "3", "--kind", "implement", "--json")

    assert json.loads(result.out)["task"]["position"] is None


def test_edit_json_reports_a_missing_task(wq: Callable, tasks: None) -> None:
    """A missing task is an error in JSON with ``--json``."""
    result = wq("edit", "99", "--status", "doing", "--json")

    assert (result.code, result.out) == (1, "")
    assert json.loads(result.err) == {"error": "タスク 99 がありません"}
