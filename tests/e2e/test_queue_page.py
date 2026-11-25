"""E2E tests of the queue page: add, drag to reorder, edit, log, done, and a stale save."""

from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

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
