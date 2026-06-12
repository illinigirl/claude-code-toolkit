---
name: coverage-audit
description: Audit a project's test coverage for NEGATIVE SPACE — run line coverage, then judge the misses against a checklist of the gaps agent-written suites predictably leave (empty/degenerate, boundary, error paths, scale/pagination, time-dependence, untested adapters, tests that can't fail). Reports per-module coverage, the top gaps ranked by silent-failure risk, and the cheapest high-value tests to add, with a GREEN/AMBER/RED verdict. Use when checking whether coverage kept up with the code, after the coverage-nudge hook fires, or before calling a surface ship-ready. Complements verify-mcp ("verify proves it runs; coverage-audit proves it's protected").
argument-hint: "[project-dir]"
---

# /coverage-audit

Line coverage tells you what *executed*; this skill judges what's *protected*.
The premise (validated empirically across several agent-built repos): coverage
written without direction has a predictable fingerprint — pure cores near 100%,
while the same five gaps recur everywhere. Your job is to run real coverage,
then read the misses against that fingerprint and report the negative space,
ranked by where a silent failure would hurt most.

**This is an audit, not a code review.** Don't critique style or design; report
what is and isn't protected, and what one would add first.

## 1. Locate and size up the project

- Target dir = the first argument, or the current working directory.
- Python: a `pyproject.toml` / `pytest.ini` / `tests/` dir. Web: a
  `package.json` with vitest/jest. Audit every tested surface you find; if a
  surface has zero tests at all, that's finding #1, not a reason to stop.
- **Cost guard:** look for eval/behavioral suites that call paid APIs (an
  `evals/` dir, Anthropic/OpenAI clients in test deps). NEVER run those —
  count their cases by reading them, and say you did.

## 2. Run line coverage (local env only)

