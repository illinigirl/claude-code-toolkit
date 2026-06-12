# Coverage audit: book-tracker

Audited 2026-06-12 · 71 tests, all passing (0.90s) · ruff clean · line
coverage via local `.venv` (pytest-cov) · no evals/paid-API suites present
(cost guard: n/a). **Third pass same-day: round 1 found, round 2 closed gaps
1/2/4/5, this round closed 3/6/7 + the residuals.** History preserved below.

## Checklist
- [x] empty: closed — direct asserts for `reading_summary([])`, `top_genres([])`, `top_authors([])`, `books_by_month([])`, plus the no-finished-books and seed-hidden tool paths.
- [x] boundary: closed — rating validated AT the edges (0/1/5/6 through `add_book`), `as_of_month` clamp pinned at 0→1 and 13→12.
- [x] error: closed — corrupt `state.json` fails soft (tested, file preserved); importer survives messy rows (unparseable date → None, empty title skipped, "Uncategorized" fallback, header-less CSV → `[]`); tool-boundary errors pinned (title required, no-finished-books, no-goal-for-year, invalid status, non-numeric rating).
- [x] scale: closed — `record_export` logs `{title, path}` only (the unbounded content-append is gone, shape pinned). No pagination loops (in-memory by design, documented expiring contract in CLAUDE.md).
- [x] time: closed — clock reads factored to seams (`store._today_iso`, `server._today`) and the formerly midnight-flaky mark-status test now pins both. CLI's two `date.today()` reads remain but no test asserts against runtime dates.
- [x] adapters: smoke tests on both — 6 CLI tests (`test_cli.py`, 0% → 73%; remaining dark lines are print formatting in pace/by-month/edit/delete/samples/reset) and every tool wrapper now invoked in-process. `server.main()` transport binding (285-291, 295) untested by design — `_resolve_transport` is the factored, tested decision logic.
- [x] cant-fail: closed — registration asserted via `mcp.list_tools()` (names + docstrings), proven red once with a decorator removed. Dead `core.book_index` (dark because unreachable) deleted rather than tested.

## Per-module coverage
| module | stmts | line cov (first audit) | tests touching it |
|---|---|---|---|
| `core.py` | 119 | **100%** (97%) | 20 direct + indirect |
| `server.py` | 121 | 94% (89%) | 40+ tool tests + registration |
| `store.py` | 182 | **100%** (97%) | direct + indirect |
| `models.py` | 64 | **100%** (97%) | via validation tests |
| `exports.py` | 27 | 100% (100%) | indirect |
| `cli.py` | 154 | 73% (**0%**) | 6 smoke tests |
| **TOTAL** | 668 | **93%** (73%) | **71** (was 49) |

## Verdict: GREEN (was RED → AMBER → GREEN, all 2026-06-12)
No checklist dimension is dark on a relied-upon path; both adapters have
smoke tests; no can't-fail tests remain (and the registration test has been
red once — proven able to fail). Honest residuals, accepted on the record:
`main()` transport binding (by design), CLI print formatting in non-smoked
commands, and the CLI's two unpinned clock reads (no test depends on them).

## Closed across the three passes (directed by Megan)
1. ✅ Registration test asks FastMCP (`mcp.list_tools()` + docstrings; proven
   red) + in-process tests for the three uninvoked wrappers.
2. ✅ Corrupt `state.json` fails soft — moved aside to `.json.corrupt`, library
   preserved, tools continue; pinned.
3. ✅ Importer beyond the happy path — messy-CSV fixture (malformed date,
   empty title, no shelf, non-numeric pages/rating) + header-less CSV → `[]`.
4. ✅ `record_export` stores `{title, path}` metadata only (nothing read the
   content; it grew `state.json` unbounded). Design call: Megan.
5. ✅ CLI smoke suite (6 tests, 0% → 73%).
6. ✅ Clock seams (`_today_iso` / `_today`) + de-flaked the mark-status test.
7. ✅ Rating boundaries 0/1/5/6 + `as_of_month` clamp at both edges.
   Plus residuals: empty-state asserts, tool error returns, numeric-string
   coercion, `BOOKTRACKER_SEED` override, non-numeric rating message, dead
   `book_index` removed.

## Cheapest high-value additions (if ever wanted)
- Smoke the remaining CLI commands (pace, by-month, edit, delete, samples,
  reset) — same pattern as `test_cli.py`, ~6 more tests, mostly print
  formatting.
- Route the CLI's two `date.today()` reads through a seam if a date-asserting
  CLI test ever lands.

## Strengths
- **Every pure module at 100% with behavioral assertions** — exact pinned
  values, tie-breaks, sample-size-carry, clamps at both edges, messy-input
  contracts. Not line-coverage padding.
- **The registration test asks FastMCP, not the module namespace** — and has
  been proven red. The tool contract is genuinely guarded.
- **Failure semantics are design decisions, tested as such** — corrupt state
  preserves the user's file; the importer degrades row-by-row; export logs
  metadata because nothing reads content. Each carries a docstring saying why.
- **Sandboxing is airtight** — server AND CLI suites run against `tmp_path`
  via the env seam; the clock is pinnable at both adapter seams.
