"""Persistence — the ONLY module that touches the filesystem.

Two locations, deliberately separate:

- the **bundled seed** (`src/booktracker/data/booktracker.seed.json`) ships
  *inside the package*, read-only, so the project runs with a realistic,
  already-populated library plus a reading goal — from a clone, an editable
  install, or a built wheel alike;
- **mutable state** (`state.json`: books you've added, status changes, goals you
  set, exported reports) lives in a user data dir (BOOKTRACKER_DATA_DIR, default
  ~/.book-tracker) and is gitignored — a reviewer's experiments never dirty the
  repo, and real data never lands in a public commit.

The seed is immutable, so an edit to a *seed* book can't write the seed file.
Instead we use **copy-on-write**: the first edit of a seed book copies the whole
record into mutable state under the same id, and `load_books` lets your copy win.
Deleting a seed book records a tombstone (`hidden_ids`) the loader filters out.
One overlay mechanism for every mutation — `mark_status` is just `update_book`
changing the status (and stamping `finished` when a book becomes read).
Keeping all I/O in this one module is what lets every
other module stay pure and unit-testable without a runtime.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from datetime import date
from importlib import resources
from pathlib import Path

from .models import STATUSES, Book, validate_book_fields


def data_dir() -> Path:
    d = Path(os.environ.get("BOOKTRACKER_DATA_DIR", Path.home() / ".book-tracker"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path() -> Path:
    return data_dir() / "state.json"


# ── Seed (read-only) ─────────────────────────────────────────────────

def _load_seed() -> dict:
    """The bundled sample library. Resolved via importlib.resources because the
    seed ships inside the package — a path computed from __file__ only works in
    a src-layout checkout and breaks under a non-editable install, where the
    module lands in site-packages. BOOKTRACKER_SEED overrides with a file path."""
    override = os.environ.get("BOOKTRACKER_SEED")
    if override:
        return json.loads(Path(override).read_text())
    seed = resources.files(__package__) / "data" / "booktracker.seed.json"
    return json.loads(seed.read_text())


# ── State (mutable) ──────────────────────────────────────────────────

def _empty_state() -> dict:
    return {"books": [], "hidden_ids": [], "goals": {}, "exports": [], "settings": {}}


def load_state() -> dict:
    p = state_path()
    if not p.exists():
        return _empty_state()
    try:
        state = json.loads(p.read_text())
    except json.JSONDecodeError:
        # A truncated or hand-edited state file must not brick every tool —
        # but silently resetting would destroy the user's library. Fail soft:
        # move the corrupt file aside (preserved for recovery) and continue
        # with fresh state.
        p.replace(p.with_suffix(".json.corrupt"))
        return _empty_state()
    # Legacy state (pre copy-on-write) carried per-book status_overrides; it's
    # ignored now — the demo always runs against a fresh data dir, so there are
    # no real upgrades to migrate. Dropped silently rather than crash on it.
    state.pop("status_overrides", None)
    state.setdefault("books", [])
    state.setdefault("hidden_ids", [])
    state.setdefault("goals", {})
    state.setdefault("exports", [])
    state.setdefault("settings", {})
    return state


def save_state(state: dict) -> None:
    """Write-then-rename so a crash mid-write can't corrupt state.json
    (os.replace is atomic on the same filesystem)."""
    p = state_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, p)


# ── Books (bundled seed + your added books, with status overlays) ─────

def _show_seed(state: dict) -> bool:
    """Whether the bundled sample library is currently included (default yes)."""
    return state.get("settings", {}).get("show_seed", True)


def load_books() -> list[Book]:
    """Your books — the single read path every tool grounds itself in. Applies the
    copy-on-write overlay: where you've edited a seed book, your state copy wins;
    deleted books (tombstoned in `hidden_ids`) are filtered out. Includes the
    bundled sample library unless you've turned it off (set_show_seed / reset)."""
    state = load_state()
    seed_raw = _load_seed().get("books", [])
    seed_ids = {b["id"] for b in seed_raw}
    state_by_id = {b["id"]: b for b in state.get("books", [])}
    hidden = set(state.get("hidden_ids", []))
    books: list[Book] = []
    if _show_seed(state):
        # Seed books in seed order, but your edited copy wins where one exists.
        books += [Book.from_dict(state_by_id.get(b["id"], b)) for b in seed_raw]
    # Books you added that aren't edits of a seed book (those are folded in above).
    books += [Book.from_dict(b) for b in state.get("books", []) if b["id"] not in seed_ids]
    return [b for b in books if b.id not in hidden]


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "book"


def _dedupe_key(title: str, author: str) -> str:
    return f"{title.strip().lower()}|{author.strip().lower()}"


def existing_ids() -> set[str]:
    return {b.id for b in load_books()}


def existing_keys() -> set[str]:
    return {_dedupe_key(b.title, b.author) for b in load_books()}


def taken_ids() -> set[str]:
    """Ids unavailable for a new book: visible books AND tombstoned (deleted) seed
    ids. Including the tombstones means re-adding a deleted title gets a fresh id
    instead of colliding with the hidden one — which the loader would otherwise
    filter straight back out."""
    return existing_ids() | set(load_state().get("hidden_ids", []))


