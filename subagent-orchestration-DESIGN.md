# Subagent-orchestration advisor — design note

**Status:** DESIGN, not built. 2026-06-21

A `subagent-nudge` hook + `/orchestrate` skill that help pick a *good* use of
subagents — and, on go-ahead, kick it off.

## 1. Problem / motivation

Claude Code already has the *mechanisms* for delegation (the Agent tool —
Explore/Plan/general-purpose/custom types — and the Workflow tool for
deterministic fan-out) and is *prompted* to use them. But there is **no
proactive advisor**: nothing detects "this task is subagent-shaped" and
surfaces it, and the decision logic for *when fan-out beats inline* lives
implicitly in the model's head, not in anything inspectable, reusable, or
tunable.

For a solo dev that means good delegation depends on the model noticing in the
moment — easy to miss on a task framed as one big thing (e.g. "audit the whole
analytics layer"). The cost of missing isn't a crash; it's a slower, shallower,
single-threaded pass where parallel readers or a verify-after-find pipeline
would have been better.

## 2. Core reframe

**The scarce thing isn't a way to run subagents — it's the judgment of whether
to, and which shape.** So the deliverable is an *advisor*, not another runner.
And: **a skill the user won't proactively call is dead weight** — so the
advisor's primary entry point must be a hook that fires on its own, with the
skill as the engine behind it (and also directly invocable). This is the
toolkit's existing `coverage-nudge → /coverage-audit` pattern, third instance.

Corollary that shapes everything: **the load-bearing assumption of all
parallelism is item independence.** The advisor's real failure mode is nudging
toward fan-out for work that *looks* independent but shares state/ordering
(races, wrong results). So an independence guard is not a nicety — it's the
thing that makes the advice honest instead of merely enthusiastic.

## 3. The design — options with tradeoffs

### Granularity of the decision tree
- **A. Flat 3 (inline / single-agent / fan-out).** Easy to scan; throws away
  the actual value — "fan-out" doesn't say *pipeline vs loop-until-dry vs
  judge-panel vs adversarial-verify*.
- **B. Flat 5–7 patterns.** Precise but hard to scan and maintain.
- **C. 2-level (RECOMMENDED).** Top level for the quick call
  (`inline` → `single agent` → `multi-agent`); second level only if
  multi-agent — the pattern selector (parallel-read / worktree-mutate /
  pipeline / loop-until-dry / adversarial-verify / judge-panel). Fast altitude
  *and* a precise pattern; stays legible as patterns are added.

**Why C:** progressive disclosure — most tasks resolve at level 1; only the
genuinely-parallel ones pay for the pattern selector.

### Entry point: hook vs skill vs both
- **Skill only.** Inspectable, safe — but the user won't invoke it
  proactively, so it rarely fires. Rejected as primary.
- **Hook only.** Fires automatically — but a hook can't run a multi-step
  analysis or offer/execute; it can only nudge.
- **Both, composed (RECOMMENDED).** Hook (UserPromptSubmit, pure-regex,
  conservative) detects a subagent-shaped prompt and its `additionalContext`
  tells Claude to run the `/orchestrate` analysis. Skill is the engine: the
  2-level tree, and the advise→offer→execute flow. User calls nothing; the hook
  notices and offers.

### Execution model of the skill
- **Print-only.** Safe, but dead-ends at a recommendation.
- **Advise → offer → execute on go-ahead (RECOMMENDED).** Always prints the
  recommendation + a ready-to-run Agent/Workflow snippet; if there's a clear
  actionable shape, ends by offering to run it; kicks off **only** on explicit
  go-ahead. Human gate preserved; not dead-ended.

## 4. Edge cases

- **Looks-independent-but-isn't** (the big one) — items share a file, a
  counter, or dispatch order. *Independence guard:* the skill must state *why*
  the items are independent before recommending fan-out; if it can't, it
  recommends a pipeline or inline instead. Cross-linked to a new
  `parallel-without-independence` failure-modes catalog entry.
- **Nag fatigue** — UserPromptSubmit fires every prompt. Debounce: nudge once
  per session, re-arm if usage pattern resets (model on context-alert's state
  approach). Plus `SUBAGENT_NUDGE_DISABLED` to silence entirely.
- **Crying wolf on small tasks** — a prompt says "audit" but touches one file.
  Triggers stay conservative and the nudge is *flag-for-review* ("this *might*
  parallelize; if items aren't independent, ignore"), never prescriptive.
- **Workflow opt-in reality** — fan-out via the Workflow tool needs explicit
  user opt-in and can burn many tokens. The skill must surface the rough cost
  and the opt-in requirement, not silently assume it.
- **Latency** — the hook must add ~no latency before the turn: pure regex, no
  LLM call, fail-open exit 0 on any error (toolkit hook convention).
- **Hook can't see the repo cheaply** — detection is prompt-text-only by
  design; it does not scan the filesystem. Accept lower precision for speed.

## 5. Open questions (decide at build time)

- **Trigger lexicon** — exact regex set ("audit", "across the (whole )?codebase",
  "for (each|every)", "find all", "comprehensive|exhaustive", "migrate every",
  enumerated multi-target lists). Start narrow; widen only if it under-fires.
- **Debounce window** — once per session vs re-arm on a new distinct trigger.
  Lean once-per-session for v1.
- **Does the skill emit a runnable snippet or a prose plan?** Lean: both — prose
  recommendation + a copy-paste Agent/Workflow snippet.
- **Where the skill executes** — for the "execute on go-ahead" path, does it hand
  back a Workflow script for the main loop to run, or invoke Agent directly?
  Likely: print the snippet; the main loop runs it (keeps the skill advisory).

## 6. Rollout / cost

- Outward-facing only in that it ships in the public toolkit (a new hook +
  skill + catalog entry + version bump). No deploy.
- **Risk:** an over-eager hook is *noise*, which erodes trust in the whole
  toolkit's nudge family. Mitigation is the conservative triggers + disable
  switch + flag-for-review framing above; ship it muted-by-default-ish (narrow
  triggers) and widen based on real use.
- New `parallel-without-independence` catalog entry must land with the feature
  so the independence guard has something to cross-link.
- Bump `plugin.json` and update the `hooks/hooks.json` UserPromptSubmit array
  (alongside context-alert). Confirm the failure-mode + context-alert nudges
  don't stack confusingly on the same prompt.