Python (reuse the project's venv; never install anything globally):

```bash
cd <project-dir>
.venv/bin/pip install -q pytest-cov 2>/dev/null || pip install -q pytest-cov  # venv-local only
.venv/bin/python -m pytest -q --cov=src --cov-report=term-missing
```

- Adjust `--cov=src` to the actual package layout (`--cov=<pkg>` for flat
  layouts). Capture the per-module table AND the missed line numbers — the
  judgment pass needs them.
- Web: `pnpm vitest run --coverage` if `@vitest/coverage-v8` is present;
  otherwise count tests per source module by reading test files and say
  line coverage wasn't configured.
- If there's no clean way to run coverage, don't contort the environment —
  fall back to inventory-by-reading (source modules vs test files) and mark
  the report as qualitative.

## 3. The judgment pass — read the misses against the checklist

For each dimension, combine the coverage misses with targeted reading/grep.
Cite `file:line` for every finding.

- **Empty / degenerate:** do tests pass `[]`, `0`, empty state, a fresh/blank
  store? Read the test files; absence of any zero-state test on a public
  function is a finding.
- **Boundary:** limits and off-by-one edges — 0/1/exactly-at-cap, validation
  bounds tested at the boundary (not just at 99 when the limit is 5).
- **Error paths:** map missed lines onto `except`/`raise`/fallback branches
  (`grep -n "except\|raise" <module>` and intersect with the missed ranges).
  Defensive code that has never executed in a test is unverified handling —
  flag especially: corrupt state/JSON guards, external-API failure fallbacks,
  malformed-input rows. Also flag *unhandled* obvious errors at tool/adapter
  boundaries (e.g. `date.fromisoformat(user_input)` with no guard).
- **Scale / pagination:** grep source for pagination/chunk loops
  (`LastEvaluatedKey|ExclusiveStartKey|next_page|cursor|offset|while.*page|
  [0:100]`-style chunking). For each, check whether ANY test forces more than
  one page/chunk (stubs that always return a single page hide multi-page bugs
  — the classic silent data-growth regression). Note fixture sizes vs
  realistic production sizes.
- **Time:** grep source for direct clock reads (`datetime.now|date.today|
  time.time|Date.now`). In pure logic, each is a testability finding (inject
  the clock); at adapters, check the default-today paths are themselves
  covered. Tests that compute "today" at runtime are midnight-flaky — flag.
- **Adapters:** CLI modules and server/tool wiring at 0% or near it. Pure-core
  coverage does not protect argparse plumbing, tool registration, or output
  formatting. A documented demo path with zero tests ranks high.
- **Tests that can't fail:** scan test files for asserts that survive removal
  of the behavior — `hasattr(...)` registration checks (a plain function
  still has the attribute after the decorator is deleted), tests with no
  assert, asserts on the stub instead of the code. A test that has never
  been red protects nothing.

## 4. Rank by silent-failure risk

Order findings by **how quietly the failure ships**, not by coverage points:

1. Plausible-but-wrong output on a path someone relies on (wrong data that
   renders fine; a contract another process/consumer reads).
2. Dark code on the production path (the seam to the real world: API wire
   format, hydration joins, file formats an external daemon parses).
3. Unexercised error handling that will eventually run for the first time
   in production.
4. Untested adapters (breaks loudly for a human, but invisibly to CI).
5. Boundary minutiae (note briefly; don't pad the report).

## 5. Report

Write the report to **`COVERAGE-AUDIT.md` in the project root** — the name
and location matter: the coverage-nudge hook keys staleness off this exact
file (its mtime vs. source changes), so writing it re-arms the automation
and silences stale notices. Step 6 validates the file. (Use a temp file
only if the user explicitly doesn't want the artifact — and say that this
disables staleness tracking. The file is a local artifact; suggest adding
it to `.gitignore` if the user doesn't want audits committed.)

```
# Coverage audit: <project>

## Checklist
- [x] empty: <finding refs, or "checked — none found: <what you looked at>">
- [x] boundary: <...>
- [x] error: <...>
- [x] scale: <...>
- [x] time: <...>
- [x] adapters: <...>
- [x] cant-fail: <...>

## Per-module coverage
| module | stmts | line cov | tests touching it |

## Verdict: GREEN / AMBER / RED
- GREEN: no checklist dimension is dark on a relied-upon path; adapters have
  at least smoke tests; no can't-fail tests found.
- AMBER: real gaps, but none where failure would be silent on a relied-upon
  path.
- RED: a relied-upon path runs on dark code, OR a can't-fail test is standing
  guard over a real contract.

## Top gaps (ranked by silent-failure risk)
1. <finding> — <file:line> — why it ships silently — the one test that closes it

## Cheapest high-value additions
- <3 concrete tests, each one sentence: the behavior to pin + the fixture trick>

## Strengths
- <what's genuinely well protected — be specific, not polite>
```

The "cheapest high-value additions" section is the point of the whole audit:
each entry should be addable in minutes (a `page_size` knob on an existing
stub, one `main([...])` + capsys smoke test, one corrupt-file fixture).

Percentages are detectors, not targets — never recommend chasing a number,
and never call a suite good because the number is high: a test that executes
lines while asserting nothing passes any gate. Judge protection, not
execution.

## 6. Prove the audit itself is complete (MANDATORY)

An audit that silently skipped a dimension reads exactly like a thorough one
— so completeness is enforced in code, not trusted. Run the validator that
ships with this skill against the report you just wrote:

```bash
python3 <this-skill-dir>/checklist.py <report-file>
```

- It fails unless ALL seven dimensions (`empty boundary error scale time
  adapters cant-fail`) appear as annotated `- [x] dim: ...` lines.
- If it fails, the audit is NOT done: go back to step 3, check the missing
  dimension for real, annotate the line, and re-run the validator.
- Include the validator's one-line output at the bottom of your summary to
  the user — it's the audit's own test, shown green.

"Checked — none found" is a perfectly good annotation; an absent line is
not. The difference between those two is the entire point of this step.
