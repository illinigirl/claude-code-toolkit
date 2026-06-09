"""Test fixtures + import-path setup.

Puts `src/` on the path so tests can `from booktracker import ...` without an
editable install — keeping the zero-setup goal: the pure-core tests run on stdlib
alone (no `pip install` needed; that's only for the MCP server itself).
"""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from booktracker.models import Book  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_SEED = _ROOT / "data" / "booktracker.seed.json"


@pytest.fixture
def books() -> list[Book]:
    """The bundled seed library, as Book objects."""
    raw = json.loads(_SEED.read_text())
    return [Book.from_dict(b) for b in raw["books"]]


@pytest.fixture
def goodreads_csv() -> str:
    """A small real-shape Goodreads export for the importer test."""
    return (_ROOT / "tests" / "fixtures" / "goodreads_sample.csv").read_text()
