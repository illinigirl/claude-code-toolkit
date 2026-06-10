# book-tracker

A self-contained [MCP](https://modelcontextprotocol.io) server for your reading
log — in the **pure-core + thin-adapters** shape: a deterministic data plane
(exact compute over your books, persisted state, a durable export) that Claude
narrates. No cloud, no API keys, no database. Clone it and it runs.

It's the **worked example** of the [`scaffold-mcp`](../../SKILL.md) pattern — what
the generic scaffold looks like after you grow it into a real domain.

```bash
pip install -e ".[test]" && python -m pytest -q
PYTHONPATH=src python -m booktracker.cli top-genres     # the one-line insight
PYTHONPATH=src python -m booktracker.cli by-month
```

```
Genres you read most:

  Fantasy          4
  Science Fiction  3
  Mystery          2
  Literary         1
  Nonfiction       1

→ You read Fantasy most (4 books).
```

## Why an MCP (and not just asking Claude)?

A tool only earns its place if it does something the model *can't*. There are
exactly four such things, and this server demonstrates all four:

| Need | Plain Claude | This server |
|---|---|---|
| Remember your library across chats | ❌ no memory | ✅ persistent `state.json` |
| Produce a reading list you can keep | ❌ can't write files | ✅ `export_markdown` (file + inline) |
| Work over *your* books | ❌ doesn't know them | ✅ local seed + state |
| Count genres / average ratings exactly | ❌ hand-waves the math | ✅ deterministic compute |

The model does the *creative / conversational* part — choosing what to say,
parsing what you photographed or typed; the server supplies the memory, the
artifact, the private data, and the exact arithmetic.

## Try asking it

Once it's connected to Claude, these are the kinds of things you can ask in plain
language — Claude picks the right tool and narrates the result:

**Insights**
- *"What genres do I read most?"*
- *"Which genres do I rate the highest?"*
- *"What months do I read the most?"*
- *"Am I on pace for my reading goal this year?"*

**Find things**
- *"Show me everything I've read by Ursula K. Le Guin."*
- *"What's in my to-read pile?"*

**Add or import**
- *"I just finished Babel by R.F. Kuang — five stars."*
- *"Here's my Goodreads export — import it."* (paste the CSV)
- *"Add this one"* — with a photo of the cover (Claude's vision reads title + author)

**Fix or remove**
- *"That's not History — Babel is Fantasy."* (Claude guessed the genre; correct it)
- *"Bump Dune to five stars."*
- *"Drop The Silmarillion from my list."*

**Make something / start fresh**
- *"Make me a shareable reading list."*
- *"Clear the samples — I want to start my own library."*

## The tools (17)

**Ingest — a ladder by scale, all funneling into one dedupe-and-persist sink:**

- **`add_book`** — one book ("I just finished X", or snap its cover).
- **`add_books`** — a handful, as rows. The sink for a photographed shelf
  (Claude's *vision* extracts the rows) or a natural-language list.
- **`import_goodreads_csv`** — your whole back-catalog from a Goodreads
  "Export Library" CSV. Photo/NL don't scale to a decade of reading; the export
  does. Parsed deterministically (you don't want the model hand-parsing 300 rows).

> **The realistic import mechanism is the model, not a format.** Talk to it,
> photograph a shelf, or paste a CSV — all three are "the model parses the messy
> input; the tool persists it exactly." That division of labor is the point.

**Persist / update:** `mark_status` (to-read → reading → read; marking read
stamps the finish date so it counts toward your goal), `update_book`
(fix any field — the genre Claude guessed, a rating, a title), `delete_book`
(drop one book), `set_goal`. `mark_status` is just the common case of `update_book`.

**Compute (exact — the model narrates, never calculates):** `top_genres`,
`rating_by_genre` (carries sample size — a 5.0 over one book isn't a 4.75 over
four), `top_authors`, `books_by_month` (seasonality), `reading_summary`,
`pace_to_goal`.

**Filter:** `find_books` — one parameterized lookup ('all fantasy', 'by Le Guin',
'my to-read pile', 'rated 4+') instead of four near-identical tools.

**Artifact:** `export_markdown` — a reading list, written to disk *and* returned
inline (so a remote caller who can't read the server's disk still gets it).

**Make it your own:** `use_sample_library` (show/hide the bundled samples —
reversible; *"stop using the sample library"*), `reset_library` (adopt it for real:
hide the samples and clear anything you added).

## Use it for real

It clones populated with 15 sample books so every tool returns something cold.
When you want it to be **your** library, clear the samples and start from your own:

```bash
PYTHONPATH=src python -m booktracker.cli reset          # hide samples + clear added books
PYTHONPATH=src python -m booktracker.cli import-goodreads ~/Downloads/goodreads_library_export.csv
# ...or just start adding. Bring the samples back any time:
PYTHONPATH=src python -m booktracker.cli samples on
```

From Claude it's the same, conversationally: *"stop using the sample library and
import my Goodreads export"* → `reset_library` + `import_goodreads_csv`.

## Architecture

Pure core + thin adapters. All logic is I/O-free and unit-tested without a
runtime; the MCP server and the CLI are two adapters over the same functions, and
one module does all the file I/O.

```
src/booktracker/
  models.py    Book + the typed shapes compute returns          (pure)
  core.py      filters, rankings, pace, the CSV parser           (pure)
  exports.py   Markdown / text reading-list rendering            (pure)
  store.py     JSON persistence: seed + mutable state        (the only I/O)
  server.py    MCP adapter (FastMCP), dual stdio/HTTP transport
  cli.py       CLI adapter — runs the whole thing without an MCP client
  data/booktracker.seed.json   bundled starter library (ships inside the package)
```

The seed ships inside the package (resolved via importlib.resources, so a
non-editable install finds it too); your added books, edits, deletions, goals, and reports
live in a gitignored `state.json` under `~/.book-tracker/` — real data never lands
in a commit. The seed is immutable, so editing a *seed* book uses **copy-on-write**:
the first edit copies that record into your state and your copy wins thereafter;
deleting one records a tombstone the loader filters out. One overlay mechanism for
every mutation — `mark_status` is just `update_book` changing the status (and
stamping `finished` when a book becomes read).

## Use it from Claude

Two transports from one codebase — stdio for a local Claude Desktop subprocess,
or streamable-HTTP so it can be added as a remote *custom connector* by URL.

**Local (stdio) — Claude Desktop.** After `pip install -e .`:

```json
{
  "mcpServers": {
    "book-tracker": { "command": "/path/to/book-tracker/.venv/bin/book-tracker" }
  }
}
```

**As a custom connector (HTTP).**

```bash
book-tracker --http --port 8765          # or BOOKTRACKER_HTTP=1
# then add http://localhost:8765/mcp as a custom connector
```

## Drive it from the CLI (no MCP client needed)

```bash
PYTHONPATH=src python -m booktracker.cli top-genres
PYTHONPATH=src python -m booktracker.cli by-month
PYTHONPATH=src python -m booktracker.cli pace
PYTHONPATH=src python -m booktracker.cli summary
PYTHONPATH=src python -m booktracker.cli list --genre fantasy
PYTHONPATH=src python -m booktracker.cli add "Babel" --author "R.F. Kuang" --genre Fantasy --status read --rating 5
PYTHONPATH=src python -m booktracker.cli export
```

## License

[MIT](LICENSE).
