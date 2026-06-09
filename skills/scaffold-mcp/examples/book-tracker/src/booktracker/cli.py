"""A thin CLI over the same core — so the project runs and demos WITHOUT wiring
up an MCP client. Same functions the MCP tools call.

    python -m booktracker.cli top-genres          # the headline: one-line insight
    python -m booktracker.cli by-month
    python -m booktracker.cli pace [--year YYYY]
    python -m booktracker.cli summary
    python -m booktracker.cli list [--genre X] [--author Y] [--status read] [--min-rating N]
    python -m booktracker.cli add "<title>" --author "<author>" [--genre G] [--status S] [--rating N]
    python -m booktracker.cli edit <book_id> [--genre G] [--rating N] [--status S] ...
    python -m booktracker.cli delete <book_id>
    python -m booktracker.cli import-goodreads <file.csv>
    python -m booktracker.cli export [path] [--format markdown|text]
"""

from __future__ import annotations

import argparse
from datetime import date

from . import core, store
from .exports import export_title, render_grouped_markdown, render_grouped_text
from .models import STATUSES, Book


def cmd_top_genres(args):
    genres = core.top_genres(store.load_books())
    if not genres:
        print("No finished books yet.")
        return
    print("Genres you read most:\n")
    for g in genres:
        print(f"  {g.genre:<16} {g.count}")
    top = genres[0]
    print(f"\n→ You read {top.genre} most ({top.count} books).")


def cmd_by_month(args):
    months = core.books_by_month(store.load_books())
    if not months:
        print("No finished books yet.")
        return
    busiest = max(months, key=lambda m: m.count)
    print("Books finished by month:\n")
    for m in months:
        bar = "█" * m.count
        print(f"  {m.month:<11} {bar} {m.count}")
    print(f"\n→ You read most in {busiest.month} ({busiest.count}).")


def cmd_pace(args):
    books = store.load_books()
    year = args.year or core.latest_finished_year(books)
    if year is None:
        print("No finished books yet.")
        return
    goal = store.get_goal(year)
    if goal is None:
        print(f"No goal set for {year}.")
        return
    today = date.today()
    as_of_month = today.month if year == today.year else 12
    g = core.pace_to_goal(books, goal=goal, year=year, as_of_month=as_of_month)
    verdict = "on track" if g.on_track else "behind"
    print(f"{year}: read {g.read} of {g.goal} ({verdict}); "
          f"{g.remaining} to go, projected {g.projected} for the year.")


def cmd_summary(args):
    s = core.reading_summary(store.load_books())
    print(f"{s.total} books — {s.read} read, {s.reading} reading, {s.to_read} to read")
    print(f"avg rating {s.avg_rating:g} · {s.pages_read:,} pages read")


def cmd_list(args):
    rows = core.find_books(store.load_books(), genre=args.genre, author=args.author,
                           status=args.status, min_rating=args.min_rating)
    print(f"{len(rows)} books\n")
    for b in rows:
        stars = f"{'★' * b.rating}" if b.rating else ""
        print(f"  {b.title:<34} {b.author:<22} {b.genre:<14} {b.status:<10} {stars}")


def cmd_add(args):
    rid = store.unique_id(args.title)
    store.add_book(Book(id=rid, title=args.title, author=args.author, genre=args.genre,
                        status=args.status, rating=args.rating, pages=args.pages,
                        finished=args.finished))
    print(f"Added {rid}")


def cmd_import_goodreads(args):
    text = open(args.csv_file, encoding="utf-8").read()
    rows = core.parse_goodreads_csv(text)
    result = store.add_books(rows)
    print(f"Parsed {len(rows)} rows: added {len(result['added'])}, "
          f"skipped {len(result['skipped_duplicates'])} duplicates.")


def cmd_samples(args):
    store.set_show_seed(args.state == "on")
    n = len(store.load_books())
    print(f"Sample library {args.state} — {n} books in your library.")


