"""Render a reading-list report to Markdown or plain text. Pure string-building —
no file writes happen here (store.py / server.py own that). The rendered content
is returned inline so a remote caller who can't read the server's disk still gets
the result.

The grouping axis (status / genre / author / year) is decided by `core.group_books`;
these renderers just lay out whatever sections it returns. One parameterized
export, not one per arrangement.
"""

from __future__ import annotations

from .core import group_books, reading_summary
from .models import Book


def export_title(group_by: str, min_rating: int | None) -> str:
    """A title that reflects the selection + arrangement, e.g. 'My 5★+ books by
    genre'. Plain 'My reading list' for the default status view."""
    noun = f"My {min_rating}★+ books" if min_rating else "My reading list"
    return noun if group_by == "status" else f"{noun} by {group_by}"


def render_grouped_markdown(books: list[Book], title: str, by: str = "status") -> str:
    """A Markdown report, grouped by `by`, with an exact stats header."""
    s = reading_summary(books)
    lines = [
        f"# {title}",
        "",
        f"**{s.total} books** · {s.read} read · avg rating **{s.avg_rating:g}** · "
        f"**{s.pages_read:,}** pages read",
        "",
    ]
    for label, rows in group_books(books, by):
        lines.append(f"## {label}")
        lines.append("")
        for b in rows:
            stars = f" — {'★' * b.rating}" if b.rating else ""
            lines.append(f"- *{b.title}* — {b.author} ({b.genre}){stars}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_grouped_text(books: list[Book], title: str, by: str = "status") -> str:
    """A plain-text report — for pasting into Notes / Reminders / a message."""
    s = reading_summary(books)
    lines = [title, "", f"{s.total} books — {s.read} read, avg rating {s.avg_rating:g}", ""]
    for label, rows in group_books(books, by):
        lines.append(f"{label}:")
        for b in rows:
            stars = f" ({b.rating}/5)" if b.rating else ""
            lines.append(f"  - {b.title} — {b.author}{stars}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
