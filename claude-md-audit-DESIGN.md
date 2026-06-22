# claude-md-audit — design note

**Status:** DESIGN, not built. 2026-06-22

A `claude-md-curator` hook + `/claude-md-audit` skill that keep a `CLAUDE.md`
lean, current, and non-redundant — auditing it when it grows and archiving
(not deleting) what no longer earns its session-start cost.

## 1. Problem / motivation

`CLAUDE.md` is injected verbatim into context every session, but **nothing
ever re-evaluates it.** It only grows: each session appends guidance, and
stale facts, redundant restatements, and no-longer-useful sections accumulate
silently. Observed live this session — a real MM `CLAUDE.md` had drifted to
232 lines with a lesson stated three different ways and a `~22 tools` fact
that was actually 28; both sat unflagged until a human happened to look.

Cost of the rot is real and compounding: a bloated context file is more
tokens every session, harder to keep honest, and the signal (the rules that
matter) drowns in restatement. The community guideline of **≤~200 lines**
exists for exactly this reason. Nothing today watches for it.

## 2. Core reframe

**A hook can't audit prose — judgment isn't deterministic.** "Could this be
more concise / is it still true / does this duplicate what's above" is LLM
reasoning, not a regex. So the audit *cannot* live in the hook. The hook's
only honest job is the **mechanical** part (did `CLAUDE.md` change? how long
is it now?) and to **nudge** the judgment engine. The judgment lives in a
skill. (Toolkit's established nudge-hook + judgment-skill split — same as
coverage-nudge → /coverage-audit.)

