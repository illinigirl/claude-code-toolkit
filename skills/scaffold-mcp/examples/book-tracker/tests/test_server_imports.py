"""Smoke test: the MCP server module imports and registers its tools, and
transport selection works. Skips cleanly if the `mcp` SDK isn't installed (the
pure-core tests don't need it). Catches wiring/signature breakage without running
a server or touching saved state."""

import asyncio

import pytest

pytest.importorskip("mcp")


def test_tools_are_registered_with_fastmcp():
    # Asks FastMCP itself what's registered — NOT hasattr(server, name),
    # which still passes after an @mcp.tool() decorator is deleted (the bare
    # function remains a module attribute). This version goes red when a
    # tool actually falls off the live surface.
    import booktracker.server as server

    expected = {
        "add_book", "add_books", "import_goodreads_csv", "mark_status",
        "update_book", "delete_book", "set_goal",
        "use_sample_library", "reset_library",
        "find_books", "top_genres", "rating_by_genre", "top_authors",
        "books_by_month", "reading_summary", "pace_to_goal", "export_markdown",
    }
    registered = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    missing = expected - set(registered)
    assert not missing, f"not registered with FastMCP: {missing}"

    # Docstrings are the contract Claude reads — a tool without one is wired
    # but mute.
    undocumented = [n for n in expected if not (registered[n].description or "").strip()]
    assert not undocumented, f"tools missing docstrings: {undocumented}"


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
