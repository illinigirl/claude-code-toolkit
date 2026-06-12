"""Pure domain logic for book-tracker — no I/O, fully unit-tested on stdlib.

This is the deterministic data plane. Every function here takes books in and
returns a value out: no files, no network, no globals, and crucially **no clock**
(pace_to_goal takes the elapsed month as an argument so it stays pure and
testable). Exact counts and averages live here so the model never has to do
arithmetic in its head — reason #4 a tool earns its place (see CLAUDE.md).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from .models import (
    AuthorCount,
    Book,
    GenreCount,
    GenreRating,
    GoalProgress,
    MonthCount,
    Summary,
)

# Goodreads "Exclusive Shelf" values → our statuses.
_GOODREADS_SHELF = {"read": "read", "to-read": "to-read", "currently-reading": "reading"}

# Calendar month names, 1-indexed via MONTHS[n - 1].
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Status display order + labels for grouped exports.
_STATUS_DISPLAY = (
    ("reading", "Currently reading"),
    ("to-read", "Want to read"),
    ("read", "Read"),
)


def read_books(books: list[Book]) -> list[Book]:
    """Just the finished books — the subset most stats are computed over."""
    return [b for b in books if b.status == "read"]


def find_books(
    books: list[Book],
    genre: str | None = None,
    author: str | None = None,
    status: str | None = None,
    min_rating: int | None = None,
) -> list[Book]:
    """One parameterized filter over your local data. 'show me all fantasy',
    'everything by Le Guin', 'my unread pile', 'books I rated 4+' are all THIS
    function with different args — deliberately one tool, not four. Matching is
    case-insensitive on genre/author. Pure over its input."""
    out = list(books)
    if genre is not None:
        out = [b for b in out if b.genre.lower() == genre.lower()]
    if author is not None:
        out = [b for b in out if author.lower() in b.author.lower()]
    if status is not None:
        out = [b for b in out if b.status == status]
    if min_rating is not None:
        out = [b for b in out if b.rating is not None and b.rating >= min_rating]
    return out


def _sorted_books(books: list[Book]) -> list[Book]:
    return sorted(books, key=lambda b: (b.author, b.title))


def group_books(books: list[Book], by: str = "status") -> list[tuple[str, list[Book]]]:
    """Arrange books into (label, books) sections for an export, in display order.

    `by`: 'status' (reading / to-read / read), 'genre' or 'author' (ranked by
    size, biggest first), or 'year' (finished year, most recent first; unfinished
    last). Pure; raises ValueError on an unknown axis. This only *arranges* —
    selecting which books to include is the caller's job via find_books, so one
    parameterized export covers "favorites by genre", "everything by year", etc.,
    instead of a separate tool per arrangement.
    """
    if by == "status":
        sections = []
        for status, label in _STATUS_DISPLAY:
            rows = _sorted_books([b for b in books if b.status == status])
            if rows:
                sections.append((label, rows))
        return sections
    if by == "year":
        buckets: dict[str | None, list[Book]] = defaultdict(list)
        for b in books:
            year = b.finished[:4] if b.finished and len(b.finished) >= 4 else None
            buckets[year].append(b)
        sections = [(y, _sorted_books(buckets[y]))
                    for y in sorted((y for y in buckets if y), reverse=True)]
        if None in buckets:
            sections.append(("Not yet finished", _sorted_books(buckets[None])))
        return sections
    if by in ("genre", "author"):
        key = (lambda b: b.genre) if by == "genre" else (lambda b: b.author)
        buckets = defaultdict(list)
        for b in books:
            buckets[key(b)].append(b)
        ranked = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        return [(label, _sorted_books(rows)) for label, rows in ranked]
    raise ValueError(f"unknown group_by: {by!r} (use status|genre|author|year)")


def top_genres(books: list[Book]) -> list[GenreCount]:
    """Genres you've read most, ranked. Counts finished books only ('what do I
    actually read', not 'what's on the shelf'). Ties broken alphabetically so the
    ordering is deterministic."""
    counts: dict[str, int] = defaultdict(int)
    for b in read_books(books):
        counts[b.genre] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [GenreCount(genre=g, count=c) for g, c in ranked]


def rating_by_genre(books: list[Book]) -> list[GenreRating]:
    """Average rating per genre over your rated books, ranked high→low. Carries
    `count` too, because an average is only as trustworthy as its sample size —
    a 5.0 over one book ranks above a 4.75 over four, and the caller should say so."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for b in read_books(books):
        if b.rating is not None:
            buckets[b.genre].append(b.rating)
    rows = [
        GenreRating(genre=g, count=len(rs), avg_rating=round(sum(rs) / len(rs), 2))
        for g, rs in buckets.items()
    ]
    return sorted(rows, key=lambda r: (-r.avg_rating, r.genre))


