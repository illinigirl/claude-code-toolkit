---
name: claude-md-audit
description: Audit a CLAUDE.md (or AGENTS.md) for health — concision, currency, usefulness, redundancy, scope, and length vs a line budget — plus cross-file checks (contradictions between CLAUDE.md/rules that make Claude pick arbitrarily, dead .claude/rules path globs that silently never load, and directives a hook or skill now mechanically enforces). On approval, tighten it and move reference material to on-demand skills (stale guidance to CLAUDE.archive.md). Use when the curator or enforcement-nudge hook nudges, when a context file crosses its line budget, when an addition might already be covered, when instructions seem to conflict, when you just wrote a hook/skill that may mechanize a rule, or whenever a CLAUDE.md feels long or stale.
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

For the cross-file checks in step 2.5, also enumerate the *other* instruction
sources that share this session's context: parent-dir and nested `CLAUDE.md`
(loaded for the working tree), `~/.claude/CLAUDE.md`, and `.claude/rules/*.md`
(plus `~/.claude/rules/`). You don't need to deeply audit each, but you need
their content to spot contradictions and dead rules.

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
- **Scope** — is it in the right CLAUDE.md in the hierarchy? A *team/project
  convention* belongs in the project `./CLAUDE.md`; a *personal preference for
  all your projects* belongs in user `~/.claude/CLAUDE.md`; a *sandbox URL,
  personal test data, or anything secret* belongs in `./CLAUDE.local.md`
  (gitignored), never the committed file. Flag anything sitting in the wrong
  scope (e.g. a personal preference or a secret in the shared project file).
- **Bucket** — for anything not staying as-is, which destination (next step)?

## 2.5 Cross-file checks (the whole loaded set, not just one file)

Because every CLAUDE.md / rule in the hierarchy is concatenated into context,
two more silent failures live *between* files:

- **Contradictions.** If two instructions conflict (e.g. root says "use pnpm,"
  a nested file says "use npm"; or two files give different test commands),
  Claude picks one arbitrarily — a silent coin-flip. Compare the loaded set and
  flag every conflicting or divergent-duplicate pair, with a recommended
  resolution (usually: keep the most-specific/most-correct, delete the other).
  See the `conflicting-instructions` catalog entry.
- **Dead `.claude/rules/` globs.** A rule whose `paths:` frontmatter glob matches
  *no* file in the repo never loads — a silently inert rule (an expiring
  contract). For each path-scoped rule, check its globs still match something;
  flag the ones that don't (the glob drifted, or the code moved/was renamed).
- **Directives now mechanized by a hook or skill** (doc-vs-enforcement
  redundancy). When prose tells Claude to *do* (or *not do*) something that a
  hook now enforces, or that a skill now performs, the *mechanical* instruction
  is dead weight — the enforcement carries it every time, the prose only when
  this file happens to be in context. This is the redundancy the curator hook
  *can't* see: it fires on CLAUDE.md edits, but mechanization happens when you
  write the **hook/skill**, not the doc. Scan the enforcement surface —
  `.claude/skills/*/SKILL.md` (and plugin skills), and registered hooks
  (`settings.json` / `settings.local.json` `hooks`, `.claude/hooks/`, plugin
  `hooks.json`) — and match each against the directives here. For every match,
  the verdict is **condense to a pointer, NOT remove**: a hook/skill almost
  always enforces only the *mechanical half* (the "always paginate", the "run
  the audit") while the *judgment half* (the war story, the *why*, when to
  surface it) still earns its place. Replace the mechanical instruction with a
  one-line pointer at the enforcing hook/skill; keep the reasoning. Only delete
  outright if the line was *purely* mechanical with no judgment left once the
  enforcement exists.

## 3. Triage each demotable section

Each section that isn't staying as-is goes to one of these destinations:

