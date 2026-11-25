"""Tests of the direction of imports between packages."""

import ast
from pathlib import Path

import pytest

import worqueue

PACKAGE_DIR = Path(worqueue.__file__).parent


def imported_modules(path: Path) -> list[str]:
    """Return the absolute names a source file imports, with ``from x import y`` as ``x.y``."""
    package = ["worqueue", *path.relative_to(PACKAGE_DIR).parent.parts]
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join([*base, *([node.module] if node.module else [])])
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("package", ["store", "web"])
def test_package_does_not_import_cli(package: str) -> None:
    """``worqueue.store`` and ``worqueue.web`` do not import ``worqueue.cli``."""
    sources = sorted((PACKAGE_DIR / package).rglob("*.py"))
    assert sources

    offending = {
        str(path.relative_to(PACKAGE_DIR)): name
        for path in sources
        for name in imported_modules(path)
        if name == "worqueue.cli" or name.startswith("worqueue.cli.")
    }
    assert offending == {}

