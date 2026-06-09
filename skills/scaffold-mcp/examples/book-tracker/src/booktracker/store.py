"""Persistence — the ONLY module that touches the filesystem.

Two locations, deliberately separate:

- the **bundled seed** (`data/booktracker.seed.json`) ships in the repo,
  read-only, so the project clones-and-runs with a realistic, already-populated
  library plus a reading goal;
- **mutable state** (`state.json`: books you've added, status changes, goals you
  set, exported reports) lives in a user data dir (BOOKTRACKER_DATA_DIR, default
  ~/.book-tracker) and is gitignored — a reviewer's experiments never dirty the
  repo, and real data never lands in a public commit.

The seed is immutable, so a status change to a *seed* book can't edit the seed
file; instead `mark_status` records an override in state, and `load_books`
overlays it. Keeping all I/O in this one module is what lets every other module
stay pure and unit-testable without a runtime.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from pathlib import Path

from .models import STATUSES, Book

_PKG_ROOT = Path(__file__).resolve().parents[2]  # repo root when run from a clone


def seed_path() -> Path:
    return Path(os.environ.get("BOOKTRACKER_SEED", _PKG_ROOT / "data" / "booktracker.seed.json"))


def data_dir() -> Path:
    d = Path(os.environ.get("BOOKTRACKER_DATA_DIR", Path.home() / ".book-tracker"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path() -> Path:
    return data_dir() / "state.json"


# ── Seed (read-only) ─────────────────────────────────────────────────

def _load_seed() -> dict:
    return json.loads(seed_path().read_text())


# ── State (mutable) ──────────────────────────────────────────────────

def load_state() -> dict:
    p = state_path()
    if not p.exists():
        return {"books": [], "status_overrides": {}, "goals": {}, "exports": [], "settings": {}}
    state = json.loads(p.read_text())
    state.setdefault("books", [])
    state.setdefault("status_overrides", {})
    state.setdefault("goals", {})
    state.setdefault("exports", [])
    state.setdefault("settings", {})
    return state


def save_state(state: dict) -> None:
    state_path().write_text(json.dumps(state, indent=2))


# ── Books (bundled seed + your added books, with status overlays) ─────

def _show_seed(state: dict) -> bool:
    """Whether the bundled sample library is currently included (default yes)."""
    return state.get("settings", {}).get("show_seed", True)


def load_books() -> list[Book]:
    """Your books, with any `mark_status` overrides applied — the single read path
    every tool grounds itself in. Includes the bundled sample library unless you've
    turned it off (set_show_seed / reset_library)."""
    state = load_state()
    books: list[Book] = []
    if _show_seed(state):
        books += [Book.from_dict(b) for b in _load_seed().get("books", [])]
    books += [Book.from_dict(b) for b in state.get("books", [])]
    overrides = state.get("status_overrides", {})
    if overrides:
        books = [
            dataclasses.replace(b, status=overrides[b.id]) if b.id in overrides else b
            for b in books
        ]
    return books


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "book"


def _dedupe_key(title: str, author: str) -> str:
    return f"{title.strip().lower()}|{author.strip().lower()}"


def existing_ids() -> set[str]:
    return {b.id for b in load_books()}


def existing_keys() -> set[str]:
    return {_dedupe_key(b.title, b.author) for b in load_books()}


def unique_id(title: str, taken: set[str] | None = None) -> str:
    """A slug not already taken by a seed or added book."""
    taken = taken if taken is not None else existing_ids()
    base = _slug(title)
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def add_book(book: Book) -> str:
    """Append one book to mutable state. Returns its id."""
    state = load_state()
    state["books"].append(book.to_dict())
    save_state(state)
    return book.id


def add_books(rows: list[dict]) -> dict:
    """Bulk-add books, skipping any that duplicate an existing title+author. This
    is the single sink every import mode funnels into — natural language, a
    photographed shelf (Claude's vision extracts the rows), or a pasted Goodreads
    export. Returns the ids added and the titles skipped as duplicates."""
    state = load_state()
    taken_ids = existing_ids()
    taken_keys = existing_keys()
    added: list[str] = []
    skipped: list[str] = []
    for row in rows:
        title = (row.get("title") or "").strip()
        author = (row.get("author") or "").strip()
        if not title:
            continue
        key = _dedupe_key(title, author)
        if key in taken_keys:
            skipped.append(title)
            continue
        rid = unique_id(title, taken_ids)
        taken_ids.add(rid)
        taken_keys.add(key)
        book = Book.from_dict({**row, "id": rid, "title": title, "author": author})
        state["books"].append(book.to_dict())
        added.append(rid)
    save_state(state)
    return {"added": added, "skipped_duplicates": skipped}


def mark_status(book_id: str, status: str) -> bool:
    """Record a status change for a book (seed or added) as a state overlay.
    Returns False if the id isn't known or the status is invalid."""
    if status not in STATUSES or book_id not in existing_ids():
        return False
    state = load_state()
    state["status_overrides"][book_id] = status
    save_state(state)
    return True


# ── Goals (seed defaults, overridable in state) ──────────────────────

def get_goal(year: int) -> int | None:
    """The reading goal for a year — a goal you set wins; the seed default applies
    only while the sample library is shown."""
    state = load_state()
    state_goals = state.get("goals", {})
    if str(year) in state_goals:
        return int(state_goals[str(year)])
    if _show_seed(state):
        seed_goals = _load_seed().get("goals", {})
        if str(year) in seed_goals:
            return int(seed_goals[str(year)])
    return None


def set_goal(year: int, goal: int) -> None:
    state = load_state()
    state["goals"][str(year)] = int(goal)
    save_state(state)


# ── Library lifecycle (adopt it for your own reading) ────────────────

def set_show_seed(enabled: bool) -> None:
    """Show or hide the bundled sample library — reversible, non-destructive."""
    state = load_state()
    state.setdefault("settings", {})["show_seed"] = bool(enabled)
    save_state(state)


def reset_library() -> dict:
    """Empty your library for real use: hide the bundled samples AND clear
    everything you've added (books, status changes, goals, exports). Reversible
    for the samples via set_show_seed(True). Returns what was cleared."""
    state = load_state()
    cleared = {
        "books": len(state.get("books", [])),
        "status_changes": len(state.get("status_overrides", {})),
        "goals": len(state.get("goals", {})),
    }
    save_state({"books": [], "status_overrides": {}, "goals": {}, "exports": [],
                "settings": {"show_seed": False}})
    return cleared


# ── Exports (durable artifacts) ──────────────────────────────────────

def record_export(title: str, content: str) -> None:
    state = load_state()
    state["exports"].append({"title": title, "content": content})
    save_state(state)


def export_default_path(name: str, ext: str = "md") -> Path:
    """Where export writes when no path is given: a KNOWN location under the data
    dir (not the process cwd, which is unpredictable when a desktop client
    launches the server). Creates the dir."""
    d = data_dir() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.{ext}"
