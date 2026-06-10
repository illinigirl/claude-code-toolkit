"""The MCP server — a thin adapter over the pure core.

Design split: all logic lives in core/exports and is unit-tested without a
runtime; this file only wires those to MCP tools + persistence (store.py). The
CLI (cli.py) is a second adapter over the exact same functions.

The ingest tools form a ladder by scale/source — `add_book` (one), `add_books`
(a few; the sink Claude's vision uses for a photographed shelf, or NL for "I read
X, Y, Z"), `import_goodreads_csv` (your whole back-catalog from the real export).
All three funnel into one dedupe-and-persist sink. The compute tools are exact
(counts, averages, pace) so the model narrates numbers it never has to compute.

Dual transport from one codebase: stdio by default (a local Claude Desktop
subprocess), or streamable-HTTP via --http / BOOKTRACKER_HTTP=1 so the same
server can be added as a remote custom connector by URL.
"""

from __future__ import annotations

import argparse
import os
from datetime import date

from mcp.server.fastmcp import FastMCP

from . import core, store
from .exports import export_title, render_grouped_markdown, render_grouped_text

mcp = FastMCP("book-tracker")

_GROUP_BY = ("status", "genre", "author", "year")


# ── Ingest (persist state — the cross-session memory plain Claude lacks) ──

@mcp.tool()
def add_book(title: str, author: str, genre: str = "Uncategorized", status: str = "to-read",
             rating: int | None = None, pages: int = 0, finished: str | None = None) -> dict:
    """Add one book to your library. Use for a single book you mention or
    photograph. `status` is to-read / reading / read; `rating` (1–5) and
    `finished` (YYYY-MM-DD) apply once you've read it. Goes through the same
    validate-dedupe-persist sink as bulk adds, so a duplicate (same title +
    author) or an invalid status/rating is reported back, not silently stored."""
    result = store.add_books([{"title": title, "author": author, "genre": genre,
                               "status": status, "rating": rating, "pages": pages,
                               "finished": finished}])
    if result["added"]:
        return {"added": True, "book_id": result["added"][0]}
    if result["skipped_invalid"]:
        return {"added": False, "error": result["skipped_invalid"][0]["error"], "title": title}
    if result["skipped_duplicates"]:
        return {"added": False, "title": title,
                "error": "already in your library (same title + author) — use update_book to edit it"}
    return {"added": False, "error": "title is required"}


@mcp.tool()
def add_books(books: list[dict]) -> dict:
    """Bulk-add a list of books, skipping duplicates (same title + author). This is
    the sink for a photographed shelf (your vision extracts the rows) or a natural-
    language list. Each row: title (required), author, genre, status, rating, pages,
    finished. Returns the ids added and titles skipped as duplicates."""
    return store.add_books(books)


@mcp.tool()
def import_goodreads_csv(csv_text: str) -> dict:
    """Import your reading history from a pasted Goodreads "Export Library" CSV —
    the path for backfilling years of books at once (photo/NL don't scale to a
    back-catalog). Parses the real export columns deterministically and dedupes
    against what's already there. Genre is derived from your shelves (Goodreads
    has no genre field), so it's best-effort."""
    rows = core.parse_goodreads_csv(csv_text)
    result = store.add_books(rows)
    return {"parsed": len(rows), **result}


@mcp.tool()
def mark_status(book_id: str, status: str, finished: str | None = None) -> dict:
    """Move a book between to-read / reading / read (e.g. you finished it). A
    shortcut for the common case — update_book changes any field, this just
    status. Marking a book "read" stamps its finish date (today, or pass
    `finished` as YYYY-MM-DD for "I finished it last week"), so it counts
    toward your reading goal and monthly stats; a book that already has a
    finish date keeps it."""
    ok = store.mark_status(book_id, status, finished=finished)
    return {"updated": ok, "book_id": book_id, "status": status} if ok else {
        "updated": False, "error": "unknown book_id or invalid status", "book_id": book_id}


