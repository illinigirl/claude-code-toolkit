"""Integration tests for the MCP tool layer — the surface a reviewer actually
drives. The pure logic is covered in test_core; this pins the *tool contract*:
reads over the seed, that an add/import flows through to the stats, the status
overlay, dedupe, and the export. Tools are called in-process (they're plain
functions) against a sandboxed data dir, so no transport/runtime is needed.
Skips if the MCP SDK isn't installed (the pure-core tests don't need it).
"""

from pathlib import Path

import pytest

pytest.importorskip("mcp")  # tool layer needs the MCP SDK; pure-core tests don't

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "goodreads_sample.csv"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKTRACKER_DATA_DIR", str(tmp_path))
    import booktracker.server as server
    return server


def test_top_genres_over_seed(srv):
    genres = srv.top_genres()["genres"]
    assert genres[0] == {"genre": "Fantasy", "count": 4}


def test_summary_over_seed(srv):
    s = srv.reading_summary()
    assert s["total"] == 15
    assert s["read"] == 11
    assert s["pages_read"] == 4119


def test_pace_to_goal_defaults_to_latest_year(srv):
    g = srv.pace_to_goal()
    assert g["year"] == 2024
    assert g["goal"] == 12
    assert g["read"] == 11
    assert g["remaining"] == 1


def test_add_book_flows_into_stats(srv):
    res = srv.add_book(title="Babel", author="R.F. Kuang", genre="Fantasy",
                       status="read", rating=5, pages=560, finished="2024-11-01")
    assert res["added"] is True
    # the new fantasy read bumps Fantasy from 4 → 5
    assert srv.top_genres()["genres"][0] == {"genre": "Fantasy", "count": 5}
    assert srv.reading_summary()["read"] == 12


def test_mark_status_overlays_a_seed_book(srv):
    # finish the book currently being read; reading 1 → 0, read 11 → 12
    assert srv.mark_status("the-two-towers", "read")["updated"] is True
    s = srv.reading_summary()
    assert s["reading"] == 0
    assert s["read"] == 12


def test_mark_status_rejects_unknown(srv):
    assert srv.mark_status("not-a-book", "read")["updated"] is False


def test_update_book_fixes_a_seed_genre(srv):
    # copy-on-write: editing a sample book's genre takes, and the seed file is
    # never touched (the change lives only in your state dir). Dune ships as
    # "Science Fiction" (3 of them); reclassifying it moves the buckets.
    assert srv.find_books(genre="Science Fiction")["count"] == 3
    assert srv.update_book("dune", genre="Space Opera")["updated"] is True
    dune = srv.find_books(author="Herbert")["books"][0]
    assert dune["genre"] == "Space Opera"
    # the edit moved it between buckets, didn't duplicate it
    assert srv.find_books(genre="Space Opera")["count"] == 1
    assert srv.find_books(genre="Science Fiction")["count"] == 2


def test_update_book_partial_leaves_other_fields(srv):
    # Dune ships rated 4; bump to 5 without disturbing title/genre/status.
    before = srv.find_books(author="Herbert")["books"][0]
    assert before["rating"] == 4
    assert srv.update_book("dune", rating=5)["updated"] is True
    after = srv.find_books(author="Herbert")["books"][0]
    assert after["rating"] == 5
    assert after["title"] == before["title"]
    assert after["genre"] == before["genre"]
    assert after["status"] == before["status"]


def test_update_book_rejects_unknown_and_bad_status(srv):
    assert srv.update_book("not-a-book", genre="X")["updated"] is False
    assert srv.update_book("dune", status="abandoned")["updated"] is False


def test_delete_added_book_is_dropped(srv):
    rid = srv.add_book(title="Babel", author="R.F. Kuang", genre="Fantasy")["book_id"]
    assert srv.find_books(author="Kuang")["count"] == 1
    assert srv.delete_book(rid)["deleted"] is True
    assert srv.find_books(author="Kuang")["count"] == 0
    assert srv.delete_book(rid)["deleted"] is False  # already gone


