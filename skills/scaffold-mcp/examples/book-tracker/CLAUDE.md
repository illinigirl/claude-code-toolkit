# CLAUDE.md — book-tracker guidance

Read this first. It's the contract for working in this repo with an agent: what
the pieces are, how to run and test, the design decisions, and — most
importantly — the test for whether a new tool belongs here at all.

> This is the **worked example** of the `scaffold-mcp` pattern: a real domain (a
> reading log) wired through the same pure-core + thin-adapters architecture the
> generic scaffold ships. Compare it to the generated skeleton to see what
> "adapt the toy core to your domain" actually looks like.

## What this is

A **self-contained MCP server**: a deterministic data plane (exact compute,
persisted state, durable exports over your own reading log) that the LLM narrates.
No auth, no cloud, no external API — it clones and runs with zero credentials,
because the bundled `data/booktracker.seed.json` is a realistic starter library.

## Why this is an MCP and not just a prompt — the four-part test

The honest test for whether a tool earns its place: **does it give the model
something it cannot do alone?** There are exactly four such things. A tool is
justified only if it does at least one; if it does none, it's overkill.

| # | The need | Plain Claude | A tool here |
|---|---|---|---|
| 1 | **Persist state across sessions** | ❌ forgets between chats | ✅ your library in `state.json` |
| 2 | **Cause a side effect / durable artifact** | ❌ can't write files | ✅ `export_markdown` writes + returns a reading list |
| 3 | **Access private / live data** | ❌ doesn't know your books | ✅ reads your local seed + state |
| 4 | **Compute something exact** | ❌ hand-waves arithmetic | ✅ `top_genres`, `rating_by_genre`, `pace_to_goal` |

When you add or change a tool, ask which of the four it serves. If the answer is
"none — Claude already does this well," it probably shouldn't be a tool. A
`get_book_title(id)` would fail the test (no persistence, no artifact, no exact
math) — which is *why it isn't here*. Knowing what to leave out is the test
working.

## The ingest ladder (and why the model is the real importer)

Three tools add books, deliberately split by **scale and source**:

| Scale | Source | Tool |
|---|---|---|
| One book | "I read X" / a photo of one cover | `add_book` |
| A handful | a shelf photo, "I read X, Y, and Z" | `add_books` |
| A back-catalog | a Goodreads "Export Library" CSV | `import_goodreads_csv` |

The key design point: **the importer isn't a paste format — it's the model.** For
a photographed shelf, *Claude's vision* extracts the rows and calls `add_books`;
the server never touches the image. For natural language, Claude parses the
sentence. Only the bulk CSV path uses a deterministic parser, because you don't
want the model hand-parsing hundreds of rows. All three funnel into one
dedupe-and-persist sink (`store.add_books`).

(Goodreads has no genre field — genre is derived from your shelves, lossy. That's
a real-world data-mapping compromise, documented in `core.parse_goodreads_csv`.)

## Using it for real (the seed is shared, not your data)

The 15 sample books live in a **read-only, committed seed file** so the repo always
demos clean. To actually adopt book-tracker, you don't delete that file — you stop
loading it for *your* library:

- **`reset_library`** — hides the samples and clears anything you've added; your
  starting point for a real library (then import or add).
- **`use_sample_library(enabled)`** — the reversible toggle behind it. Off = your
  books only; on = samples back. Stored as a flag in your `state.json`, so it never
  touches the seed file or anyone else's clone.

This is the right shape for "purge the demo data" generally: hide a shared,
read-only fixture via per-user state, rather than mutating the fixture.

## Architecture: pure core + thin adapters

The logic is pure and I/O-free, so it's all unit-tested without a runtime. Two
adapters (MCP server, CLI) wire the same functions to the outside world; one
module (`store.py`) is the *only* thing that touches the filesystem.

| Module | Role | Touches I/O? |
|---|---|---|
| `models.py` | dataclasses: `Book` + the shapes compute returns | no |
| `core.py` | filters, rankings, pace, the Goodreads CSV parser | no |
| `exports.py` | render a reading list to Markdown / text | no |
| `store.py` | JSON persistence: bundled seed + mutable state | **yes** |
| `server.py` | MCP adapter (FastMCP), dual stdio/HTTP transport | via store |
| `cli.py` | CLI adapter | via store |

Keep new logic in the pure modules and test it directly; let the adapters stay
thin (parse args → call core → persist → return a dict).

## Run + test

```bash
pip install -e ".[test]"            # pytest + the MCP SDK
python -m pytest -q                 # full suite
ruff check .                        # if ruff is installed

# CLI — runs the whole flow without an MCP client (stdlib only):
PYTHONPATH=src python -m booktracker.cli top-genres
PYTHONPATH=src python -m booktracker.cli add "Babel" --author "R.F. Kuang" --genre Fantasy --status read --rating 5
PYTHONPATH=src python -m booktracker.cli summary
PYTHONPATH=src python -m booktracker.cli export

# MCP server — the only thing that needs a dependency:
PYTHONPATH=src python -m booktracker.server          # stdio (Claude Desktop)
PYTHONPATH=src python -m booktracker.server --http   # streamable-HTTP connector
```

Mutable state lives in `BOOKTRACKER_DATA_DIR` (default `~/.book-tracker`), not the
repo. Point it at a temp dir to experiment without touching real data:
`export BOOKTRACKER_DATA_DIR=/tmp/booktracker`.

## Design decisions (the patterns worth keeping)

- **Deterministic math in the data plane; the LLM narrates.** Counts, averages,
  and pace are exact functions — never left to the model. `rating_by_genre`
  deliberately returns the sample `count` alongside the average, so the model can
  say "highest-rated, but on one book" instead of overclaiming.
- **Inject the clock, keep the core pure.** `pace_to_goal` takes `as_of_month` as
  an argument rather than reading today's date, so it's deterministic and
  testable; the adapter supplies the real month.
- **Bundled seed vs. mutable state, kept apart.** The seed ships read-only so the
  repo runs cold; your books/goals/reports go in a gitignored `state.json`.
  Finishing a *seed* book records a status overlay, since the seed can't be edited.
- **Server-side I/O degrades gracefully for remote callers.** `export_markdown`
  returns the rendered content inline (not just a path) and defaults to a known
  data-dir location, not the process cwd. The importer takes pasted CSV *text*,
  not a server-side file path, for the same reason.
- **Dual transport from one codebase.** `_resolve_transport` is factored out of
  `main()` so transport selection is testable without binding a port.
- **Tool-layer integration tests, not just helper unit tests.** `test_core.py`
  covers the pure functions; `test_server_tools.py` drives the actual tool surface
  in-process against a sandboxed data dir (round-trip, dedupe, overlay, export).

## A data-shape assumption to retire before it bites

`load_books` reads the whole seed + state into memory and every tool operates on
the full list. Correct while a personal library is small. If this grew to tens of
thousands of books, the in-memory scan would get slow — a regression that ships
with no code change. When that becomes plausible, index or page, and write the
assumption down as an expiring contract ("valid while a library fits in memory").

## Good first extensions

1. **`rate_book`** — change a rating after the fact (mirror `mark_status`).
2. **`remove_book`** — delete from state.
3. **A StoryGraph CSV importer** — same shape as the Goodreads one, different
   columns.
4. **`recommend_next`** — pick from your to-read pile in your top-read genre
   (a deterministic filter, not a search).