@mcp.tool()
def update_book(book_id: str, title: str | None = None, author: str | None = None,
                genre: str | None = None, status: str | None = None,
                rating: int | None = None, pages: int | None = None,
                finished: str | None = None) -> dict:
    """Edit a book already in your library — fix a genre Claude guessed, correct a
    title or author, set a rating, change page count. Only the fields you pass
    change; omit the rest and they stay as they are. Works on the sample books too:
    the first edit makes your own copy of that book, and your version wins after.
    `status` is to-read / reading / read; `rating` is 1–5. Find the book_id with
    find_books first. Returns whether it updated."""
    changes = {"title": title, "author": author, "genre": genre, "status": status,
               "rating": rating, "pages": pages, "finished": finished}
    ok = store.update_book(book_id, changes)
    return {"updated": ok, "book_id": book_id} if ok else {
        "updated": False, "error": "unknown book_id or invalid field value",
        "book_id": book_id}


@mcp.tool()
def delete_book(book_id: str) -> dict:
    """Remove a single book from your library. A book you added is dropped; a sample
    book is hidden (reversible by adding it again). Find the book_id with find_books
    first. To clear the whole library at once, use reset_library instead. Returns
    whether it deleted."""
    ok = store.delete_book(book_id)
    return {"deleted": ok, "book_id": book_id} if ok else {
        "deleted": False, "error": "unknown book_id", "book_id": book_id}


@mcp.tool()
def set_goal(year: int, goal: int) -> dict:
    """Set your reading goal (number of books) for a year — feeds pace_to_goal."""
    store.set_goal(year, goal)
    return {"year": year, "goal": goal}


# ── Lifecycle: adopt book-tracker for your own reading ───────────────

@mcp.tool()
def use_sample_library(enabled: bool = True) -> dict:
    """Show or hide the bundled sample books. Turn it off ("stop using the sample
    library") and your library is only what you've added or imported; turn it on
    to bring the samples back. Reversible and non-destructive."""
    store.set_show_seed(enabled)
    return {"sample_library": "on" if enabled else "off",
            "books_in_library": len(store.load_books())}


@mcp.tool()
def reset_library() -> dict:
    """Start a fresh library of your own: hide the bundled sample books AND clear
    everything you've added (books, status changes, goals). Use this to actually
    adopt book-tracker for your real reading — then import a Goodreads export or
    start adding. Reversible for the samples via use_sample_library(True). Returns
    what was cleared."""
    return store.reset_library()


# ── Read / filter (ground the model in your private local data) ──────

@mcp.tool()
def find_books(genre: str | None = None, author: str | None = None,
               status: str | None = None, min_rating: int | None = None) -> dict:
    """Filter your library — 'all fantasy', 'everything by Le Guin', 'my to-read
    pile', 'books I rated 4+'. One parameterized lookup, not four separate tools."""
    rows = core.find_books(store.load_books(), genre=genre, author=author,
                           status=status, min_rating=min_rating)
    return {"count": len(rows), "books": [b.to_dict() for b in rows]}


# ── Compute (exact arithmetic the model narrates but never guesses) ──

@mcp.tool()
def top_genres() -> dict:
    """The genres you read most, ranked — counts finished books only."""
    return {"genres": [{"genre": g.genre, "count": g.count}
                       for g in core.top_genres(store.load_books())]}


@mcp.tool()
def rating_by_genre() -> dict:
    """Average rating per genre over your rated books, ranked high→low. Includes
    `count` so you can weigh a 5.0-over-one against a 4.75-over-four."""
    return {"genres": [{"genre": r.genre, "count": r.count, "avg_rating": r.avg_rating}
                       for r in core.rating_by_genre(store.load_books())]}


@mcp.tool()
def top_authors() -> dict:
    """The authors you've read most, ranked."""
    return {"authors": [{"author": a.author, "count": a.count}
                        for a in core.top_authors(store.load_books())]}


@mcp.tool()
def books_by_month() -> dict:
    """How many books you finished per calendar month (seasonality) — 'when do I
    read most?'. Aggregated across years, calendar order."""
    return {"months": [{"month": m.month, "count": m.count}
                       for m in core.books_by_month(store.load_books())]}


