"""E2E setup: the Web UI's server on a free port of 127.0.0.1, over the temporary data/."""

import threading
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
import uvicorn

from worqueue.web.app import create_app

START_TIMEOUT_SECONDS = 10


@pytest.fixture
def server(data: Path, now: datetime) -> Iterator[str]:
    """Serve the app on ``data`` in a thread until the test ends, and return its URL."""
    config = uvicorn.Config(create_app(data, lambda: now), host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the Web UI's server did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(START_TIMEOUT_SECONDS)
