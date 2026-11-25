"""E2E tests of the kanban board: moves within a column, status changes between columns, done, and the view switch.

Drags are Playwright's synthetic mouse operations (``drag_to``); they do not go through the OS's drag and drop.
"""

from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, Position, Route, expect

from worqueue.store.ops import NewTask, TaskEdit, add_task, edit_task
from worqueue.store.queue import read_queue
from worqueue.store.task import read_task

pytestmark = pytest.mark.e2e


def add(data: Path, now: datetime, *statuses: str) -> None:
    """Create one task per status given, in order (IDs 1, 2, ...)."""
    for number, status in enumerate(statuses, start=1):
        add_task(data, NewTask(title=f"タスク {number}", kind="implement", status=status), now)


def column(page: Page, status: str) -> Locator:
    """Return the locator of the column of a status."""
    return page.locator(f'#board .column[data-status="{status}"]')


def card(page: Page, status: str, task_id: int) -> Locator:
    """Return the locator of a task's card in the column of a status."""
    return column(page, status).locator(f'.card[data-id="{task_id}"]')


def ids_in(page: Page, status: str) -> list[int]:
    """Return the IDs of the cards in a column, from the top."""
    return [int(i) for i in column(page, status).locator(".card").evaluate_all("cards => cards.map(c => c.dataset.id)")]


def lower_half(target: Locator) -> Position:
    """Return a position in the lower half of an element."""
    box = target.bounding_box()
    assert box is not None
    return {"x": 10, "y": box["height"] - 3}


def open_board(page: Page, server: str) -> None:
    """Open the page on the board and wait for it to be drawn."""
    page.goto(f"{server}#kanban")
    expect(page.locator("#board")).to_be_visible()
    page.wait_for_load_state("networkidle")


def test_dropping_on_the_upper_half_of_a_card_puts_the_task_before_it(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """Within a column, a card dropped on another card's upper half goes just before it in the queue."""
    add(data, now, "todo", "todo", "todo")
    open_board(page, server)

    card(page, "todo", 3).drag_to(card(page, "todo", 1), target_position={"x": 10, "y": 3})

    expect(column(page, "todo").locator(".card").first).to_have_attribute("data-id", "3")
    assert ids_in(page, "todo") == [3, 1, 2]
    assert read_queue(data) == [3, 1, 2]
    expect(page.locator("#error")).to_be_hidden()


def test_dropping_below_the_last_card_puts_the_task_after_it(page: Page, server: str, data: Path, now: datetime) -> None:
    """Below the column's last card, the task goes just after it, past a task of another column in between."""
    add(data, now, "todo", "doing", "todo")
    open_board(page, server)

    target = card(page, "todo", 3)
    card(page, "todo", 1).drag_to(target, target_position=lower_half(target))

    expect(column(page, "todo").locator(".card").first).to_have_attribute("data-id", "3")
    assert ids_in(page, "todo") == [3, 1]
    assert read_queue(data) == [2, 3, 1]
    assert [read_task(data, i).status for i in (1, 2, 3)] == ["todo", "doing", "todo"]


def test_dropping_on_another_column_changes_only_the_status(page: Page, server: str, data: Path, now: datetime) -> None:
    """Between columns, the status changes and the queue keeps its order."""
    add(data, now, "todo", "todo")
    open_board(page, server)

    card(page, "todo", 2).drag_to(column(page, "doing"))

    expect(card(page, "doing", 2)).to_have_count(1)
    assert read_task(data, 2).status == "doing"
    assert read_task(data, 2).markdown.endswith("- 2026-11-24 09:10 状態 todo → doing\n")
    assert read_queue(data) == [1, 2]


def test_dropping_on_done_completes_and_dropping_back_puts_it_at_the_bottom(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """Dropping on the done column completes a task; dropping it back reopens it at the bottom of the queue."""
    add(data, now, "todo", "todo")
    open_board(page, server)

    card(page, "todo", 1).drag_to(column(page, "done"))

    expect(card(page, "done", 1)).to_have_count(1)
    assert read_task(data, 1).status == "done"
    assert read_queue(data) == [2]

    card(page, "done", 1).drag_to(column(page, "waiting"))

    expect(card(page, "waiting", 1)).to_have_count(1)
    assert read_task(data, 1).status == "waiting"
    assert read_queue(data) == [2, 1]


def test_a_status_change_of_a_file_changed_after_reading_shows_an_error(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """A task file changed after the board read it is not overwritten; the error bar says so and the board is read again."""
    add(data, now, "todo")
    open_board(page, server)
    edit_task(data, 1, TaskEdit(status="waiting"), None, now)
    after = (data / "tasks" / "1.md").read_bytes()

    card(page, "todo", 1).drag_to(column(page, "doing"))

    expect(page.locator("#error")).to_contain_text("変わりました")
    expect(card(page, "waiting", 1)).to_have_count(1)
    assert (data / "tasks" / "1.md").read_bytes() == after


def test_the_view_is_kept_in_the_hash_and_a_card_opens_the_detail(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """The view buttons switch through the URL's hash, a reload keeps the view, and a card opens the detail."""
    add(data, now, "todo")
    page.goto(server)
    expect(page.locator("#list")).to_be_visible()

    page.click("#view-board")
    expect(page).to_have_url(f"{server}#kanban")
    expect(page.locator("#board")).to_be_visible()
    expect(page.locator("#list")).to_be_hidden()

    page.reload()
    expect(page.locator("#board")).to_be_visible()
    expect(page.locator("#list")).to_be_hidden()
    card(page, "todo", 1).click()
    expect(page.locator("#detail")).to_be_visible()

    page.click("#view-list")
    expect(page.locator("#list")).to_be_visible()
    expect(page.locator("#board")).to_be_hidden()


def test_a_drop_on_a_board_being_read_again_uses_the_versions_of_the_cards_shown(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """While the board is read again, a drop on its old cards carries their versions, not those read later."""
    add(data, now, "todo")
    open_board(page, server)
    edit_task(data, 1, TaskEdit(status="waiting"), None, now)
    after = (data / "tasks" / "1.md").read_bytes()
    page.click("#view-list")  # reads the queue again, with the new version of task 1
    expect(page.locator("#queue tr").first).to_contain_text("waiting")
    held: list[Route] = []
    page.route("**/api/queue", lambda route: held.append(route))

    page.click("#view-board")
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the board's read of the queue was not held"
    card(page, "todo", 1).drag_to(column(page, "doing"))

    expect(page.locator("#error")).to_contain_text("変わりました")
    assert (data / "tasks" / "1.md").read_bytes() == after
    page.unroute("**/api/queue")  # lets the held reads go on
