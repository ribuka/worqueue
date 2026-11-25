"""Tests of the Web UI's API: the JSON it returns and the writes it makes."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worqueue.store.ops import TaskEdit, edit_task
from worqueue.store.queue import read_queue, write_queue
from worqueue.store.task import read_task
from worqueue.store.versions import file_version

Git = Callable[..., str]


def add(client: TestClient, title: str, **fields: object) -> int:
    """Create a task through the API and return its ID."""
    response = client.post("/api/tasks", json={"title": title, "kind": "implement", **fields})
    assert response.status_code == 201, response.text
    return response.json()["task"]["id"]


def version_of(client: TestClient, task_id: int) -> str:
    """Return the version of a task's file as ``GET /api/tasks/{id}`` gives it."""
    return client.get(f"/api/tasks/{task_id}").json()["version"]


def commit_count(git: Git, repo: Path) -> int:
    """Return the number of commits on HEAD."""
    return int(git(repo, "rev-list", "--count", "HEAD"))


def test_the_page_and_its_files_are_served(client: TestClient) -> None:
    """``/`` is the page and ``/static`` has its modules."""
    page = client.get("/")
    assert page.status_code == 200
    assert "Worqueue" in page.text
    assert client.get("/static/js/app.js").status_code == 200


def test_the_queue_of_a_new_data_is_empty(client: TestClient, data: Path) -> None:
    """Without data/, the queue is empty with the version of a missing ``queue.md``, and nothing is created."""
    assert client.get("/api/queue").json() == {"tasks": [], "version": "none"}
    assert not data.exists()


def test_adding_a_task_commits_it_and_shows_it_in_the_queue(client: TestClient, data: Path, git: Git) -> None:
    """``POST /api/tasks`` answers 201 with the task, as ``wq add --json``, and commits it."""
    add(client, "一つ目")
    response = client.post(
        "/api/tasks",
        json={"title": "二つ目", "kind": "manage", "assignee": "佐藤", "due": "2026-11-27", "depends_on": [1]},
    )

    assert response.status_code == 201
    task = response.json()["task"]
    assert task == {
        "id": 2,
        "position": 2,
        "title": "二つ目",
        "status": "todo",
        "kind": "manage",
        "assignee": "佐藤",
        "due": "2026-11-27",
        "depends_on": [1],
        "created": task["created"],
    }
    queue = client.get("/api/queue").json()
    assert [t["id"] for t in queue["tasks"]] == [1, 2]
    assert queue["version"] == file_version(data / "queue.md")
    assert commit_count(git, data) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"title": "a"},
        {"title": "a", "kind": "manage", "due": "2026-11-31"},
        {"title": "a", "kind": "manage", "unknown": 1},
    ],
    ids=["no-kind", "bad-due", "unknown-key"],
)
def test_adding_a_malformed_task_is_422(client: TestClient, data: Path, body: dict) -> None:
    """A body of the wrong shape is answered with 422 and writes nothing."""
    assert client.post("/api/tasks", json=body).status_code == 422
    assert not data.exists()


def test_adding_an_invalid_task_is_400_with_the_message(client: TestClient) -> None:
    """A value the data layer refuses is answered with 400 and its message."""
    response = client.post("/api/tasks", json={"title": "  ", "kind": "manage"})

    assert response.status_code == 400
    assert response.json() == {"error": "タイトルが空です"}


def test_a_task_has_its_markdown_body_and_version(client: TestClient, data: Path) -> None:
    """``GET /api/tasks/{id}`` gives the task as ``wq show --json``, its body, and its file's version."""
    add(client, "タスク", body="本文の行")

    response = client.get("/api/tasks/1").json()

    assert response["task"]["id"] == 1
    assert response["task"]["position"] == 1
    assert response["task"]["markdown"] == "本文の行\n\n## 履歴\n\n- 2026-11-24 09:10 作成"
    assert response["body"] == "本文の行"
    assert response["version"] == file_version(data / "tasks" / "1.md")


def test_a_missing_task_is_400(client: TestClient) -> None:
    """A task that does not exist is answered with 400 and the message of the data layer."""
    response = client.get("/api/tasks/9")

    assert response.status_code == 400
    assert response.json() == {"error": "タスク 9 がありません"}