def unique_id(title: str, taken: set[str] | None = None) -> str:
    """A slug not already taken by a seed, added, or deleted book."""
    taken = taken if taken is not None else taken_ids()
    base = _slug(title)
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def add_books(rows: list[dict]) -> dict:
    """Bulk-add books, validating each row and skipping any that duplicate an
    existing title+author. This is the single sink EVERY ingest path funnels
    into — a single add, natural language, a photographed shelf (Claude's vision
    extracts the rows), or a pasted Goodreads export — so validation and dedupe
    are decided once, here, not per-adapter. Returns the ids added, the titles
    skipped as duplicates, and any rows skipped as invalid (with why)."""
    state = load_state()
    taken = taken_ids()
    taken_keys = existing_keys()
    added: list[str] = []
    skipped: list[str] = []
    invalid: list[dict] = []
    for row in rows:
        title = (row.get("title") or "").strip()
        author = (row.get("author") or "").strip()
        if not title:
            continue
        err = validate_book_fields(status=row.get("status"), rating=row.get("rating"))
        if err:
            invalid.append({"title": title, "error": err})
            continue
        key = _dedupe_key(title, author)
        if key in taken_keys:
            skipped.append(title)
            continue
        rid = unique_id(title, taken)
        taken.add(rid)
        taken_keys.add(key)
        book = Book.from_dict({**row, "id": rid, "title": title, "author": author})
        state["books"].append(book.to_dict())
        added.append(rid)
    save_state(state)
    return {"added": added, "skipped_duplicates": skipped, "skipped_invalid": invalid}


# Every field of a Book except its id can be edited.
_EDITABLE = ("title", "author", "genre", "status", "rating", "pages", "finished")


def update_book(book_id: str, changes: dict) -> bool:
    """Edit a book (seed or added) via copy-on-write. Only the keys present in
    `changes` with a non-None value are applied — the rest stay as they are — so
    callers pass just what's changing. The first edit of a seed book writes a full
    copy into mutable state under the same id; thereafter your copy wins. Returns
    False if the id is unknown (incl. already-deleted) or a value is invalid
    (unknown status, rating outside 1-5)."""
    current = {b.id: b for b in load_books()}.get(book_id)
    if current is None:
        return False
    clean = {k: v for k, v in changes.items() if k in _EDITABLE and v is not None}
    if validate_book_fields(status=clean.get("status"), rating=clean.get("rating")):
        return False
    if "rating" in clean:
        clean["rating"] = int(clean["rating"])
    if "pages" in clean:
        clean["pages"] = int(clean["pages"])
    updated = dataclasses.replace(current, **clean)
    state = load_state()
    # Replace any existing state record for this id, then write the new full copy.
    state["books"] = [b for b in state["books"] if b["id"] != book_id]
    state["books"].append(updated.to_dict())
    save_state(state)
    return True


def _today_iso() -> str:
    """The store's one clock read, factored out as a seam so tests can pin it
    (monkeypatch this) instead of asserting against a runtime date.today()."""
    return date.today().isoformat()


def mark_status(book_id: str, status: str, finished: str | None = None) -> bool:
    """Move a book between to-read / reading / read — the common 'I finished it'
    edit, still one update_book overlay underneath. Marking a book "read" also
    stamps `finished` (today, unless a date is given) when it has no date yet:
    without the date, a finished book is invisible to everything date-keyed —
    books_by_month, latest_finished_year, pace_to_goal — so "I finished it"
    would never advance a reading goal. Re-marking a book that already has a
    date keeps the original. False on unknown id / invalid status."""
    if status not in STATUSES:
        return False
    changes: dict = {"status": status}
    if status == "read":
        current = {b.id: b for b in load_books()}.get(book_id)
        if current is None:
            return False
        if current.finished is None:
            changes["finished"] = finished or _today_iso()
    return update_book(book_id, changes)


def delete_book(book_id: str) -> bool:
    """Remove a book. A book you added is dropped from state; a seed book is hidden
    via a tombstone (reversible by adding it again). Returns False if unknown."""
    if book_id not in existing_ids():
        return False
    state = load_state()
    seed_ids = {b["id"] for b in _load_seed().get("books", [])}
    state["books"] = [b for b in state["books"] if b["id"] != book_id]
    if book_id in seed_ids:
        state["hidden_ids"] = sorted(set(state.get("hidden_ids", [])) | {book_id})
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
    everything you've added or edited (book records, deletions, goals, exports).
    Reversible for the samples via set_show_seed(True). Returns what was cleared."""
    state = load_state()
    cleared = {
        "books": len(state.get("books", [])),
        "deletions": len(state.get("hidden_ids", [])),
        "goals": len(state.get("goals", {})),
    }
    save_state({"books": [], "hidden_ids": [], "goals": {}, "exports": [],
                "settings": {"show_seed": False}})
    return cleared


# ── Exports (durable artifacts) ──────────────────────────────────────

def record_export(title: str, path: str) -> None:
    """Log export metadata: title + where it was written. Deliberately NOT the
    rendered content — nothing reads it back, and storing full reports grew
    state.json without bound on every export (the silent data-growth class
    this repo's CLAUDE.md warns about). The file on disk is the artifact."""
    state = load_state()
    state["exports"].append({"title": title, "path": path})
    save_state(state)


def export_default_path(name: str, ext: str = "md") -> Path:
    """Where export writes when no path is given: a KNOWN location under the data
    dir (not the process cwd, which is unpredictable when a desktop client
    launches the server). Creates the dir."""
    d = data_dir() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.{ext}"


def resolve_export_path(path: str) -> Path:
    """Confine a caller-supplied export path to the data dir.

    `path` arrives from the model (or a CLI flag); used raw it would make the
    export tool an arbitrary-file-write primitive — worst over the HTTP
    transport. Relative paths resolve under the data dir; absolute paths must
    already point inside it. Raises ValueError for anything that escapes."""
    base = data_dir().resolve()
    p = Path(path)
    out = (p if p.is_absolute() else base / p).resolve()
    if not out.is_relative_to(base):
        raise ValueError(f"export path must stay under the data dir ({base})")
    return out
