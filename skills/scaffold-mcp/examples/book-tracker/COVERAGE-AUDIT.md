# Coverage audit: book-tracker

Audited 2026-06-12 · 49 tests, all passing (0.84s) · line coverage via local
`.venv` (pytest-cov) · no evals/paid-API suites present (cost guard: n/a).

## Checklist
- [x] empty: zero-state covered only indirectly — `use_sample_library(False)` exercises an empty library once; no direct `reading_summary([])` / `top_genres([])` / fresh-store asserts. Minor.
- [x] boundary: rating bounds tested far from the edge (99), never at 0/1/5/6 — `models.py:33` executes but the boundary values themselves are unpinned. `as_of_month` clamp unexercised.
- [x] error: findings #2, #3, #5 — corrupt `state.json` is unhandled AND untested; importer malformed-row branches (`core.py:220,238,260`) and tool-boundary error returns (`server.py:54,211,214`; `store.py:229`) written but never executed.
- [x] scale: no pagination loops (in-memory by design, documented as an expiring contract in CLAUDE.md) — but `record_export` (`store.py:302-304`) appends full report content to `state.json` forever: unbounded growth, no cap, no test. Finding #4.
- [x] time: core is exemplary (`as_of_month` injected). Adapter defaults read the clock directly (`store.py:236`, `server.py:215,253`, `cli.py:61,146`) and the mark-status test computes `date.today()` at runtime — midnight-flaky. Finding #6.
- [x] adapters: `cli.py` 0% (154 stmts — the documented no-MCP demo path), and three server tool wrappers never invoked (`server.py:175,182,190`). Findings #1 (wrappers) and #5 (CLI).
- [x] cant-fail: `tests/test_server_imports.py:21` checks `hasattr(server, name)` — passes even with the `@mcp.tool()` decorator deleted, since the bare function remains a module attribute. The suite's only registration guard cannot go red. Finding #1.

## Per-module coverage
| module | stmts | line cov | tests touching it |
|---|---|---|---|
| `core.py` | 121 | 97% | 14 direct (`test_core.py`) + indirect |
| `server.py` | 119 | 89% | 31 (`test_server_tools.py`) + 4 import smoke |
| `store.py` | 176 | 97% | indirect via server tests |
| `models.py` | 64 | 97% | indirect |
| `exports.py` | 27 | 100% | indirect via export tests |
| `cli.py` | 154 | **0%** | none |
| **TOTAL** | 662 | **73%** (≈95% excluding the CLI) | 49 |

## Verdict: RED
By the rubric's second clause: **a can't-fail test is standing guard over a
real contract.** The `hasattr` registration check is the suite's only guard
on the MCP tool surface — the contract a connected Claude actually consumes —
and it survives deletion of the registration itself. Everything else here is
AMBER-shaped (real gaps, mostly loud-failure paths); this one finding is what
tips it. It is also a minutes-long fix (see additions).

## Top gaps (ranked by silent-failure risk)
1. **Registration guard can't fail + three tool wrappers never invoked** —
   `tests/test_server_imports.py:21`, `server.py:175,182,190`. Delete a
   decorator or typo a response key in `rating_by_genre`/`top_authors`/
   `books_by_month` and the suite stays green while the live tool surface is
   broken or missing. *Closes it:* enumerate FastMCP's actual registered
   tools (`await mcp.list_tools()`) and assert names + docstrings; add one
   in-process call per untested wrapper asserting a real key.
2. **Corrupt `state.json` is unhandled and untested** — `store.load_state`
   does bare `json.loads`; a truncated write bricks every tool with a raw
   `JSONDecodeError`. *Closes it:* one corrupt-file fixture in `tmp_path` +
   decide the behavior (error dict beats stack trace at a tool boundary).
3. **Goodreads importer is happy-path only** — `core.py:220` (malformed date
   → None), `:238` (empty-title skip), `:260` ("Uncategorized" default) all
   dark; a header-less CSV silently yields `{"parsed": 0}`, unverified. This
   is the highest-variance real-user input in the system. *Closes it:* one
   messy-CSV fixture exercising all three branches + a no-headers case.
4. **`record_export` grows `state.json` without bound** — `store.py:302-304`
   appends full report content on every export, forever — a silent
   data-growth regression in miniature, in the repo that teaches the
   pattern. *Closes it:* a test pinning a cap/truncation decision.
5. **CLI adapter fully dark** — `cli.py` 0%, including `cmd_import_goodreads`
   (the only file-reading ingest) and `SystemExit` paths. Breaks loudly for
   a human, invisibly for CI. *Closes it:* 3–4 `cli.main([...])` + capsys
   smoke tests on the existing sandboxed-data-dir fixture.
6. **Adapter clock reads** — `store.py:236`, `server.py:215`; the
   mark-status test asserts runtime `date.today()` (midnight-flaky), and the
   default-today branches are themselves uncovered. *Closes it:* thread an
   optional `today=` through the two adapter defaults, pin it in tests.

## Cheapest high-value additions
- **Registration test that can fail:** assert the name set from
  `mcp.list_tools()` (not `hasattr`) and that every tool has a docstring —
  ~10 lines, converts the RED to AMBER on its own.
- **Corrupt-state fixture:** write `"{not json"` to the sandboxed
  `state.json`, call any tool, assert the chosen behavior — one test.
- **CLI smoke trio:** `main(["summary"])`, `main(["add", ...])`,
  `main(["import-goodreads", fixture])` with capsys on the existing env
  fixture — covers most of the 154 dark statements in minutes.

## Strengths
- **Tool-layer tests are real integration tests** — 31 in-process calls
  against sandboxed state covering validation rejection, dedupe,
  copy-on-write overlay semantics, tombstone reversibility, and export
  path-traversal confinement (`test_export_rejects_path_outside_data_dir`).
- **The pure core was designed for testability and the tests cash it in** —
  injected `as_of_month`, frozen dataclasses, exact pinned values
  (`avg_rating == 4.36`), tie-breaks and sample-size-carry asserted
  explicitly.
- **Sandboxing is airtight** — every write-path test runs against
  `tmp_path` via the env-var seam; tests are order-independent and cannot
  touch `~/.book-tracker`.
