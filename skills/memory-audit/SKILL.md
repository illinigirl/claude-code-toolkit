---
name: memory-audit
description: Audit Claude Code's auto memory (MEMORY.md + topic files in ~/.claude/projects/<project>/memory/) for the load cutoff, staleness, redundancy/contradiction, and index↔topic split — then, on approval, tighten MEMORY.md to a lean index, move detail into on-demand topic files, and drop stale entries. Use when the memory-curator hook nudges, when MEMORY.md is over the ~200-line / 25KB load cutoff, or whenever auto memory feels bloated or out of date.
---

# /memory-audit

Keep Claude Code's **auto memory** healthy. Auto memory lives at
`~/.claude/projects/<project>/memory/` — a `MEMORY.md` index plus topic files.
**The principle is the same as CLAUDE.md: MEMORY.md is the index, topic files are
the chapters.** But MEMORY.md has a *hard* limit, not a soft one: **only its
first 200 lines / 25 KB load each session — anything past that is silently not
loaded.** Since Claude writes this file itself across sessions, it grows on its
own, and the dropped tail is memory you thought was active.

Advisor, not editor: **report, then apply only on the user's explicit go-ahead.
Never edit memory unprompted.**

## 1. Locate and read

Find the memory dir for this project: `~/.claude/projects/<project>/memory/`
(the `<project>` segment is derived from the git repo; or an
`autoMemoryDirectory` from settings). Read `MEMORY.md` and every topic file.
State `MEMORY.md`'s line count and byte size vs the cutoff
(`MEMORY_LINE_BUDGET` default 200, `MEMORY_BYTE_BUDGET` default 25 KB) up front.

## 2. Report (highest-value finding first)

- **Below the cutoff — silently dropped NOW.** If `MEMORY.md` exceeds 200 lines
  or 25 KB, name exactly which entries fall past the line — they are not loaded
  this session. This is the headline: those "memories" are currently inert.
- **Index↔topic split.** Is `MEMORY.md` a lean index of one-line pointers, or is
  detail that belongs in a topic file inflating it past the cutoff?
- **Staleness.** Entries describing code, paths, counts, or decisions that have
  since drifted (verify cheap ones against the repo; flag the rest).
- **Redundancy / contradiction.** Claude wrote these incrementally, so duplicate
  or *conflicting* notes are likely — flag both; conflicting memory is worse than
  none (Claude may act on the wrong one).

## 3. On approval, apply

- **Tighten** `MEMORY.md` to a pure index — one line per memory, pointing to its
  topic file (the format the harness expects: `MEMORY.md` tracks what's stored
  where).
- **Move detail** that inflated the index into the relevant topic file (create
  topic files as needed). Detail in topic files is uncapped and loads on-demand —
  so this is the fix for overflow, not a workaround.
- **Drop** stale entries; **reconcile** contradictions (keep the true one, delete
  or correct the other).
- Re-state the new `MEMORY.md` line/byte count — confirm it's back under the
  cutoff so nothing is silently dropped.

## Notes

- **Don't manufacture cuts.** A `MEMORY.md` under the cutoff and current may need
  nothing — say so.
- **Only `MEMORY.md` truncates.** Topic files load on-demand in full, so moving
  content into them genuinely removes the per-session-load problem.
- **Memory is plain markdown** you (and the user) can edit directly; `/memory`
  in-session also browses it.
- Twin of the CLAUDE.md curator (`/claude-md-audit`): same index/chapters
  discipline, different surface. Catalog: `memory-index-overflow` (the hard-cutoff
  sibling of `context-doc-bloat`).