def test_editing_changes_only_the_fields_given(client: TestClient, data: Path, git: Git) -> None:
    """``PATCH`` changes the fields given, keeps the others, and answers as ``wq edit --json``."""
    add(client, "タスク", assignee="佐藤", due="2026-11-27", body="本文")

    response = client.patch(
        "/api/tasks/1", json={"version": version_of(client, 1), "status": "doing", "due": None, "reason": "着手"}
    )

    assert response.status_code == 200
    assert response.json()["changed"] == ["status", "due"]
    assert response.json()["task"]["status"] == "doing"
    task = read_task(data, 1)
    assert (task.assignee, task.due, task.title) == ("佐藤", None, "タスク")
    assert task.markdown.endswith("- 2026-11-24 09:10 状態 todo → doing、期限 2026-11-27 → なし: 着手\n")
    assert commit_count(git, data) == 2


def test_editing_to_the_same_values_writes_nothing(client: TestClient, data: Path, git: Git) -> None:
    """Sending the current values changes nothing and commits nothing."""
    add(client, "タスク", body="本文")

    response = client.patch(
        "/api/tasks/1", json={"version": version_of(client, 1), "title": "タスク", "body": "本文", "depends_on": []}
    )

    assert response.json()["changed"] == []
    assert commit_count(git, data) == 1


@pytest.mark.parametrize(
    ("given", "expected"),
    [([3, 4], (3, 4)), ([4, 2], (2, 4)), ([], ())],
    ids=["replace", "keep-order-then-add", "clear"],
)
def test_editing_the_dependencies_takes_the_whole_list(
    client: TestClient, data: Path, given: list[int], expected: tuple[int, ...]
) -> None:
    """``depends_on`` is the new list: kept IDs stay in their order, new ones follow."""
    for title in ("a", "b", "c", "d"):
        add(client, title)
    add(client, "e", depends_on=[2, 3])

    response = client.patch("/api/tasks/5", json={"version": version_of(client, 5), "depends_on": given})

    assert response.status_code == 200, response.text
    assert read_task(data, 5).depends_on == expected


def test_editing_keeps_a_dependency_whose_file_is_gone(client: TestClient, data: Path) -> None:
    """A kept dependency is not checked again, so a task deleted by hand can stay or be removed."""
    add(client, "a")
    add(client, "b")
    add(client, "c", depends_on=[1, 2])
    (data / "tasks" / "1.md").unlink()
    write_queue(data, [2, 3])

    response = client.patch("/api/tasks/3", json={"version": version_of(client, 3), "depends_on": [2]})

    assert response.status_code == 200, response.text
    assert read_task(data, 3).depends_on == (2,)


@pytest.mark.parametrize(
    "body",
    [{"title": None}, {"depends_on": None}, {"reason": None}, {"due": "soon"}, {"unknown": 1}, {}],
    ids=["null-title", "null-depends-on", "null-reason", "bad-due", "unknown-key", "no-version"],
)
def test_editing_with_a_malformed_body_is_422(client: TestClient, data: Path, body: dict) -> None:
    """A null where it is not allowed, a bad date, an unknown key, or no version is 422."""
    add(client, "タスク")
    before = (data / "tasks" / "1.md").read_bytes()
    version = {} if body == {} else {"version": version_of(client, 1)}

    assert client.patch("/api/tasks/1", json={**version, **body}).status_code == 422
    assert (data / "tasks" / "1.md").read_bytes() == before


def test_editing_to_done_is_400(client: TestClient) -> None:
    """``done`` is not a status to edit to (``done`` has its own route)."""
    add(client, "タスク")

    response = client.patch("/api/tasks/1", json={"version": version_of(client, 1), "status": "done"})

    assert response.status_code == 400
    assert "状態は todo, doing, waiting のどれか" in response.json()["error"]


