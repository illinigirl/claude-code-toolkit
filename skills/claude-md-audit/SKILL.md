---
name: claude-md-audit
description: Audit a CLAUDE.md (or AGENTS.md) for health — concision, currency, usefulness, redundancy, and length vs a line budget — then, on approval, tighten it and move reference material to on-demand skills (and stale guidance to CLAUDE.archive.md) so it stays the lean index it should be. Use when the curator hook nudges, when a context file crosses its line budget, when an addition might already be covered, or whenever a CLAUDE.md feels long or stale.
---

# /claude-md-audit

Keep an auto-loaded context file lean and honest. **The principle:** CLAUDE.md
is the *index* — only always-relevant **directives** belong in it; conditionally-
relevant **reference** (war stories, how-to-run-X, operational detail) belongs in
a **skill** that loads on-demand. Every line costs tokens *every session*, and
nothing else re-evaluates this file — so the audit is the only thing keeping it
from growing forever.

You are an advisor: **report and propose, then apply only on the user's explicit
go-ahead. Never edit the file unprompted.**

## 1. Read the target(s)

Default to the `CLAUDE.md` for the current repo (and `~/.claude/CLAUDE.md` if the
user means the global one; ask only if ambiguous). Also read `CLAUDE.archive.md`
beside it if present (the cold-storage of previously demoted content). If the
curator hook passed *what was just added*, evaluate that block first.

State the file and its **line count vs the budget** (`CLAUDE_MD_LINE_BUDGET`,
default 200) up front.

## 2. Evaluate every section against five lenses

For each section / block:

- **Concision** — can it say the same in fewer lines? Draft the tighter version.
- **Currency** — is it still true *against the repo*? Volatile facts (tool/test/
  case counts, versions, file paths, dates) drift silently. Verify the cheap ones
  by reading the source (e.g. count `@mcp.tool()`); for the rest, flag
  "confirm — looks stale" rather than guessing. (See the
  `stated-not-derived-doc-facts` catalog entry.)
- **Usefulness** — does it still earn its session-start cost, or is it advice no
  one needs anymore?
- **Redundancy** — does it overlap another section? **And if it was just added:
  is it already covered above, or could it fold into an existing section** rather
  than stand alone?
- **Bucket** — for anything not staying as-is, which destination (next step)?

## 3. Triage each demotable section (the three-way call)

- **Keep & tighten** — a real, always-relevant directive. Stays; just made concise.
- **Extract to a skill** — still useful but *reference-grade*. Propose a skill
  name + a one-line pointer to replace it in CLAUDE.md. This is the **primary
  release valve**: the content survives and becomes *invoked when relevant*, at
  zero per-session cost.
- **Archive** — genuinely stale / superseded. Move to `CLAUDE.archive.md` with a
  dated `<!-- archived YYYY-MM-DD: why -->` note, not deleted, so it's recoverable.

Prefer **extract** over **archive** for anything still true and occasionally
useful — archiving is for what's probably dead.

## 4. Report, then (on approval) apply

Report: current vs projected line count, and a short table — section → verdict
(keep / tighten / extract→`skill-name` / archive) → one-line why. Lead with the
highest-value cuts.

**Only after the user agrees**, apply the approved changes:
- tighten/merge in place;
- for each **extract**: create the skill (`skills/<name>/SKILL.md`, with a
  description so it loads on-demand) and replace the section with its pointer;
- for each **archive**: append to `CLAUDE.archive.md` with the dated note and
  remove from CLAUDE.md.

Re-state the new line count. If the user declines a suggestion, leave it and
don't re-raise it this session.

## Notes

- **Don't manufacture cuts.** A file already under budget and current may need
  nothing — "it's healthy, N lines, nothing to do" is a valid result.
- **Archive is not auto-loaded** (it isn't named `CLAUDE.md`), so it costs no
  context; you only re-read it here. Surface anything in it that's now safe to
  delete permanently, or worth resurrecting.
- Pairs with the `claude-md-curator` hook (which nudges you here) and the
  `parallel`/`stated-not-derived` catalog discipline — same "pin it, derive it,
  or move it; don't let it rot" spirit.