@mcp.tool()
def reading_summary() -> dict:
    """Exact whole-library roll-up: totals by status, average rating, pages read."""
    s = core.reading_summary(store.load_books())
    return {"total": s.total, "read": s.read, "reading": s.reading, "to_read": s.to_read,
            "avg_rating": s.avg_rating, "pages_read": s.pages_read}


@mcp.tool()
def pace_to_goal(year: int | None = None) -> dict:
    """Progress toward your reading goal for a year. Defaults to the most recent
    year you finished a book in. Reports books read, books remaining, and a
    pace-based projection for the full year."""
    books = store.load_books()
    if year is None:
        year = core.latest_finished_year(books)
        if year is None:
            return {"error": "no finished books yet"}
    goal = store.get_goal(year)
    if goal is None:
        return {"error": f"no goal set for {year}", "year": year}
    today = date.today()
    as_of_month = today.month if year == today.year else 12
    g = core.pace_to_goal(books, goal=goal, year=year, as_of_month=as_of_month)
    return {"year": g.year, "goal": g.goal, "read": g.read, "remaining": g.remaining,
            "projected": g.projected, "on_track": g.on_track, "as_of_month": g.as_of_month}


# ── Durable artifact (a report you keep; returned inline for remote callers) ──

@mcp.tool()
def export_markdown(path: str | None = None, format: str = "markdown",
                    group_by: str = "status", min_rating: int | None = None,
                    genre: str | None = None, author: str | None = None,
                    status: str | None = None) -> dict:
    """Write a reading-list report AND return it inline.

    Select which books with the same filters as find_books (`min_rating`, `genre`,
    `author`, `status`) and arrange them with `group_by` — "status" (default),
    "genre", "author", or "year". So "my 5-star books grouped by genre" is one
    call: group_by="genre", min_rating=5. One parameterized export, not a separate
    tool per arrangement.

    `format`: "markdown" (default) or "text". With no `path`, writes to a known
    location under the data dir (not the process cwd, unpredictable when a desktop
    client launches the server); a given `path` is confined to the data dir too.
    `content` is always returned, so a remote caller who can't read the server's
    disk still gets it."""
    if group_by not in _GROUP_BY:
        return {"error": f"group_by must be one of {list(_GROUP_BY)}", "group_by": group_by}
    books = core.find_books(store.load_books(), genre=genre, author=author,
                            status=status, min_rating=min_rating)
    title = export_title(group_by, min_rating)
    if format == "text":
        content, ext = render_grouped_text(books, title, group_by), "txt"
    else:
        content, ext = render_grouped_markdown(books, title, group_by), "md"
    try:
        out = (store.resolve_export_path(path) if path
               else store.export_default_path(date.today().isoformat(), ext=ext))
    except ValueError as e:
        return {"error": str(e), "path": path}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)
    store.record_export(title, content)
    return {"written": str(out), "format": format, "group_by": group_by, "content": content}


def _resolve_transport(argv=None) -> tuple[str, str, int]:
    """Decide transport from CLI flags / env. Default stdio (Claude Desktop launches
    the server as a subprocess); `--http` (or BOOKTRACKER_HTTP=1) serves
    streamable-HTTP so the same server can be a remote custom connector by URL.
    Factored out so it's unit-testable without binding a port."""
    parser = argparse.ArgumentParser(prog="book-tracker", description="book-tracker MCP server")
    parser.add_argument("--http", action="store_true",
                        help="serve over streamable-HTTP (custom connector) instead of stdio")
    parser.add_argument("--host", default=os.environ.get("BOOKTRACKER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BOOKTRACKER_PORT", "8000")))
    args = parser.parse_args(argv)
    http = args.http or os.environ.get("BOOKTRACKER_HTTP", "").lower() in {"1", "true", "yes"}
    return ("streamable-http" if http else "stdio", args.host, args.port)


def main(argv=None) -> None:
    transport, host, port = _resolve_transport(argv)
    if transport == "streamable-http":
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
