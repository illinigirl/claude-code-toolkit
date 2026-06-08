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
- **Detectability:** hook (flag-for-review)
- **Smell:** Multiple sources can fire for the same entity/event, and
  the *order they run* silently decides the outcome — coordinated by
  ad-hoc "skip if already handled" checks instead of an explicit rule.
- **Signature:** `if .*(in|already).*: \s*continue` near dispatch/
  send/notify code; multiple senders writing to the same target. Flag
  for human confirmation — it's a smell, not a proof.
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
