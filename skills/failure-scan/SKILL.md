---
name: failure-scan
description: Review the current code changes (the git diff, or named files) against the failure-mode catalog — especially the judgment classes a hook can't catch (plausible-but-wrong AI/LLM output, biased per-segment statistics, implicit coordination via dispatch order). Use when finishing a change, before committing, or when the failure-mode hook nudges you. Reports concrete risks with the catalog's verify questions and fix patterns.
---

# /failure-scan

Review the current changes against the **failure-mode catalog** and report
any bug class this change plausibly exhibits. The PostToolUse hook already
auto-flags the *grep-able* classes (e.g. silent-data-growth). Your job is the
**judgment classes a regex can't catch** — while still sanity-checking the
grep-able ones in context.

## 1. Load the catalog (the single source of bug classes)

Find and read `catalog.md`. Try, in order:
1. `~/.claude/failure-modes/catalog.md` (standalone install)
2. the installed-plugin copy:
   `find ~/.claude/plugins -path '*failure-modes/catalog.md' 2>/dev/null`
3. a repo-vendored copy: `failure-modes/catalog.md` under the project root.

Read the **whole** catalog so you have every class, its smell, its **Verify**
questions, and its **Fix pattern**. If you genuinely can't find it, say so and
fall back to the four seeded classes named in this skill's description.

## 2. Decide what to review

- **Default:** the uncommitted work — `git diff HEAD` plus `git diff --staged`.
  If both are empty, diff against the default branch (`git diff main...HEAD`)
  or the last commit (`git show`).
- **If the user named files/paths** in the invocation, review those instead.
- State the scope you reviewed (diff range or file list) up front.

## 3. Review against every class — judgment classes hardest

For each class in the catalog, decide whether this change plausibly exhibits
it, using that class's **Verify** questions as your rubric. Weigh hardest:

- **plausible-but-wrong-ai** — any LLM/agent/tool/prompt change: silently
  dropped constraints, a **tool docstring or prompt changed without running
  evals**, output that reads fine but could be subtly wrong.
- **segment-stat-bias** — a statistic computed per-user / per-segment on small
  or uneven samples, or an *objective* quantity modeled per-segment when it
  could be universal.
- **dispatch-order-coupling** — multiple sources can fire for one target,
  coordinated by ad-hoc "skip if already handled" checks rather than an
  explicit priority resolver.

Rules for the review itself:
- Be **concrete**: cite `file:line` and quote the relevant code.
- Grade each finding: **confirmed** / **worth a look** / **checked — clear**.
- **Do not invent issues to seem thorough.** A calm "nothing here" is a valid,
  valuable result — manufacturing findings is itself the plausible-but-wrong
  failure mode, applied to you.
- If a class doesn't apply, dismiss it in a few words ("n/a — no LLM surface").

## 4. Report

For each flagged class:
- **Class** — and where (`file:line`).
- **Why** it might be an instance (1–2 lines, grounded in the code).
- **Fix pattern** — quoted from the catalog entry.

End with a one-line verdict: *clear*, or *N issues worth addressing*. Honest
and specific beats exhaustive.
