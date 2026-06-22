# Failure-mode catalog

A cross-project registry of **classes of bugs to watch for** — the
shared brain behind two consumers:

- a **hook** auto-runs the `grep`-able rules on code change (and nudges
  the review), and
- a **`/failure-scan` skill** runs the judgment-class review against
  this file on demand.

This file can grow without bloating any session's context (only a
one-line pointer lives in global `CLAUDE.md`; the hook/skill read this
file on demand).

## How to add a class

Copy the entry template below. The one decision that routes everything:

> **Is the danger in the code's *shape* or in its *behavior/data*?**
> - In the **shape** (a recognizable construct, or a missing one, you
>   can match from source text) → **grep-able** → give it a `Signature`
>   and it feeds the **hook**.
> - In the **behavior/data/meaning** (only catchable by reasoning or
>   running it) → **judgment** → no signature; it feeds the **skill**.

Detectability tiers:
- `hook` — strong textual signature, auto-flag every time.
- `hook (flag-for-review)` — a smell you can grep, but a human/Claude
  must confirm it's real.
- `judgment` — no signature; review-only.

### Entry template

```
## <kebab-id>: <name>
- **Detectability:** hook | hook (flag-for-review) | judgment
- **Smell:** the assumption or anti-pattern, in one line.
- **Signature:** grep/AST rule, or "none — behavioral".
- **Verify:** how to confirm it's a real instance.
- **Fix pattern:** the right response.
- **Origin:** where it bit (optional, keeps it concrete).
```

---

