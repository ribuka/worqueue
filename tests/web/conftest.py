"""Setup for Web UI server tests: a client of the app on the temporary data/."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from worqueue.web.app import create_app


@pytest.fixture
def client(data: Path, now: datetime) -> Iterator[TestClient]:
    """Return a client of the app on ``data`` with the clock fixed at ``now``, as from 127.0.0.1."""
    with TestClient(create_app(data, lambda: now), base_url="http://127.0.0.1") as client:
        yield client