def cmd_edit(args):
    changes = {"title": args.title, "author": args.author, "genre": args.genre,
               "status": args.status, "rating": args.rating, "pages": args.pages,
               "finished": args.finished}
    ok = store.update_book(args.book_id, changes)
    print(f"Updated {args.book_id}" if ok else f"No such book: {args.book_id}")


def cmd_delete(args):
    ok = store.delete_book(args.book_id)
    print(f"Deleted {args.book_id}" if ok else f"No such book: {args.book_id}")


def cmd_reset(args):
    cleared = store.reset_library()
    print(f"Reset: cleared {cleared['books']} book records, "
          f"{cleared['deletions']} deletions, {cleared['goals']} goals; "
          "sample library hidden. Your library is empty — add or import to start.")


def cmd_export(args):
    from pathlib import Path
    books = core.find_books(store.load_books(), genre=args.genre, author=args.author,
                            status=args.status, min_rating=args.min_rating)
    title = export_title(args.group_by, args.min_rating)
    if args.format == "text":
        content, ext = render_grouped_text(books, title, args.group_by), "txt"
    else:
        content, ext = render_grouped_markdown(books, title, args.group_by), "md"
    out = Path(args.path) if args.path else store.export_default_path(date.today().isoformat(), ext=ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)
    print(f"Wrote {out}\n")
    print(content)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="booktracker", description="book-tracker CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("top-genres", help="genres you read most").set_defaults(func=cmd_top_genres)
    sub.add_parser("by-month", help="books finished by calendar month").set_defaults(func=cmd_by_month)
    sub.add_parser("summary", help="whole-library roll-up").set_defaults(func=cmd_summary)

    pp = sub.add_parser("pace", help="progress toward your yearly goal")
    pp.add_argument("--year", type=int)
    pp.set_defaults(func=cmd_pace)

    pl = sub.add_parser("list", help="filter your library")
    pl.add_argument("--genre")
    pl.add_argument("--author")
    pl.add_argument("--status", choices=list(STATUSES))
    pl.add_argument("--min-rating", type=int, dest="min_rating")
    pl.set_defaults(func=cmd_list)

    pa = sub.add_parser("add", help="add one book")
    pa.add_argument("title")
    pa.add_argument("--author", default="")
    pa.add_argument("--genre", default="Uncategorized")
    pa.add_argument("--status", default="to-read")
    pa.add_argument("--rating", type=int)
    pa.add_argument("--pages", type=int, default=0)
    pa.add_argument("--finished")
    pa.set_defaults(func=cmd_add)

    ped = sub.add_parser("edit", help="change fields of a book already in your library")
    ped.add_argument("book_id")
    ped.add_argument("--title")
    ped.add_argument("--author")
    ped.add_argument("--genre")
    ped.add_argument("--status", choices=list(STATUSES))
    ped.add_argument("--rating", type=int)
    ped.add_argument("--pages", type=int)
    ped.add_argument("--finished")
    ped.set_defaults(func=cmd_edit)

    pdl = sub.add_parser("delete", help="remove a book (added book dropped; sample hidden)")
    pdl.add_argument("book_id")
    pdl.set_defaults(func=cmd_delete)

    pi = sub.add_parser("import-goodreads", help="bulk import a Goodreads export CSV")
    pi.add_argument("csv_file")
    pi.set_defaults(func=cmd_import_goodreads)

    psm = sub.add_parser("samples", help="show/hide the bundled sample books")
    psm.add_argument("state", choices=["on", "off"])
    psm.set_defaults(func=cmd_samples)

    sub.add_parser(
        "reset", help="adopt it for real: hide samples + clear your added books"
    ).set_defaults(func=cmd_reset)

    pe = sub.add_parser("export", help="write a reading-list report")
    pe.add_argument("path", nargs="?")
    pe.add_argument("--format", choices=["markdown", "text"], default="markdown")
    pe.add_argument("--group-by", dest="group_by",
                    choices=["status", "genre", "author", "year"], default="status")
    pe.add_argument("--min-rating", type=int, dest="min_rating")
    pe.add_argument("--genre")
    pe.add_argument("--author")
    pe.add_argument("--status", choices=list(STATUSES))
    pe.set_defaults(func=cmd_export)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
