# Coverage audit: book-tracker

Audited 2026-06-12 · 60 tests, all passing (0.93s) · line coverage via local
`.venv` (pytest-cov) · no evals/paid-API suites present (cost guard: n/a).
**Re-audit after closing gaps 1, 2, 4, 5 from the same-day first audit**
(directed by Megan; original findings preserved below for the record).

## Checklist
- [x] empty: zero-state covered only indirectly — `use_sample_library(False)` exercises an empty library once; no direct `reading_summary([])` / `top_genres([])` asserts. Minor, unchanged.
- [x] boundary: rating bounds still tested far from the edge (99, plus the new CLI exit test), never at 0/1/5/6 — `models.py:33` executes but the boundary values are unpinned. Open (gap 7).
- [x] error: corrupt `state.json` now fails soft (moved aside to `.json.corrupt`, library preserved) and is TESTED. Importer malformed-row branches (`core.py:220,238,260`) remain dark — open (gap 3). Tool-boundary error returns `server.py:54,211,214` still unexercised (minor).
- [x] scale: `record_export` now logs `{title, path}` metadata only — the unbounded content-append is gone and the new shape is pinned by test. No pagination loops (in-memory by design, documented expiring contract).
- [x] time: core exemplary (`as_of_month` injected). Adapter clock reads remain (`store.py:~240`, `server.py:215,253`, `cli.py:61,146`) and the mark-status test still computes `date.today()` at runtime — open (gap 6).
- [x] adapters: CLI 0% → **73%** via 6 smoke tests (`tests/test_cli.py`) covering summary, top-genres, add→list round-trip, invalid-rating exit, import, export. The three previously-uninvoked tool wrappers now have in-process tests. Remaining CLI dark lines are per-command print formatting (pace, by-month, edit/delete/samples) — acceptable.
- [x] cant-fail: FIXED — registration is now asserted against `mcp.list_tools()` (names + docstrings), and was **proven red** with a decorator removed, then green restored. No other can't-fail patterns found in the suite.

## Per-module coverage
| module | stmts | line cov (was) | tests touching it |
|---|---|---|---|
| `core.py` | 121 | 97% (97%) | 14 direct + indirect |
| `server.py` | 119 | 92% (89%) | 34 tool tests + 4 import/registration |
| `store.py` | 180 | 97% (97%) | indirect + corrupt-state + export-metadata |
| `models.py` | 64 | 97% (97%) | indirect |
| `exports.py` | 27 | 100% (100%) | indirect |
| `cli.py` | 154 | **73% (0%)** | 6 smoke tests (`test_cli.py`) |
| **TOTAL** | 666 | **91% (73%)** | **60 (was 49)** |

## Verdict: AMBER (was RED)
The RED finding — a can't-fail `hasattr` test standing guard over the MCP
tool contract — is fixed and was proven able to fail. Remaining gaps are
real but loud-failure or low-variance: no silent failure stands on a
relied-upon path.

## Top gaps (open; ranked by silent-failure risk)
3. **Goodreads importer is happy-path only** — `core.py:220` (malformed date
   → None), `:238` (empty-title skip), `:260` ("Uncategorized" default)
   still dark; a header-less CSV silently parses to zero rows, unverified.
   *Closes it:* one messy-CSV fixture exercising all three branches + a
   no-headers case.
6. **Adapter clock reads** — `store.py:~240`, `server.py:215`; the
   mark-status test asserts runtime `date.today()` (midnight-flaky).
   *Closes it:* thread an optional `today=` through the two adapter
   defaults and pin it.
7. **Boundary minutiae** — rating tested at 99, not at 0/1/5/6;
   `as_of_month` clamp unexercised. Brief, low risk.

## Closed this round (2026-06-12, directed)
1. ✅ Registration test that can fail (`mcp.list_tools()` + docstring check;
   proven red once) + in-process tests for `rating_by_genre`/`top_authors`/
   `books_by_month`.
2. ✅ Corrupt `state.json` fails soft: moved aside to `state.json.corrupt`
   (user data preserved), tools continue on fresh state; pinned by test.
4. ✅ `record_export` stores `{title, path}` metadata only — nothing ever
   read the stored content, and it grew `state.json` without bound. Pinned.
5. ✅ CLI adapter smoke suite (6 tests, 0% → 73%).

## Cheapest high-value additions (next round)
- **Messy-CSV importer fixture** — malformed date + empty title + no-shelf
  rows in one file, assert parsed/skipped counts and the "Uncategorized"
  default — one fixture, one test, closes gap 3.
- **`today=` seam at the two adapter defaults** — small signature thread,
  kills the midnight-flaky assert, closes gap 6.
- **Rating boundary quartet** — `0/1/5/6` through `add_book`, four asserts,
  closes gap 7.

## Strengths
- **Tool-layer tests are real integration tests** — now 34 in-process calls
  covering validation rejection, dedupe, copy-on-write overlay semantics,
  tombstone reversibility, export path confinement, corrupt-state fail-soft,
  and export-metadata shape.
- **The registration test asks FastMCP, not the module namespace** — and the
  suite's history now includes proof it can go red.
- **Sandboxing is airtight** — every write-path test (server AND the new CLI
  suite) runs against `tmp_path` via the env-var seam.
- **The pure core was designed for testability** — injected `as_of_month`,
  frozen dataclasses, exact pinned values, tie-breaks asserted explicitly.
