"""Tests of ``wq move``."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

Git = Callable[..., str]


@pytest.fixture
def four_tasks(wq: Callable) -> None:
    """Create four tasks, queued 1, 2, 3, 4."""
    for title in ("1 つ目", "2 つ目", "3 つ目", "4 つ目"):
        wq("add", title, "--kind", "implement")


def queue_ids(data: Path) -> list[int]:
    """Return the IDs in queue.md, read from its lines."""
    text = (data / "queue.md").read_text(encoding="utf-8")
    return [int(line[2:]) for line in text.splitlines() if line.startswith("- ")]


def commit_count(git: Git, data: Path) -> int:
    """Return the number of commits of data/."""
    return int(git(data, "rev-list", "--count", "HEAD"))


MOVES = [
    (["4", "--top"], 4, 4, 1, [4, 1, 2, 3]),
    (["1", "--bottom"], 1, 1, 4, [2, 3, 4, 1]),
    (["1", "--to", "3"], 1, 1, 3, [2, 3, 1, 4]),
    (["4", "--before", "2"], 4, 4, 2, [1, 4, 2, 3]),
    (["1", "--after", "3"], 1, 1, 3, [2, 3, 1, 4]),
]
MOVE_IDS = ["top", "bottom", "to", "before", "after"]


@pytest.mark.parametrize(("args", "task_id", "start", "end", "queue"), MOVES, ids=MOVE_IDS)
def test_move_without_reason_writes_only_queue_md(
    wq: Callable,
    four_tasks: None,
    data: Path,
    git: Git,
    args: list[str],
    task_id: int,
    start: int,
    end: int,
    queue: list[int],
) -> None:
    """``wq move`` without a reason rewrites queue.md only, in one commit."""
    task_file = (data / "tasks" / f"{task_id}.md").read_bytes()

    result = wq("move", *args)

    assert (result.code, result.err) == (0, "")
    assert result.out == f"動かしました: {task_id} {task_id} つ目（{start} → {end} 番目）\n"
    assert queue_ids(data) == queue
    assert git(data, "log", "-1", "--format=%s") == f"move {task_id}: {start} → {end}\n"
    assert git(data, "show", "--name-only", "--format=", "HEAD").split() == ["queue.md"]
    assert (data / "tasks" / f"{task_id}.md").read_bytes() == task_file


@pytest.mark.parametrize(("args", "task_id", "start", "end", "queue"), MOVES, ids=MOVE_IDS)
def test_move_with_reason_writes_the_history_and_queue_md(
    wq: Callable,
    four_tasks: None,
    data: Path,
    now: datetime,
    git: Git,
    args: list[str],
    task_id: int,
    start: int,
    end: int,
    queue: list[int],
) -> None:
    """``wq move --reason`` writes the history line and queue.md in one commit, and prints JSON."""
    result = wq("move", *args, "--reason", " 期限が近い ", "--json")

    assert result.code == 0
    output = json.loads(result.out)
    assert output["from"] == start
    assert (output["task"]["id"], output["task"]["position"]) == (task_id, end)
    assert queue_ids(data) == queue
    text = (data / "tasks" / f"{task_id}.md").read_text(encoding="utf-8")
    assert text.endswith(f"作成\n- {now.strftime('%Y-%m-%d %H:%M')} 移動 {start} → {end}: 期限が近い\n")
    assert git(data, "log", "-1", "--format=%s") == f"move {task_id}: {start} → {end}\n"
    assert sorted(git(data, "show", "--name-only", "--format=", "HEAD").split()) == [
        "queue.md",
        f"tasks/{task_id}.md",
    ]
    assert commit_count(git, data) == 5


def test_move_skips_a_done_task_left_in_queue_md(wq: Callable, four_tasks: None, data: Path) -> None:
    """``wq move`` counts positions without a done task left in queue.md and keeps its line."""
    path = data / "tasks" / "2.md"
    path.write_text(path.read_text(encoding="utf-8").replace("status: todo", "status: done"), encoding="utf-8")

    result = wq("move", "4", "--to", "2")

    assert result.out == "動かしました: 4 4 つ目（3 → 2 番目）\n"
    assert queue_ids(data) == [1, 2, 4, 3]
    assert [t["id"] for t in json.loads(wq("list", "--json").out)["tasks"]] == [1, 4, 3]


@pytest.mark.parametrize(
    "args",
    [["2", "--to", "2"], ["1", "--top"], ["4", "--bottom"], ["3", "--after", "2"], ["2", "--before", "3"]],
    ids=["to", "top", "bottom", "after", "before"],
)
def test_move_to_the_same_position_writes_nothing(
    wq: Callable, four_tasks: None, data: Path, git: Git, args: list[str]
) -> None:
    """``wq move`` to where the task is succeeds without writing, even with a reason."""
    files = {p.name: p.read_bytes() for p in (data / "tasks").iterdir()}

    result = wq("move", *args, "--reason", "そのまま")

    task_id = int(args[0])
    assert (result.code, result.out) == (0, f"動かしませんでした: {task_id} {task_id} つ目（{task_id} 番目のまま）\n")
    assert {p.name: p.read_bytes() for p in (data / "tasks").iterdir()} == files
    assert queue_ids(data) == [1, 2, 3, 4]
    assert commit_count(git, data) == 4
    assert git(data, "status", "--porcelain") == ""


def test_move_json_to_the_same_position_prints_from(wq: Callable, four_tasks: None) -> None:
    """``wq move --json`` to the same position prints the same ``from`` and position."""
    output = json.loads(wq("move", "3", "--to", "3", "--json").out)

    assert (output["from"], output["task"]["position"]) == (3, 3)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["1", "--to", "0"], "位置は 1 から 3 までにしてください: 0"),
        (["2", "--to", "4"], "位置は 1 から 3 までにしてください: 4"),
        (["4", "--top"], "タスク 4 はキューにありません"),
        (["99", "--top"], "タスク 99 がありません"),
        (["1", "--before", "99"], "タスク 99 がありません"),
        (["1", "--before", "4"], "タスク 4 はキューにありません"),
        (["2", "--after", "2"], "タスク 2 自身の前後には動かせません"),
        (["1", "--top", "--reason", " "], "理由が空です"),
        (["1", "--top", "--reason", "a\nb"], "理由に改行は入れられません"),
    ],
    ids=[
        "to-zero",
        "to-past-end",
        "done",
        "missing",
        "missing-target",
        "done-target",
        "itself",
        "empty-reason",
        "newline-reason",
    ],
)
def test_move_rejects_an_impossible_move_without_writing(
    wq: Callable, four_tasks: None, data: Path, git: Git, args: list[str], message: str
) -> None:
    """``wq move`` stops with exit code 1 and writes nothing when it cannot move."""
    wq("done", "4")
    queue = (data / "queue.md").read_bytes()

    result = wq("move", *args)

    assert (result.code, result.out, result.err) == (1, "", f"{message}\n")
    assert (data / "queue.md").read_bytes() == queue
    assert commit_count(git, data) == 5
    assert git(data, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "args",
    [["1"], ["1", "--top", "--bottom"], ["1", "--to", "2", "--after", "3"], ["x", "--top"], ["1", "--to", "a"]],
    ids=["no-target", "two-targets", "to-and-after", "bad-id", "bad-position"],
)
def test_move_rejects_bad_arguments_with_exit_code_2(
    wq: Callable, four_tasks: None, data: Path, git: Git, args: list[str]
) -> None:
    """``wq move`` needs exactly one destination and integer IDs (exit code 2)."""
    result = wq("move", *args)

    assert result.code == 2
    assert queue_ids(data) == [1, 2, 3, 4]
    assert commit_count(git, data) == 4
