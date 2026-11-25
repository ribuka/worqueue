"""Bodies of the Web UI's write requests, and how they become the data layer's inputs."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from worqueue.store.ops import NewTask, TaskEdit
from worqueue.store.task import MY_ASSIGNEE

_NOT_NULL_EDIT_FIELDS = ("title", "status", "kind", "assignee", "depends_on", "body", "reason")


class _Body(BaseModel):
    """A request body: unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")


class NewTaskBody(_Body):
    """``POST /api/tasks``: the task to create, as ``wq add`` takes it."""

    title: str
    kind: str
    assignee: str = MY_ASSIGNEE
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

    def to_edit(self) -> TaskEdit:
        """Return the edit for ``edit_task``.

        Returns
        -------
        TaskEdit
            The fields given, with ``due: null`` as ``clear_due``. ``depends_on`` is
            passed whole: ``edit_task`` resolves it against the file it reads under
            the lock, after checking the version.
        """
        return TaskEdit(
            title=self.title,
            status=self.status,
            kind=self.kind,
            assignee=self.assignee,
            due=self.due,
            clear_due="due" in self.model_fields_set and self.due is None,
            depends_on=None if self.depends_on is None else tuple(self.depends_on),
            body=self.body,
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
