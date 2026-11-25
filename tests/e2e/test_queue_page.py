"""E2E tests of the queue page: add, drag to reorder, edit, log, done, and a stale save."""

from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from worqueue.store.ops import TaskEdit, edit_task
from worqueue.store.queue import read_queue
from worqueue.store.task import read_task

pytestmark = pytest.mark.e2e


def add_on_page(page: Page, title: str, kind: str = "implement") -> None:
    """Add a task with the add form and wait for its row."""
    page.fill("#add-title", title)
    page.select_option("#add-kind", kind)
    page.click("#add-submit")
    expect(page.locator("#queue tr", has_text=title)).to_have_count(1)


def row(page: Page, task_id: int) -> Locator:
    """Return the locator of a task's row."""
    return page.locator(f'#queue tr[data-id="{task_id}"]')


def test_the_queue_page_adds_reorders_edits_logs_and_completes(page: Page, server: str, data: Path) -> None:
    """Each operation of the page is written to data/ and shown on the page."""
    page.goto(server)
    expect(page.locator("#queue-empty")).to_be_visible()

    add_on_page(page, "一つ目", "manage")
    add_on_page(page, "二つ目")
    expect(page.locator("#ratio")).to_have_text("管理 1（50%） / 実装 1（50%）")

    row(page, 2).drag_to(row(page, 1), target_position={"x": 20, "y": 2})
    expect(page.locator("#queue tr").first).to_have_attribute("data-id", "2")
    assert read_queue(data) == [2, 1]

    row(page, 1).click()
    expect(page.locator("#detail")).to_be_visible()
    page.select_option("#edit-status", "doing")
    page.fill("#edit-reason", "着手")
    page.click("#edit-save")
    expect(page.locator("#history")).to_contain_text("状態 todo → doing: 着手")
    assert read_task(data, 1).status == "doing"

    page.fill("#log-content", "レビューを依頼した")
    page.click("#log-submit")
    expect(page.locator("#history")).to_contain_text("レビューを依頼した")

    page.click("#done-submit")
    expect(page.locator("#detail")).to_be_hidden()
    expect(row(page, 1)).to_have_count(0)
    assert read_task(data, 1).status == "done"
    expect(page.locator("#error")).to_be_hidden()


def test_saving_a_task_changed_after_opening_it_shows_an_error(
    page: Page, server: str, data: Path, now: datetime
) -> None:
    """A file changed after the page read it is not overwritten, and the error bar says so."""
    page.goto(server)
    add_on_page(page, "タスク")
    row(page, 1).click()
    expect(page.locator("#detail")).to_be_visible()
    edit_task(data, 1, TaskEdit(title="CLI で変えた"), None, now)
    after = (data / "tasks" / "1.md").read_bytes()

    page.fill("#edit-title", "画面で変えた")
    page.click("#edit-save")

    expect(page.locator("#error")).to_contain_text("変わりました")
    expect(page.locator("#edit-title")).to_have_value("CLI で変えた")
    assert (data / "tasks" / "1.md").read_bytes() == after


def hold_task_reads(page: Page, task_id: int) -> list[Route]:
    """Hold the page's reads of a task until the test continues them; return the held requests."""
    held: list[Route] = []
    page.route(f"**/api/tasks/{task_id}", lambda route: held.append(route))
    return held


def wait_held(page: Page, held: list[Route]) -> None:
    """Wait until a read is held."""
    for _ in range(100):
        if held:
            return
        page.wait_for_timeout(50)
    raise AssertionError("no read was held")


def test_a_late_read_of_another_task_does_not_replace_the_open_one(page: Page, server: str) -> None:
    """Opening task 2 while task 1 is still being read keeps task 2 and what was typed for it."""
    page.goto(server)
    add_on_page(page, "一つ目")
    add_on_page(page, "二つ目")
    held = hold_task_reads(page, 1)
    row(page, 1).click()
    wait_held(page, held)

    row(page, 2).click()
    expect(page.locator("#detail-title")).to_have_text("2 二つ目")
    page.fill("#edit-title", "入力中")
    held[0].continue_()
    page.wait_for_load_state("networkidle")

    expect(page.locator("#detail-title")).to_have_text("2 二つ目")
    expect(page.locator("#edit-title")).to_have_value("入力中")


def test_a_late_read_does_not_reopen_a_closed_panel(page: Page, server: str) -> None:
    """Closing the panel while a task is being read keeps it closed."""
    page.goto(server)
    add_on_page(page, "一つ目")
    add_on_page(page, "二つ目")
    row(page, 2).click()
    expect(page.locator("#detail")).to_be_visible()
    held = hold_task_reads(page, 1)
    row(page, 1).click()
    wait_held(page, held)

    page.click("#detail-close")
    held[0].continue_()
    page.wait_for_load_state("networkidle")

    expect(page.locator("#detail")).to_be_hidden()
