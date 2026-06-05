---
name: handoff
description: Write a PICKUP handoff file that captures the current session — the task, what's done (verified), what's in flight, the next steps, key paths/ids, and working norms — so a fresh session can resume cold with full context. Use when the user wants to checkpoint or hand off a session, save a pickup/handoff file, or wrap up so they can continue later. PICKUP files are personal context and stay local (never committed).
argument-hint: [topic]
---

# Write a session handoff (PICKUP file)

Capture this session so a future session can pick it up with zero ramp-up. The
file is **personal context — local only, never committed or pushed.**

## 1. Distill the session
Pull the real state of this session into:
- **The task / goal** — and why it matters.
- **Done (don't redo)** — verified facts: what shipped, tests passing, what's
  deployed/public, decisions locked. Be concrete (commit hashes, URLs, counts).
- **In flight** — anything mid-stream: a running job, an open decision, a pending
  review.
- **Next steps** — the first concrete thing to do on resume.
- **Key paths / setup** — repos, files, ids, URLs, env-var *names* and setup notes
  (names, never secret values).
- **Working norms** — the standing rules worth repeating (e.g. architect/coder
  split, never push without an explicit ask, any project-specific gotchas).

Convert relative dates to absolute (e.g. "today" → the actual date).

## 2. Write the file
Write `PICKUP-<topic>.md` in the working directory (topic = `$1`, or a short
kebab-case slug of the task), following [template.md](template.md).

## 3. Keep it local
PICKUP-*.md is **never committed or pushed.** If the repo doesn't already ignore
it, add `PICKUP-*.md` to `.gitignore`. Tell the user the file is local-only and
where it is.