def test_delete_seed_book_tombstones(srv):
    assert srv.reading_summary()["total"] == 15
    assert srv.delete_book("dune")["deleted"] is True
    assert srv.reading_summary()["total"] == 14
    assert srv.find_books(author="Herbert")["count"] == 0
    # tombstone is reversible by re-adding the title
    srv.add_book(title="Dune", author="Frank Herbert", genre="Science Fiction")
    assert srv.find_books(author="Herbert")["count"] == 1


def test_add_books_dedupes(srv):
    rows = [
        {"title": "Piranesi", "author": "Susanna Clarke", "genre": "Fantasy"},
        {"title": "Dune", "author": "Frank Herbert"},  # duplicate of a seed book
    ]
    res = srv.add_books(rows)
    assert len(res["added"]) == 1
    assert res["skipped_duplicates"] == ["Dune"]


def test_import_goodreads_csv(srv):
    res = srv.import_goodreads_csv(_FIXTURE.read_text())
    assert res["parsed"] == 3
    assert len(res["added"]) == 2          # Fifth Season + Piranesi
    assert res["skipped_duplicates"] == ["Dune"]  # already in the seed
    # the imported read book lands in the stats
    assert srv.find_books(author="Jemisin")["count"] == 1


def test_set_goal_then_pace(srv):
    srv.set_goal(2024, 10)
    g = srv.pace_to_goal(2024)
    assert g["goal"] == 10
    assert g["on_track"] is True  # 11 read against a goal of 10


def test_find_books_filters(srv):
    assert srv.find_books(status="to-read")["count"] == 3
    assert srv.find_books(genre="mystery")["count"] == 2


def test_use_sample_library_toggles_reversibly(srv):
    assert srv.reading_summary()["total"] == 15        # samples on by default
    off = srv.use_sample_library(False)
    assert off["sample_library"] == "off"
    assert srv.reading_summary()["total"] == 0         # only your books (none yet)
    srv.use_sample_library(True)
    assert srv.reading_summary()["total"] == 15        # samples back


def test_reset_library_adopts_for_real(srv):
    srv.add_book(title="Babel", author="R.F. Kuang", genre="Fantasy", status="read", rating=5)
    cleared = srv.reset_library()
    assert cleared["books"] == 1
    assert srv.reading_summary()["total"] == 0         # samples hidden + your add cleared
    # reversible for the samples; your cleared add stays gone
    srv.use_sample_library(True)
    s = srv.reading_summary()
    assert s["total"] == 15
    assert srv.find_books(author="Kuang")["count"] == 0


def test_export_markdown_round_trip(srv):
    exp = srv.export_markdown()
    assert exp["format"] == "markdown"
    assert "# My reading list" in exp["content"]
    assert "Currently reading" in exp["content"]


def test_export_text_is_plain(srv):
    exp = srv.export_markdown(format="text")
    assert exp["format"] == "text"
    assert "#" not in exp["content"]


def test_export_favorites_by_genre(srv):
    # "my 5-star books grouped by genre" — one call: select + arrange
    exp = srv.export_markdown(group_by="genre", min_rating=5)
    c = exp["content"]
    assert exp["group_by"] == "genre"
    assert "# My 5★+ books by genre" in c
    assert "## Fantasy" in c
    assert "The Name of the Wind" in c   # a 5★ fantasy read
    assert "Gaudy Night" not in c        # 3★ — filtered out by min_rating
    assert "## Mystery" not in c         # no 5★ mystery → genre absent


def test_export_group_by_year(srv):
    c = srv.export_markdown(group_by="year")["content"]
    assert "## 2024" in c                # all seed reads finished in 2024
    assert "## Not yet finished" in c    # the reading + to-read books


def test_export_rejects_unknown_group_by(srv):
    assert "error" in srv.export_markdown(group_by="publisher")


def test_export_rejects_path_outside_data_dir(srv, tmp_path):
    # `path` comes from the model — confined to the data dir so the export tool
    # can't be steered into overwriting arbitrary files (worst over HTTP).
    escape = tmp_path.parent / "escape.md"
    res = srv.export_markdown(path=str(escape))
    assert "error" in res
    assert not escape.exists()


def test_export_relative_path_lands_in_data_dir(srv, tmp_path):
    res = srv.export_markdown(path="exports/mine.md")
    assert "error" not in res
    expected = (tmp_path / "exports" / "mine.md").resolve()
    assert Path(res["written"]) == expected
    assert expected.exists()