## silent-data-growth: Silent regression from data/scale growth
- **Detectability:** hook
- **Smell:** Code whose correctness depends on an *implicit, unstated
  assumption about data shape/volume* ("fits in one page", "small
  enough to X without Y") that silently becomes false as data grows —
  no code change, no error, just wrong output.
- **Signature:** file contains `ScanCommand` | `\.scan\(` |
  `FilterExpression` **and** lacks `LastEvaluatedKey` |
  `ExclusiveStartKey` (pagination) → flag. Also flag comments matching
  `small enough to .* without` / `1 (round-trip|page)` / `well under
  \d+ ?KB`. (Heuristic — warn, don't block; false positives are fine.)
- **Verify:** Is there a written upper bound + expiry condition? Does a
  test exercise pagination with a larger fixture? Does anything catch
  the cutover at runtime?
- **Fix pattern:** Paginate (`LastEvaluatedKey` loop) OR move to a
  keyed Query/GSI so size doesn't matter. Treat any "fits in one X"
  as an **expiring contract**, not a fact — comment *when* it expires.
  Add a runtime canary asserting non-empty output. (Three-layer
  defense: comment / paginated-fixture test / canary.)
- **Origin:** MM `getParkRides` — single-page Scan+Filter; table grew
  past 1MB as WAIT# rows accumulated; first page stopped containing
  STATE rows; returned `[]`; pages showed "0 attractions" silently for
  ~7 days. Lesson: moved too fast past an unexamined assumption —
  slow down and check the design.

## plausible-but-wrong-ai: Plausible-but-wrong LLM output
- **Detectability:** judgment
- **Smell:** Agent/LLM output that *looks* reasonable but is subtly
  wrong — silently dropped a constraint, ignored calibration data,
  wrong entity, missed a factor. Code-level tests don't catch
  behavioral drift.
- **Signature:** none — behavioral.
- **Verify:** Run the behavioral eval suite. Did a tool docstring /
  prompt change without re-running evals? Does the output honor every
  stated constraint?
- **Fix pattern:** **Deterministic core, narrating model** — compute in
  code, let the model narrate, don't let it do the math. Add an eval
  case per new behavior. **Never change a tool docstring without
  running evals** (the docstring is the runtime contract).
- **Origin:** MM MCP planner — natural-language plans that read fine
  while silently dropping constraints; `mcp/evals/` exists for exactly
  this category.

## dispatch-order-coupling: Implicit coordination via dispatch order
- **Detectability:** judgment
- **Smell:** Multiple sources can fire for the same entity/event, and
  the *order they run* silently decides the outcome — coordinated by
  ad-hoc "skip if already handled" checks instead of an explicit rule.
- **Signature:** none — behavioral. (A skip-check like
  `if already-handled: continue` near dispatch/send/notify code is a
  hint, but confirming requires reasoning about which sources can fire
  for the same target — a regex can't see that.)
- **Verify:** Is there an explicit priority/resolver, or does behavior
  depend on which branch happens to run first?
- **Fix pattern:** Explicit-priority **resolver**: each source
  contributes a candidate with a priority; one place picks the
  highest-priority candidate per target. Adding a source = new priority
  constant + appended candidate, not a new skip-check.
- **Origin:** MM `alert_routing.py` — favorite vs active-plan alerts for
  the same ride/user; rewritten from `if user in set: continue` to a
  candidate→resolver model.

## segment-stat-bias: Biased per-segment statistics
- **Detectability:** judgment
- **Smell:** A statistic computed **per user / per segment / per
  bucket** gets distorted by small or uneven sample sizes — or is made
  personal when the underlying quantity is actually *objective* and
  would be better estimated universally.
- **Signature:** none — semantic (depends on data distribution).
- **Verify:** What are the per-segment sample sizes? Is `n` + a
  confidence surfaced? Is "per-user" justified, or is the quantity
  objective (→ estimate it universally)? Are buckets hiding a
  sample-size cliff?
- **Fix pattern:** Prefer **universal/objective** estimates where the
  quantity is objective; **layer** context (per-park/season/weather) as
  adjustments rather than slicing into thin per-segment buckets;
  always surface `n` and confidence; guard small-`n`.
- **Origin:** MM calibration — per-ride wait-time bias modeled per-user
  when wait time is objective (and per-user starves on sample size);
  logged as a design-improvement item.

## stated-not-derived-doc-facts: Stated-not-derived doc facts
- **Detectability:** hook (flag-for-review)
- **Smell:** A volatile fact stated in prose (a count, a version, an
  "N passing" claim) silently drifts out of sync with the code it
  describes, because nothing ties the claim to its source. No error —
  the doc just reads authoritative while being wrong.
- **Signature:** a number in docs (`README.md` / `CLAUDE.md` /
  `SKILL.md`) sitting next to a volatile noun —
  `\(\d+\)` or `\d+ (tools?|tests?|cases?|passed)` near
  `tool|test|case|eval` — with **no** test that re-derives it
  (no `test_readme`-style guard reading the source). The number is
  greppable, but confirming nothing pins it needs a look →
  flag-for-review.
- **Verify:** Is the fact generated at render time, pinned by a test
  that re-derives it from the code, or hand-typed prose? Hand-typed
  and unpinned → real instance.
- **Fix pattern:** **Pinned, derived, or deleted — never just stated**
  (same triage as protected coverage). Pin it with a test that
  re-derives the fact from the source (README tool-count ==
  `@mcp.tool()` count, with the heading-reworded failure guarded too);
  or generate the line from the source; or, if it isn't worth a test,
  delete the claim from the prose. A volatile fact with no enforcement
  is an **expiring contract**, not a fact.
- **Origin:** mood-mixer README "27 tests", MM `CLAUDE.md` "5 eval
  cases", the scaffold `SKILL.md` "expect 49 passed" — all silently
  stale from ordinary work. Now pinned by `test_readme.py`
  (book-tracker), which goes red on drift instead of lying.

## parallel-without-independence: Fan-out over non-independent items
- **Detectability:** judgment
- **Smell:** Work is split across parallel subagents (or parallel
  tasks) for speed, but the items aren't actually independent — they
  share a file, a counter, an ordering, or coordinate via "skip if
  already handled". The fan-out races or double-acts and the result is
  silently wrong; the wall-clock win hides the correctness loss.
- **Signature:** none — behavioral, and it lives in the *plan*, not the
  code. The tell is a fan-out justified only by "it's faster" with no
  stated reason the items can't interfere. (Closely related to
  dispatch-order-coupling, one level up: there the coordination is
  implicit within one process; here it's across parallel workers.)
- **Verify:** Can you state in one sentence *why* these items are
  independent — no shared mutable state, no ordering, no implicit
  coordination? If two of them ran at the exact same instant, would the
  outcome still be correct?
- **Fix pattern:** **Independence is a claim you must defend, not a
  default.** If you can defend it, fan out. If you can't, model the
  dependency explicitly — an ordered `pipeline()` (stages, not a
  barrier), worktree isolation for parallel file mutations, or just stay
  inline. Speed never licenses parallelism over coupled work.
- **Origin:** the `/orchestrate` advisor + subagent-nudge hook — the
  guard that keeps "this is parallelizable" honest rather than merely
  enthusiastic.

## context-doc-bloat: Auto-loaded context file grows unbounded
- **Detectability:** hook (flag-for-review)
- **Smell:** `CLAUDE.md` (or `AGENTS.md`) — injected into context *every
  session* — only ever grows. Each session appends guidance; reference
  material, restated lessons, and stale facts accumulate because nothing
  re-evaluates the file. The signal (the directives that matter) drowns in
  bulk, and every line is paid for on every session.
- **Signature:** a context file over its line budget (~200), or an edit that
  *adds* a substantial block (≥~10 lines) to one. Greppable that something
  grew; whether it *should* have is judgment → flag-for-review.
- **Verify:** Is each section an *always-relevant directive*, or *reference*
  that's only sometimes needed? Could the newest addition fold into a section
  already there? Is every volatile fact still true?
- **Fix pattern:** **CLAUDE.md is the index; skills are the chapters.** Keep
  only always-relevant directives; move reference-grade content to a skill that
  loads on-demand (replace it with a one-line pointer); archive genuinely stale
  guidance to `CLAUDE.archive.md` (not auto-loaded) rather than deleting.
  Prevention beats cure — when *adding* reference, make it a skill instead of an
  append. The `/claude-md-audit` skill + `claude-md-curator` hook enforce this.
- **Origin:** an MM `CLAUDE.md` drifted to 232 lines with a thrice-restated
  lesson and a stale `~22 tools` (really 28); trimmed to 191 once a human
  looked. Related: stated-not-derived-doc-facts (the per-fact version).

## memory-index-overflow: Auto-memory index silently truncated at load
- **Detectability:** hook (flag-for-review)
- **Smell:** Claude Code auto memory's `MEMORY.md` loads only its **first 200
  lines / 25 KB** each session — content past that is silently NOT loaded. Claude
  writes this file itself across sessions, so it grows without anyone deciding
  to; once it crosses the cutoff, the tail entries are inert "memories" that
  look stored but never reach context. A hard truncation, not a soft budget —
  the same shape as a scan that silently drops rows past the first page.
- **Signature:** an edited `MEMORY.md` (in a `memory/` dir, canonically
  `~/.claude/projects/<project>/memory/`) over 200 lines or 25 KB. Greppable
  that it's over; which entries to keep vs demote is judgment → flag-for-review.
- **Verify:** Which entries currently fall past line 200 / 25 KB (i.e. aren't
  loaded right now)? Is `MEMORY.md` a lean index, or is detail inflating it?
- **Fix pattern:** **MEMORY.md is the index; topic files are the chapters.** Keep
  MEMORY.md to one-line pointers under the cutoff; move detail into topic files
  (uncapped, load on-demand); drop stale entries; reconcile contradictions. The
  `/memory-audit` skill + `memory-curator` hook enforce this.
- **Origin:** the auto-memory twin of context-doc-bloat — same index/chapters
  cure, but MEMORY.md *truncates* at load where CLAUDE.md only dilutes.
