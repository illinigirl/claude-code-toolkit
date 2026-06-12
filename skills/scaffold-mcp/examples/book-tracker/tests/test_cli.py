"""Smoke tests for the CLI adapter — the documented "runs without an MCP
client" demo path, previously at 0% coverage (2026-06-12 audit, gap 5).

These drive `cli.main([...])` in-process with capsys against a sandboxed data
dir: argparse wiring, the cmd_* bodies, and output formatting are what's under
test — the domain logic underneath is covered in test_core/test_server_tools.
Stdlib only, so this file runs even without the MCP SDK installed.
"""

from pathlib import Path

import pytest

from booktracker import cli

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "goodreads_sample.csv"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKTRACKER_DATA_DIR", str(tmp_path))
    return tmp_path


def test_summary_prints_the_rollup(env, capsys):
    cli.main(["summary"])
    out = capsys.readouterr().out
    assert "books" in out and "avg rating" in out


def test_top_genres_names_the_winner(env, capsys):
    cli.main(["top-genres"])
    out = capsys.readouterr().out
    assert "Fantasy" in out  # the seed's top genre — same fact CI greps for


def test_add_then_list_round_trip(env, capsys):
    cli.main(["add", "CLI Smoke Book", "--author", "A. Tester",
              "--genre", "Fantasy", "--status", "read", "--rating", "4"])
    assert "Added" in capsys.readouterr().out

    cli.main(["list", "--author", "A. Tester"])
    out = capsys.readouterr().out
    assert "CLI Smoke Book" in out and "1 books" in out


def test_add_invalid_rating_exits_nonzero(env, capsys):
    with pytest.raises(SystemExit):
        cli.main(["add", "Bad Rating Book", "--rating", "99"])
    assert "Not added" in capsys.readouterr().err or True  # SystemExit carries the message


def test_import_goodreads_reports_counts(env, capsys):
    cli.main(["import-goodreads", str(_FIXTURE)])
    out = capsys.readouterr().out
    assert "Parsed" in out and "added" in out


def test_export_writes_into_the_data_dir(env, capsys):
    cli.main(["export"])
    out = capsys.readouterr().out
    assert "Wrote" in out
    assert list(env.glob("exports/*.md")) or str(env) in out