def top_authors(books: list[Book]) -> list[AuthorCount]:
    """Authors you've read most, ranked. Finished books only; ties alphabetical."""
    counts: dict[str, int] = defaultdict(int)
    for b in read_books(books):
        counts[b.author] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [AuthorCount(author=a, count=c) for a, c in ranked]


def books_by_month(books: list[Book]) -> list[MonthCount]:
    """How many books you finished in each calendar month, in calendar order.
    Aggregates across years (seasonality, not a timeline) — 'when do I read most?'
    Only months with at least one finished book appear."""
    counts: dict[int, int] = defaultdict(int)
    for b in read_books(books):
        if b.finished and len(b.finished) >= 7:
            month_num = int(b.finished[5:7])
            if 1 <= month_num <= 12:
                counts[month_num] += 1
    return [MonthCount(month=MONTHS[n - 1], count=counts[n]) for n in sorted(counts)]


def reading_summary(books: list[Book]) -> Summary:
    """Exact whole-log roll-up: totals by status, average rating over rated books,
    total pages read. Pure arithmetic the model narrates but never computes."""
    by_status: dict[str, int] = defaultdict(int)
    for b in books:
        by_status[b.status] += 1
    rated = [b.rating for b in books if b.rating is not None]
    avg = round(sum(rated) / len(rated), 2) if rated else 0.0
    pages_read = sum(b.pages for b in read_books(books))
    return Summary(
        total=len(books),
        read=by_status.get("read", 0),
        reading=by_status.get("reading", 0),
        to_read=by_status.get("to-read", 0),
        avg_rating=avg,
        pages_read=pages_read,
    )


def latest_finished_year(books: list[Book]) -> int | None:
    """The most recent year you finished a book in — the natural default year for
    goal questions (you ask about a year that has data, not necessarily today)."""
    years = [int(b.finished[:4]) for b in read_books(books) if b.finished and len(b.finished) >= 4]
    return max(years) if years else None


def pace_to_goal(books: list[Book], goal: int, year: int, as_of_month: int) -> GoalProgress:
    """Progress toward a yearly reading goal. `as_of_month` (1–12) is how far into
    the year we are — passed in, never read from the clock, so this is pure and
    deterministic. `projected` linearly extrapolates your current pace to year-end;
    `on_track` is whether you've read at least your goal's share of the elapsed year."""
    read = len([b for b in read_books(books) if b.finished and b.finished[:4] == str(year)])
    as_of_month = max(1, min(12, as_of_month))
    projected = round(read / as_of_month * 12)
    on_track = read >= goal * as_of_month / 12
    return GoalProgress(
        year=year,
        goal=goal,
        read=read,
        remaining=max(0, goal - read),
        as_of_month=as_of_month,
        projected=projected,
        on_track=on_track,
    )


def _norm_date(raw: str) -> str | None:
    """Goodreads writes dates as YYYY/MM/DD; normalize to ISO YYYY-MM-DD."""
    raw = (raw or "").strip()
    if not raw:
        return None
    parts = raw.replace("-", "/").split("/")
    if len(parts) == 3 and parts[0].isdigit():
        y, m, d = parts
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return None


def parse_goodreads_csv(text: str) -> list[dict]:
    """Parse a Goodreads "Export Library" CSV into book rows ready for the store.

    Pure: text in, rows out — no I/O, so it's unit-tested directly. This is the
    bulk-history path (you don't photograph a decade of reading; you export it).
    Maps the real export columns: My Rating (0 = unrated → None), Number of Pages,
    Exclusive Shelf → status, Date Read → finished. Goodreads has no genre field,
    so genre is derived from the first non-status user shelf in `Bookshelves` —
    a deliberately lossy real-world compromise (default 'Uncategorized').
    """
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        title = (raw.get("Title") or "").strip()
        if not title:
            continue
        rating = (raw.get("My Rating") or "").strip()
        rating_val = int(rating) if rating.isdigit() and int(rating) > 0 else None
        pages = (raw.get("Number of Pages") or "").strip()
        shelf = (raw.get("Exclusive Shelf") or "").strip().lower()
        rows.append({
            "title": title,
            "author": (raw.get("Author") or "").strip(),
            "genre": _genre_from_shelves(raw.get("Bookshelves") or ""),
            "status": _GOODREADS_SHELF.get(shelf, "to-read"),
            "rating": rating_val,
            "pages": int(pages) if pages.isdigit() else 0,
            "finished": _norm_date(raw.get("Date Read") or ""),
        })
    return rows


def _genre_from_shelves(bookshelves: str) -> str:
    """First user shelf that isn't a status shelf, title-cased; else 'Uncategorized'."""
    for shelf in (s.strip() for s in bookshelves.split(",")):
        if shelf and shelf.lower() not in _GOODREADS_SHELF:
            return shelf.replace("-", " ").title()
    return "Uncategorized"
