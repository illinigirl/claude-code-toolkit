"""Smoke test: the MCP server module imports and registers its tools, and
transport selection works. Skips cleanly if the `mcp` SDK isn't installed (the
pure-core tests don't need it). Catches wiring/signature breakage without running
a server or touching saved state."""

import pytest

pytest.importorskip("mcp")


def test_server_exposes_expected_tools():
    import booktracker.server as server

    expected = {
        "add_book", "add_books", "import_goodreads_csv", "mark_status", "set_goal",
        "use_sample_library", "reset_library",
        "find_books", "top_genres", "rating_by_genre", "top_authors",
        "books_by_month", "reading_summary", "pace_to_goal", "export_markdown",
    }
    missing = {name for name in expected if not hasattr(server, name)}
    assert not missing, f"server missing tools: {missing}"


def test_transport_defaults_to_stdio():
    from booktracker.server import _resolve_transport

    assert _resolve_transport([])[0] == "stdio"


def test_http_flag_selects_streamable_http():
    from booktracker.server import _resolve_transport

    transport, host, port = _resolve_transport(["--http", "--port", "8765"])
    assert transport == "streamable-http"
    assert host == "127.0.0.1"
    assert port == 8765


def test_http_env_var_selects_streamable_http(monkeypatch):
    from booktracker.server import _resolve_transport

    monkeypatch.setenv("BOOKTRACKER_HTTP", "1")
    assert _resolve_transport([])[0] == "streamable-http"
