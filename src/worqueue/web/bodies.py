"""Bodies of the Web UI's write requests, and how they become the data layer's inputs."""

from dataclasses import replace
from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from worqueue.store.ops import NewTask, TaskEdit

_NOT_NULL_EDIT_FIELDS = ("title", "status", "kind", "assignee", "depends_on", "body", "reason")


class _Body(BaseModel):
    """A request body: unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")


class NewTaskBody(_Body):
    """``POST /api/tasks``: the task to create, as ``wq add`` takes it."""

    title: str
    kind: str
    assignee: str = "me"
    due: date | None = None
    depends_on: list[int] = []
    status: str = "todo"
    body: str = ""

    def to_new_task(self) -> NewTask:
        """Return the task for ``add_task``.

        Returns
        -------
        NewTask
            The same values.
        """
        return NewTask(
            title=self.title,
            kind=self.kind,
            assignee=self.assignee,
            due=self.due,
            depends_on=tuple(self.depends_on),
            status=self.status,
            body=self.body,
        )


class EditBody(_Body):
    """``PATCH /api/tasks/{id}``: the fields to change. A field left out keeps its value.

    ``due`` may be null (remove the due date); the other fields may not.
    ``depends_on`` is the whole new list of dependencies.
    """

    version: str
    title: str | None = None
    status: str | None = None
    kind: str | None = None
    assignee: str | None = None
    due: date | None = None
    depends_on: list[int] | None = None
    body: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _refuse_nulls(self) -> Self:
        """Refuse null for a field given, except ``due``."""
        nulls = [name for name in _NOT_NULL_EDIT_FIELDS if name in self.model_fields_set and getattr(self, name) is None]
        if nulls:
            raise ValueError(f"null にできない項目です: {', '.join(nulls)}")
        return self

    def to_edit(self, current_depends_on: tuple[int, ...]) -> TaskEdit:
        """Return the edit for ``edit_task``.

        Parameters
        ----------
        current_depends_on : tuple of int
            The task's dependencies now, to turn the new list into IDs to add and remove.

        Returns
        -------
        TaskEdit
            The fields given, with ``due: null`` as ``clear_due`` and ``depends_on`` as
            the IDs to add (in the given order) and remove, or ``clear_depends_on`` for
            an empty list.
        """
        edit = TaskEdit(
            title=self.title,
            status=self.status,
            kind=self.kind,
            assignee=self.assignee,
            due=self.due,
            clear_due="due" in self.model_fields_set and self.due is None,
            body=self.body,
        )
        if self.depends_on is None:
            return edit
        if not self.depends_on:
            return replace(edit, clear_depends_on=True)
        return replace(
            edit,
            add_depends_on=tuple(i for i in self.depends_on if i not in current_depends_on),
            remove_depends_on=tuple(i for i in current_depends_on if i not in self.depends_on),
        )


class LogBody(_Body):
    """``POST /api/tasks/{id}/log``: one history entry."""

    version: str
    content: str


class DoneBody(_Body):
    """``POST /api/tasks/{id}/done``: why the task is done, if given."""

    version: str
    reason: str | None = None


class MoveBody(_Body):
    """``POST /api/tasks/{id}/move``: the task to put it before, or null for the bottom.

    ``version`` is the version of ``queue.md`` from ``GET /api/queue``.
    """

    version: str
    before: int | None
