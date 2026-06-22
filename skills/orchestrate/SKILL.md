---
name: orchestrate
description: Recommend a good use of subagents for a task — walk a 2-level decision tree (inline / single agent / multi-agent → pattern), explain why, hand back a ready-to-run Agent or Workflow snippet, and execute it only on the user's go-ahead. Use when a task looks broad or parallelizable ("audit/across the whole codebase", "for each X", "find all Y"), when the subagent-nudge hook fires, or whenever you're unsure whether to delegate and in what shape.
---

# /orchestrate

Decide whether a task warrants subagents and, if so, which **shape** — then
advise, offer, and (on go-ahead) run it. You are an *advisor*: the scarce thing
is the judgment, not another way to launch agents. Never fan out silently.

If invoked with a task, use it. If invoked bare, ask for the task in one line.

## The load-bearing rule (read first)

**Parallelism is only valid when the items are INDEPENDENT** — no shared
state, no ordering dependency, no implicit coordination (e.g. "skip if already
handled"). This is the #1 way orchestration goes wrong: work that *looks*
independent but isn't produces races and wrong results. So:

> Before recommending any fan-out, **state in one sentence why the items are
> independent.** If you can't, do NOT parallelize — use a pipeline (ordered
> stages) or stay inline. Cross-reference: `parallel-without-independence` in
> the failure-mode catalog.

## The decision tree

### Level 1 — the quick call

- **Gate 0 — is delegation even worth it?** Stay **inline (no subagent)** if the
  task touches ≤1–2 files you already know, is a single lookup, or is
  inherently sequential with tight feedback (debugging one stack trace).
  Delegation costs spin-up + context handoff + tokens — don't pay it for small
  or sequential work.
- **One bounded, single-perspective chunk that would just bloat your context?**
  → **a single general-purpose (or `Explore`) subagent.** Delegate to keep your
  own context clean; no fan-out.
- **Genuinely decomposable into many items / perspectives?** → **multi-agent**,
  go to Level 2.

### Level 2 — pick the multi-agent pattern

Walk these in order; take the first that fits:

1. **Known, independent, read-only** (search/understand many files)
   → **parallel `Explore` agents**, one per area.
2. **Known, independent, each MUTATES files** (could collide)
   → **Workflow**, `isolation: 'worktree'` per agent.
3. **Known items, multi-stage each** (find → verify → fix)
   → **Workflow `pipeline()`** — no barrier between stages.
4. **Unknown-size discovery** (find all bugs / every dead flag)
   → **loop-until-dry**: spawn finders until K consecutive empty rounds.
5. **A wrong answer is costly** (correctness / security)
   → **adversarial verify**: N skeptics per finding, kill on majority-refute
   (or perspective-diverse lenses if it can fail multiple ways).
6. **Wide solution space** ("best approach to X")
   → **judge panel**: N independent attempts → score → synthesize the winner.

Patterns compose (e.g. find → dedup → pipeline-verify). Prefer `pipeline()`
over a `parallel()` barrier unless a stage genuinely needs *all* prior results
at once (dedup/merge, early-exit on zero).

## Two checks to always surface

- **Independence** — the sentence above. No sentence, no fan-out.
- **Cost / opt-in** — anything using the **Workflow** tool needs the user's
  explicit opt-in and can burn many tokens (dozens of agents). Say so, with a
  rough scale ("~6 readers + a verify pass"), rather than assuming it's allowed.

## Output: advise → offer → execute

1. **Recommend** — name the Level-1 call and (if multi-agent) the pattern, in
   1–3 lines, with the independence sentence and a rough cost.
2. **Show the snippet** — a ready-to-run `Agent` call list, or a `Workflow`
   script, that implements the recommendation. Make it copy-paste real, not
   pseudocode.
3. **Offer** — end by asking whether to run it. **Execute only on an explicit
   go-ahead**; otherwise leave the snippet for the user to run or adjust.

If the honest answer is "this doesn't need subagents," say that plainly — a
calm "do this inline" is a valid, valuable result. Manufacturing a fan-out to
look sophisticated is itself a failure mode.