Second insight (sharpened by the standing directive *"Keep CLAUDE.md under 200
lines; move reference material to skills, which load on-demand"*): **CLAUDE.md
should hold only always-relevant *directives* — conditionally-relevant
*reference* belongs in a skill.** That reframes demotion as a **three-way
triage**, not delete-vs-keep:

1. **Keep & tighten** — a real every-session directive; stays, just made concise.
2. **Extract to a skill** — still useful but *reference-grade* (a war story, how
   to run a suite, operational detail). Move it into a skill that loads
   on-demand; replace it in `CLAUDE.md` with a one-line pointer. This is the
   **primary release valve** — it preserves the content *and* makes it
   actionable when relevant, at zero per-session cost.
3. **Archive** — genuinely stale / no-longer-useful. Move to `CLAUDE.archive.md`
   (not auto-loaded; re-read only at audit time) rather than deleting, so the
   fear of "what if I need it" never blocks a cut.

The line budget is the forcing function; skill-extraction is what makes living
under it sustainable instead of just lossy.

## 3. The design — options with tradeoffs

### Where the judgment runs
- **A. All in a hook (regex).** Rejected — can't judge concision/currency;
  would only ever do line-count, missing the whole point.
- **B. All in a skill, no hook.** Honest audit, but the user must remember to
  run it — and a file that silently grows is exactly what you forget to check.
- **C. Hook nudges, skill judges (RECOMMENDED).** Hook catches the edit + does
  line-count cheaply and points at the skill; skill does the real evaluation.
  Gets "noticed automatically" *and* "judged properly."

### Two moments to intervene — prevent, then cure
The cheapest bloat to remove is the bloat that never lands. So the tool acts at
**two** moments, not one:
- **At add-time (preventive — the higher-value one).** When an edit *adds* a
  substantial block to `CLAUDE.md`, the hook nudges Claude to ask, before moving
  on: *is this a directive, or reference?* If reference, **suggest creating a
  skill instead of the append** — i.e., don't just clean it up later, question
  whether it belonged in `CLAUDE.md` at all. The hook detects "a sizable block
  was just added" (cheap: size of the edit's `new_string`); Claude/skill makes
  the directive-vs-reference call. This is the ounce of prevention.
- **On growth (curative).** The periodic/over-budget audit triages what's
  *already* there (keep/extract/archive). The backstop for what slipped past
  add-time or predates the tool.

Both routes share one engine — the directive-vs-reference judgment and the
"extract to a skill" mechanic are identical; only the trigger differs.

### Audit cadence (the key tradeoff)
The deep audit is LLM work — it costs tokens every run. So:
- **Every edit → full audit.** Rejected: a full re-read on every keystroke-
  edit is wasteful and nags.
- **On-demand only.** Cheap but back to "you forget."
- **Tiered (RECOMMENDED):** the hook *always* reports the new line count
  (~free) and fires a **full-audit nudge only when over the ~200-line budget,
  or once per session** (re-arming on a new session). You get continuous cheap
  awareness; the expensive pass is gated to when it's worth it.

### Where demoted content goes (the three-way triage)
- **Delete outright.** Rejected as the default — loses recoverability, so cuts
  don't get approved.
- **Extract to a skill (RECOMMENDED for *useful* reference).** Per the directive:
  reference-grade content (war stories, how-to-run-X, operational detail) becomes
  an on-demand skill; `CLAUDE.md` keeps a one-line pointer. Zero per-session cost,
  and the content is now *invoked when relevant* instead of always present or
  buried. The audit proposes the skill name + the pointer line; creates the skill
  only on approval.
- **Archive to `CLAUDE.archive.md` (for *stale* content).** Not auto-loaded;
  re-read only at audit time, so it can be resurrected or permanently dropped.
  The safety net for "probably dead but don't delete yet."

The skill judges *which bucket* each demotable section belongs in — extract
(still useful, conditional) vs archive (stale) — and says why.

### What the skill evaluates (per section)
concision (with the suggested rewrite) · currency (facts vs the repo —
counts, versions, paths) · usefulness (does it still earn session-start cost) ·
redundancy (overlap with another section, **and whether the newest addition
duplicates existing guidance or could fold into a rewrite**) · total length vs
budget, with what to cut to get under. Output is a report → on the user's
approval, apply tightening/merges and move demoted sections to the archive
with a dated "archived because…" note.

## 4. Edge cases

- **The newest addition is the redundant one.** The headline ask: when a
  section was just appended, check it against the *existing* file first — it
  may already be covered, or belong folded into a section above. The hook
  passes "what changed" (edit `new_string`) so the skill can prioritize it.
- **Auditing must never auto-edit.** Applying changes to `CLAUDE.md` (or
  archiving) happens **only on explicit approval** — same advise→offer→execute
  discipline as /orchestrate. An unattended hook must not rewrite the file.
- **Don't nag mid-curation.** When the *skill itself* edits `CLAUDE.md`, the
  hook will fire on that write — must not re-nudge a fresh audit. Debounce
  must survive the skill's own edits (session-scoped flag, set before write).
- **Archive must not be auto-loaded.** Verify the filename isn't one the
  harness injects (`CLAUDE.md`/`CLAUDE.local.md`/`AGENTS.md`). `CLAUDE.archive.md`
  is safe; document that it must stay out of the auto-load set.
- **Multiple CLAUDE.md files / nested.** A repo can have several (root +
  subdirs) + the global `~/.claude/CLAUDE.md`. Scope the hook to the edited
  path; don't assume one canonical file.
- **Stale-fact verification needs the repo.** "Is `~22 tools` current" requires
  reading source. The skill can do targeted checks (tool count, versions); be
  honest when a fact can't be cheaply verified rather than guessing.
- **Empty / tiny file.** A 20-line `CLAUDE.md` needs no audit — the budget
  nudge stays silent well under 200; don't manufacture suggestions.

## 5. Open questions (decide at build time)

- **Line budget number** — 200 as the default? Make it a
  `CLAUDE_MD_LINE_BUDGET` env override.
- **Counting lines vs tokens** — lines are the cited guideline and trivial to
  measure; tokens are truer to context cost. Start with lines; note tokens as
  a future refinement.
- **Archive format** — flat append with dated headers, or mirror the source
  section structure? Lean flat-append with provenance.
- **Does the skill self-verify currency** by reading the repo, or only flag
  "looks like a volatile fact, confirm it"? Lean: targeted checks where cheap
  (counts/versions), flag-for-review otherwise.
- **AGENTS.md scope** — include now or CLAUDE.md-only for v1? Lean: both, since
  both are auto-loaded and the logic is identical.

## 6. Rollout / cost

- Ships in the public `claude-code-toolkit` (new hook dir + skill + hooks.json
  wiring + README + version bump). No deploy.
- **Main risk = nag/noise** eroding trust in the toolkit's hook family. Mitigate
  with the tiered cadence, the once-per-session debounce, the
  `CLAUDE_MD_AUDIT_DISABLED` switch, and never auto-editing.
- **Token cost** of the audit is the real ongoing cost; the tiered gate is what
  keeps it proportional. `log`/note when an audit is heavy.
- Pairs with (does not duplicate) the narrower `stated-not-derived-doc-facts`
  per-edit flagger: this is the holistic, on-growth health pass; that is the
  per-edit fact catch. Cross-link both in the catalog/README.