- **Remove** — wrong or truly dead. Delete (the floor; prefer archive if unsure).
- **Condense** — keep, but say it in fewer lines (draft the tighter version).
- **Extract to a skill** — still useful but *reference-grade* and broadly
  relevant (a war story, how-to-run-X, a workflow). Propose a skill name + the
  one-line pointer that replaces it. The content survives and is *invoked when
  relevant*, at zero per-session cost.
- **Move to a nested CLAUDE.md** — *area-specific* guidance that **one directory
  owns** (conventions for `web/`, `mcp/`, `infra/`…). A nested `CLAUDE.md` loads
  on-demand when Claude works in that subtree. Propose the target dir + lines.
- **Move to a path-scoped rule** (`.claude/rules/<name>.md` with `paths:`
  frontmatter) — *area-specific* guidance that **follows a file type across
  directories**, where no single dir owns it (e.g. "all `*.test.*` must be able
  to fail," "every `**/dynamodb.ts` paginates its scans"). Loads when Claude
  touches a matching file anywhere. The deciding question: *does one directory
  own this, or does it follow a file type wherever it lives?* If you'd copy the
  same note into three subtrees, it's a rule, not a nested file. Propose the
  glob + lines. (`~/.claude/rules/` for a personal cross-project rule.)
- **Re-scope** — right content, wrong file: move a personal preference to user
  `~/.claude/CLAUDE.md`, or a sandbox URL / personal test data / secret to
  `./CLAUDE.local.md` (gitignored). A secret in a committed file is urgent —
  flag it loudly.
- **Archive** — genuinely stale / superseded but worth keeping. Append to
  `CLAUDE.archive.md` with a dated `<!-- archived YYYY-MM-DD: why -->` note (not
  auto-loaded; recoverable).

Routing rule of thumb: wrong scope (personal/secret in the shared file) →
**re-scope** first; still-true + *broadly* useful → **skill**; area-specific and
*one directory owns it* → **nested CLAUDE.md**; area-specific but *follows a file
type across dirs* → **path-scoped rule**; probably dead → **archive**; wrong →
**remove**.

## 4. Report, then (on approval) apply

Report: current vs projected line count, and a short table — section → verdict
(keep / condense / extract→`skill-name` / nest→`dir/CLAUDE.md` / rule→`glob` /
re-scope / archive / remove) → one-line why. Lead with the highest-value cuts.

**Only after the user agrees**, apply the approved changes:
- **condense**: tighten/merge in place;
- **extract**: create the skill (`skills/<name>/SKILL.md`, with a description so
  it loads on-demand) and replace the section with its pointer;
- **nest**: create/append the nested `dir/CLAUDE.md` and replace the section
  with a pointer to it;
- **rule**: create `.claude/rules/<name>.md` with `paths:` frontmatter for the
  glob and replace the section with a pointer;
- **archive**: append to `CLAUDE.archive.md` with the dated note;
- **remove**: delete.

Re-state the new line count. If the user declines a suggestion, leave it and
don't re-raise it this session.

## Notes

- **Don't manufacture cuts.** A file already under budget and current may need
  nothing — "it's healthy, N lines, nothing to do" is a valid result.
- **Don't split with `@import`.** `@path` imports load eagerly at launch (they
  cost context immediately) — they don't achieve on-demand loading. Use skills,
  nested CLAUDE.md, or `.claude/rules/` (all lazy) plus plain prose pointers.
  Per the docs, `<!-- HTML comments -->` in CLAUDE.md are stripped before
  context injection, so maintainer notes there are free.
- **Archive is not auto-loaded** (it isn't named `CLAUDE.md`), so it costs no
  context; you only re-read it here. Surface anything in it that's now safe to
  delete permanently, or worth resurrecting.
- Pairs with two hooks that nudge you here from opposite directions: the
  `claude-md-curator` hook (when you *edit* CLAUDE.md) and the
  `enforcement-nudge` hook (when you write a *hook/skill* that may mechanize a
  rule). Same "pin it, derive it, or move it; don't let it rot" spirit as the
  `parallel`/`stated-not-derived` catalog discipline.
