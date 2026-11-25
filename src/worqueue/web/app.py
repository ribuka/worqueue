"""The Web UI's server: its routes on the data layer, the static page, and error responses.

Every write goes through ``worqueue.store.ops`` (one operation, one commit), with the
version of the file the page read, so a file changed after the page read it is not
overwritten (409).
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from worqueue.store.errors import StaleError, WorqueueError
from worqueue.store.ops import (
    MoveTarget,
    add_task,
    done_task,
    edit_task,
    list_queue,
    log_task,
    move_task,
    show_task,
)
from worqueue.store.queue import QUEUE_FILE
from worqueue.store.task import body_of, task_path
from worqueue.store.versions import FileVersion, file_version
from worqueue.web.bodies import DoneBody, EditBody, LogBody, MoveBody, NewTaskBody
from worqueue.web.guard import RequestGuard

STATIC = Path(__file__).parent / "static"


def create_app(data: Path, now: Callable[[], datetime]) -> FastAPI:
    """Return the Web UI's application for a data/ directory.

    Parameters
    ----------
    data : Path
        The data/ directory. It may not exist yet.
    now : Callable[[], datetime]
        Returns the current time for the history entries of writes.

    Returns
    -------
    FastAPI
        The application, with the page at ``/``, its files at ``/static``, and the
        API at ``/api``.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestGuard)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.add_exception_handler(StaleError, _error_response(409))
    app.add_exception_handler(WorqueueError, _error_response(400))

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    _add_read_routes(app, data)
    _add_write_routes(app, data, now)
    return app


def _add_read_routes(app: FastAPI, data: Path) -> None:
    """Add the routes that read: the queue and one task."""

    @app.get("/api/queue")
    def queue() -> dict:
        # The version is read first: a change in between makes it stale, never newer.
        version = file_version(data / QUEUE_FILE)
        tasks = list_queue(data)
        return {"tasks": [task.summary(i) for i, task in enumerate(tasks, start=1)], "version": version}

    @app.get("/api/tasks/{task_id}")
    def task(task_id: int) -> dict:
        version = file_version(task_path(data, task_id))
        found, position = show_task(data, task_id)
        return {
            "task": {**found.summary(position), "markdown": found.markdown.strip("\n")},
            "body": body_of(found.markdown),
            "version": version,
        }


def _add_write_routes(app: FastAPI, data: Path, now: Callable[[], datetime]) -> None:
    """Add the routes that write: add, edit, log, done, and move."""

    def task_file(task_id: int, version: str) -> tuple[FileVersion, ...]:
        return (FileVersion(task_path(data, task_id), version),)

    @app.post("/api/tasks", status_code=201)
    def add(body: NewTaskBody) -> dict:
        created, position = add_task(data, body.to_new_task(), now())
        return {"task": created.summary(position)}

    @app.patch("/api/tasks/{task_id}")
    def edit(task_id: int, body: EditBody) -> dict:
        current, _ = show_task(data, task_id)
        edit = body.to_edit(current.depends_on)
        result = edit_task(data, task_id, edit, body.reason, now(), expected=task_file(task_id, body.version))
        return {"task": result.task.summary(result.position), "changed": list(result.changed)}

    @app.post("/api/tasks/{task_id}/log")
    def log(task_id: int, body: LogBody) -> dict:
        logged, position = log_task(data, task_id, body.content, now(), expected=task_file(task_id, body.version))
        return {"task": logged.summary(position)}

    @app.post("/api/tasks/{task_id}/done")
    def done(task_id: int, body: DoneBody) -> dict:
        finished = done_task(data, task_id, body.reason, now(), expected=task_file(task_id, body.version))
        return {"task": finished.summary(None)}

    @app.post("/api/tasks/{task_id}/move")
    def move(task_id: int, body: MoveBody) -> dict:
        target = MoveTarget("bottom") if body.before is None else MoveTarget("before", body.before)
        expected = (FileVersion(data / QUEUE_FILE, body.version),)
        moved, start, end = move_task(data, task_id, target, None, now(), expected=expected)
        return {"task": moved.summary(end), "from": start}


def _error_response(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
    """Return an exception handler that answers ``{"error": <message>}`` with ``status_code``."""

    def handle(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=status_code)

    return handle
