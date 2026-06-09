"""Unit tests for the pure core — no I/O, no MCP runtime, runs on stdlib alone.
This is where the bulk of the domain logic is covered; the values are pinned to
the bundled seed library so the deterministic math is exact, not approximate."""

from booktracker import core


def test_find_books_filters_compose(books):
    # one parameterized filter stands in for "all fantasy", "by Le Guin", etc.
    fantasy = core.find_books(books, genre="fantasy")  # case-insensitive
    assert {b.genre for b in fantasy} == {"Fantasy"}
    assert len(fantasy) == 6  # all statuses: 4 read + 1 reading + 1 to-read

    le_guin = core.find_books(books, author="le guin")
    assert {b.author for b in le_guin} == {"Ursula K. Le Guin"}
    assert len(le_guin) == 2

    highly_rated = core.find_books(books, min_rating=5)
    assert highly_rated and all(b.rating >= 5 for b in highly_rated)

    to_read = core.find_books(books, status="to-read")
    assert len(to_read) == 3


def test_top_genres_counts_read_only_and_ranks(books):
    ranked = core.top_genres(books)
    assert ranked[0].genre == "Fantasy"
    assert ranked[0].count == 4  # the reading/to-read fantasy books don't count
    # full ranking, ties broken alphabetically
    assert [(g.genre, g.count) for g in ranked] == [
        ("Fantasy", 4), ("Science Fiction", 3), ("Mystery", 2),
        ("Literary", 1), ("Nonfiction", 1),
    ]


def test_rating_by_genre_carries_sample_size(books):
    rows = core.rating_by_genre(books)
    by = {r.genre: r for r in rows}
    assert by["Fantasy"].avg_rating == 4.75
    assert by["Fantasy"].count == 4
    # Literary's 5.0 outranks Fantasy's 4.75 — but on a sample of one
    assert rows[0].genre == "Literary"
    assert rows[0].avg_rating == 5.0
    assert rows[0].count == 1


def test_top_authors_ties_alphabetical(books):
    rows = core.top_authors(books)
    assert rows[0].count == 2
    # Tolkien and Le Guin tie at 2 read; "J.R.R." sorts before "Ursula"
    assert [r.author for r in rows[:2]] == ["J.R.R. Tolkien", "Ursula K. Le Guin"]


def test_books_by_month_seasonality(books):
    months = {m.month: m.count for m in core.books_by_month(books)}
    assert months["January"] == 3  # busiest
    assert months["February"] == 1
    assert max(core.books_by_month(books), key=lambda m: m.count).month == "January"


def test_reading_summary_is_exact(books):
    s = core.reading_summary(books)
    assert (s.total, s.read, s.reading, s.to_read) == (15, 11, 1, 3)
    assert s.avg_rating == 4.36  # 48 / 11
    assert s.pages_read == 4119


def test_pace_to_goal_past_year_is_complete(books):
    g = core.pace_to_goal(books, goal=12, year=2024, as_of_month=12)
    assert g.read == 11
    assert g.remaining == 1
    assert g.projected == 11
    assert g.on_track is False  # 11 of 12 — one short


def test_pace_to_goal_midyear_projects(books):
    # as_of_month only changes the projection divisor; read is the full-year count.
    # Treated as if only 6 months elapsed, 11 books pace out to ~22 for the year.
    g = core.pace_to_goal(books, goal=20, year=2024, as_of_month=6)
    assert g.read == 11
    assert g.projected == 22  # 11 / 6 * 12, rounded


def test_latest_finished_year(books):
    assert core.latest_finished_year(books) == 2024


def test_parse_goodreads_csv(goodreads_csv):
    rows = core.parse_goodreads_csv(goodreads_csv)
    assert len(rows) == 3
    fifth = next(r for r in rows if r["title"] == "The Fifth Season")
    assert fifth["author"] == "N.K. Jemisin"
    assert fifth["genre"] == "Fantasy"      # derived from the 'fantasy' shelf
    assert fifth["status"] == "read"        # Exclusive Shelf
    assert fifth["rating"] == 5
    assert fifth["pages"] == 512
    assert fifth["finished"] == "2024-10-03"  # YYYY/MM/DD → ISO
    piranesi = next(r for r in rows if r["title"] == "Piranesi")
    assert piranesi["rating"] is None       # My Rating 0 → unrated
    assert piranesi["status"] == "to-read"
    assert piranesi["finished"] is None
