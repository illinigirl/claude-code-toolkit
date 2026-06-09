"""Render a reading-list report to Markdown or plain text. Pure string-building —
no file writes happen here (store.py / server.py own that). The rendered content
is returned inline so a remote caller who can't read the server's disk still gets
the result.
"""

from __future__ import annotations

from .core import reading_summary, top_genres
from .models import Book

_STATUS_ORDER = ("reading", "to-read", "read")
_STATUS_LABEL = {"reading": "Currently reading", "to-read": "Want to read", "read": "Read"}


def _by_status(books: list[Book], status: str) -> list[Book]:
    rows = [b for b in books if b.status == status]
    return sorted(rows, key=lambda b: (b.author, b.title))


def render_reading_list_markdown(books: list[Book], title: str) -> str:
    """A Markdown reading list grouped by status, with an exact stats header."""
    s = reading_summary(books)
    genres = top_genres(books)
    top = f"{genres[0].genre} ({genres[0].count})" if genres else "—"
    lines = [
        f"# {title}",
        "",
        f"**{s.total} books** · {s.read} read · {s.reading} reading · "
        f"{s.to_read} to read · avg rating **{s.avg_rating:g}** · "
        f"**{s.pages_read:,}** pages read · top genre **{top}**",
        "",
    ]
    for status in _STATUS_ORDER:
        rows = _by_status(books, status)
        if not rows:
            continue
        lines.append(f"## {_STATUS_LABEL[status]}")
        lines.append("")
        for b in rows:
            stars = f" — {'★' * b.rating}" if b.rating else ""
            lines.append(f"- *{b.title}* — {b.author} ({b.genre}){stars}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_reading_list_text(books: list[Book], title: str) -> str:
    """A plain-text reading list — for pasting into Notes / Reminders / a message."""
    s = reading_summary(books)
    lines = [title, "", f"{s.total} books — {s.read} read, {s.reading} reading, {s.to_read} to read", ""]
    for status in _STATUS_ORDER:
        rows = _by_status(books, status)
        if not rows:
            continue
        lines.append(f"{_STATUS_LABEL[status]}:")
        for b in rows:
            stars = f" ({b.rating}/5)" if b.rating else ""
            lines.append(f"  - {b.title} — {b.author}{stars}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
