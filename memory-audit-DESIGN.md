# memory-audit — design note

**Status:** DESIGN, not built. 2026-06-22

A `memory-curator` hook + `/memory-audit` skill — the auto-memory twin of the
CLAUDE.md curator. Keep `MEMORY.md` a lean index under the load cutoff, with
detail in on-demand topic files.

## 1. Problem / motivation

Claude Code's **auto memory** (`~/.claude/projects/<project>/memory/`) is a
`MEMORY.md` index plus topic files. Per the docs, **only the first 200 lines /
25 KB of `MEMORY.md` load each session — content past that is silently not
loaded.** That's the same shape as the MM `getParkRides` bug: it works until the
file grows, then quietly drops the tail with no error. Worse, *Claude writes
this file itself* across sessions, so it grows without anyone deciding to grow
it; the dropped entries are memories you thought were active.

Nothing watches it. The toolkit guards CLAUDE.md (curator/audit) but auto memory
— same index/chapters shape, same silent-overflow risk, plus staleness and
contradiction as notes accumulate — has no guardian.

## 2. Core reframe

**It's the CLAUDE.md curator problem on a second surface — with a *hard* cutoff
instead of a soft budget.** CLAUDE.md over 200 lines still loads fully (just
dilutes); `MEMORY.md` over 200 lines / 25 KB **actually truncates** at load.
So the line count isn't advice here — it's the boundary between "remembered" and
"silently forgotten." The hook's mechanical check is therefore higher-stakes,
and the skill's job is the same triage we already know: lean index ↔ on-demand
topic files, drop the stale.

Reuse, don't reinvent: this is `claude-md-audit` pointed at a different dir with
a truncating budget. Same nudge-hook + judgment-skill pattern.

## 3. The design — options with tradeoffs

### Build new vs extend claude-md-audit
- **Extend `/claude-md-audit` to also handle memory.** Less surface, but
  conflates two distinct files, mechanics (soft budget vs hard truncation), and
  triggers (CLAUDE.md edits vs memory-dir edits). Muddies both.
- **A dedicated `memory-curator` hook + `/memory-audit` skill (RECOMMENDED).**
  Mirrors the toolkit's one-pair-per-surface shape; each stays single-purpose.
  Shares *principles* (index/chapters) without sharing code paths that would
  have to branch on file type anyway.

### What the hook checks (mechanical only)
- Fires on PostToolUse `Edit|Write|MultiEdit` whose path is inside a memory dir
  and basename is `MEMORY.md`.
- **Truncation warning:** `MEMORY.md` > `MEMORY_LINE_BUDGET` (default 200) OR
  > 25 KB on disk → "entries past the cutoff are silently NOT loaded next
  session; run `/memory-audit`." Debounced once per session.
- It does **not** judge content (that's the skill). It does **not** edit.

### What the skill does (judgment)
Reads `MEMORY.md` + topic files and reports:
- **Below the cutoff** — exactly which entries currently fall past line 200 /
  25 KB (i.e. silently dropped *right now*). Highest-value finding.
- **Staleness** — entries describing code/paths/facts that have drifted.
- **Redundancy / contradiction** — duplicate or conflicting notes (Claude wrote
  these incrementally; contradiction is likely).
- **Index↔topic split** — is `MEMORY.md` a lean index, or is detail that belongs
  in a topic file inflating it?
On approval: tighten `MEMORY.md` to a pure index, move detail into topic files
(creating them), drop stale entries. Never auto-edits without approval.

## 4. Edge cases

- **False `MEMORY.md` match.** A repo file coincidentally named `MEMORY.md`
  isn't auto memory. Gate on the path looking like an auto-memory dir — the
  parent dir is `memory/` AND (path contains `/.claude/projects/` OR a sibling
  layout that matches). Prefer a conservative path check; when unsure, stay
  silent (fail toward quiet).
- **Bytes vs lines.** The cutoff is *whichever comes first* (200 lines OR 25 KB).
  A file under 200 lines can still exceed 25 KB with long lines — check both.
- **The skill's own edits re-trigger the hook.** Curating `MEMORY.md` is an
  edit → would re-nudge. Debounce per session (set before the skill writes), as
  the claude-md curator does.
- **Topic files aren't budget-bound.** Only `MEMORY.md` truncates at load; topic
  files load on-demand in full. So the hook warns only on `MEMORY.md`, not on
  topic-file edits — moving detail *out* of the index is the fix, not a problem.
- **Auto memory may be off / dir absent.** If there's no memory dir, nothing to
  do — the hook simply never matches.
- **Don't double-count the index vs the load rule.** The harness loads the first
  200 lines of `MEMORY.md` specifically (not the whole memory dir), so "over
  budget" is strictly a `MEMORY.md` property.

## 5. Open questions (decide at build time)

- **Budget knobs:** `MEMORY_LINE_BUDGET` (200) and a byte budget (25 KB) —
  expose both as env? Lean yes, mirroring `CLAUDE_MD_LINE_BUDGET`.
- **Memory-dir detection:** how strict? Lean: basename `MEMORY.md` AND an
  ancestor path segment `memory` (covers the documented
  `~/.claude/projects/<project>/memory/` and a custom `autoMemoryDirectory`),
  but not a bare repo `MEMORY.md`. Confirm against false positives in tests.
- **Should the skill also flag CLAUDE.md↔memory contradictions?** Both load
  every session and can conflict. Tempting, but that's the separate
  cross-file-conflicts idea; keep this skill memory-only for v1.
- **Does the hook fire on topic-file edits at all?** Lean: no — only `MEMORY.md`
  has the cutoff. Topic edits are silent.

## 6. Rollout / cost

- Ships in the public `claude-code-toolkit` (new hook dir + skill + hooks.json
  wiring + catalog entry + README + version bump). No deploy.
- **Risk = noise**, mitigated as with the other hooks: only fires on `MEMORY.md`
  over budget, debounced, `MEMORY_AUDIT_DISABLED` switch, never auto-edits,
  fail-open. Naturally low-frequency (memory edits are infrequent).
- New `memory-index-overflow` catalog entry, sibling of `context-doc-bloat`;
  cross-link both (CLAUDE.md soft budget vs MEMORY.md hard cutoff).
- This is the 5th nudge-hook + judgment-skill pair; keep each high-signal so the
  family stays trusted.
