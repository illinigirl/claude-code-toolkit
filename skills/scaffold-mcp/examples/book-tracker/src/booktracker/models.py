"""Domain models for book-tracker.

Plain dataclasses, no I/O — everything the core reasons over lives here, so the
whole pure layer is testable without an MCP runtime, a network, or a file.

A `Book` is the record; the rest are the shapes the deterministic compute returns
(genre counts, per-genre ratings, monthly counts, goal progress, a summary). The
core never returns loose dicts — it returns these, so the tool layer and the
tests share one typed contract.
"""

from __future__ import annotations

from dataclasses import dataclass

# The only valid statuses. A book moves to-read → reading → read.
STATUSES = ("to-read", "reading", "read")


@dataclass(frozen=True)
class Book:
    """One book in your log. `rating` (1–5) and `finished` (ISO date) are only
    meaningful once `status == "read"`; they stay None otherwise. Frozen and
    I/O-free so the core stays pure."""

    id: str
    title: str
    author: str
    genre: str
    status: str = "to-read"
    rating: int | None = None
    pages: int = 0
    finished: str | None = None  # "YYYY-MM-DD", set when read

    @classmethod
    def from_dict(cls, d: dict) -> Book:
        rating = d.get("rating")
        return cls(
            id=d["id"],
            title=d["title"],
            author=d["author"],
            genre=d.get("genre") or "Uncategorized",
            status=d.get("status") or "to-read",
            rating=int(rating) if rating is not None else None,
            pages=int(d.get("pages") or 0),
            finished=d.get("finished"),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "genre": self.genre,
            "status": self.status,
            "rating": self.rating,
            "pages": self.pages,
            "finished": self.finished,
        }


@dataclass(frozen=True)
class GenreCount:
    """How many books in a genre (used by top_genres / top_authors-style rollups)."""

    genre: str
    count: int


@dataclass(frozen=True)
class GenreRating:
    """Average rating within a genre, plus the sample size it's computed over —
    `count` matters because a 5.0 over one book is not a 4.75 over four."""

    genre: str
    count: int
    avg_rating: float


@dataclass(frozen=True)
class AuthorCount:
    """How many books you've read by an author."""

    author: str
    count: int


@dataclass(frozen=True)
class MonthCount:
    """How many books you finished in a calendar month (e.g. 'January')."""

    month: str
    count: int


@dataclass(frozen=True)
class GoalProgress:
    """Reading-goal progress for a year. `as_of_month` (1–12) is the elapsed
    fraction of the year used for pace — injected by the caller so the core stays
    pure (it never reads the clock)."""

    year: int
    goal: int
    read: int
    remaining: int
    as_of_month: int
    projected: int
    on_track: bool


@dataclass(frozen=True)
class Summary:
    """The exact roll-up of your whole log — counts by status, average rating
    over rated books, total pages read. Deterministic; the model never guesses it."""

    total: int
    read: int
    reading: int
    to_read: int
    avg_rating: float
    pages_read: int