def test_editing_a_file_changed_after_reading_is_409(client: TestClient, data: Path, now: datetime, git: Git) -> None:
    """A version read before another writer changed the file is answered with 409 and writes nothing."""
    add(client, "タスク")
    version = version_of(client, 1)
    edit_task(data, 1, TaskEdit(title="CLI で変えた"), None, now)
    after = (data / "tasks" / "1.md").read_bytes()

    response = client.patch("/api/tasks/1", json={"version": version, "title": "画面で変えた"})

    assert response.status_code == 409
    assert response.json() == {"error": "tasks/1.md は画面を読み込んだ後に変わりました。読み込み直してください"}
    assert (data / "tasks" / "1.md").read_bytes() == after
    assert commit_count(git, data) == 2


@pytest.mark.parametrize(("path", "body"), [("log", {"content": "内容"}), ("done", {})])
def test_log_and_done_refuse_a_stale_version(
    client: TestClient, data: Path, now: datetime, path: str, body: dict
) -> None:
    """``log`` and ``done`` check the task file's version too."""
    add(client, "タスク")
    version = version_of(client, 1)
    edit_task(data, 1, TaskEdit(title="CLI で変えた"), None, now)

    assert client.post(f"/api/tasks/1/{path}", json={"version": version, **body}).status_code == 409


def test_logging_adds_a_history_entry(client: TestClient, data: Path) -> None:
    """``log`` adds the entry and answers the task with its position."""
    add(client, "タスク")

    response = client.post("/api/tasks/1/log", json={"version": version_of(client, 1), "content": "佐藤さんに確認"})

    assert response.status_code == 200
    assert response.json()["task"]["position"] == 1
    assert read_task(data, 1).markdown.endswith("- 2026-11-24 09:10 佐藤さんに確認\n")


def test_done_takes_the_task_out_of_the_queue(client: TestClient, data: Path) -> None:
    """``done`` marks the task done with the reason and answers it without a position."""
    add(client, "a")
    add(client, "b")

    response = client.post("/api/tasks/1/done", json={"version": version_of(client, 1), "reason": "不要になった"})

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "done"
    assert response.json()["task"]["position"] is None
    assert read_queue(data) == [2]
    assert read_task(data, 1).markdown.endswith("- 2026-11-24 09:10 完了: 不要になった\n")


@pytest.mark.parametrize(
    ("task_id", "before", "order", "start", "end"),
    [(3, 1, [3, 1, 2], 3, 1), (1, 3, [2, 1, 3], 1, 2), (1, None, [2, 3, 1], 1, 3)],
    ids=["up", "down", "bottom"],
)
def test_moving_puts_the_task_before_another_or_at_the_bottom(
    client: TestClient, data: Path, task_id: int, before: int | None, order: list[int], start: int, end: int
) -> None:
    """``move`` puts the task before ``before``, or at the bottom for null, and answers as ``wq move --json``."""
    for title in ("a", "b", "c"):
        add(client, title)
    version = client.get("/api/queue").json()["version"]

    response = client.post(f"/api/tasks/{task_id}/move", json={"version": version, "before": before})

    assert response.status_code == 200, response.text
    assert response.json()["from"] == start
    assert response.json()["task"]["position"] == end
    assert read_queue(data) == order


def test_moving_needs_before_even_when_null(client: TestClient) -> None:
    """``before`` must be given; null is the bottom, a missing key is 422."""
    add(client, "a")
    version = client.get("/api/queue").json()["version"]

    assert client.post("/api/tasks/1/move", json={"version": version}).status_code == 422


def test_moving_with_a_queue_changed_after_reading_is_409(client: TestClient, data: Path) -> None:
    """A version of ``queue.md`` read before it changed is answered with 409."""
    for title in ("a", "b", "c"):
        add(client, title)
    version = client.get("/api/queue").json()["version"]
    add(client, "d")

    response = client.post("/api/tasks/1/move", json={"version": version, "before": None})

    assert response.status_code == 409
    assert response.json()["error"].startswith("queue.md は画面を読み込んだ後に変わりました")
    assert read_queue(data) == [1, 2, 3, 4]


def test_moving_before_itself_is_400(client: TestClient) -> None:
    """Moving a task before itself is refused by the data layer."""
    add(client, "a")
    add(client, "b")
    version = client.get("/api/queue").json()["version"]

    assert client.post("/api/tasks/1/move", json={"version": version, "before": 1}).status_code == 400
