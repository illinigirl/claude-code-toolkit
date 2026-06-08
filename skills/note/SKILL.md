---
name: note
description: Frictionless note-to-self capture with automatic categorization. Invoked WITH text, it classifies the note into one of a few buckets (note, skill, mcp, todo), appends it to ~/.claude/notes/<category>.md, and reports where it filed it — so you never have to pick a category. Invoked with a bare category name it lists that bucket; invoked with nothing it lists everything grouped by category. Optional override: prefix with "<category>:" to force the bucket. Use to jot ideas, todos, skill/MCP candidates, or observations without breaking flow.
---

# /note

Frictionless note-to-self: you dump a thought, the skill files it. You never
have to pick a category — but you can override one when you want.

## Categories (fixed, small on purpose)
- **skill** — "this could be a Claude Code skill" candidates
- **mcp** — "this could be an MCP / tool server" build ideas
- **todo** — things to do or fix
- **note** — everything else (observations, decisions, reminders)

One file per category: `~/.claude/notes/<category>.md` (create with a
`# <category>` header if it doesn't exist).

## Decide what the invocation means
1. **No argument** → LIST all: for each `~/.claude/notes/*.md`, show its entries
   under the category name. If none exist, say the notes are empty.
2. **Argument is exactly a category name** (`note` / `skill` / `mcp` / `todo`)
   → LIST just that bucket (say it's empty if the file is missing).
3. **Argument begins with `<category>:`** (explicit override, e.g. `skill: ...`)
   → CAPTURE into that category, verbatim (text after the colon).
4. **Otherwise** → CAPTURE with auto-classification (below).

## Capture
- If no category was given, **classify** the note into exactly one of
  {skill, mcp, todo, note}:
  - building/making a *skill* or slash command → `skill`
  - building an *MCP* / tool server → `mcp`
  - an actionable task (fix, bump, email, check, send…) → `todo`
  - otherwise → `note`
- Append exactly one line to `~/.claude/notes/<category>.md` (create it with a
  `# <category>` header first if missing):

  `- <today's date YYYY-MM-DD> — <the note, verbatim>`

  (Use `date +%F` if unsure of the date.)
- **Report where you filed it** — e.g. "Filed under **skill**: …" — so a wrong
  guess is obvious and easy to re-file.

## Keep it simple
Append and list only. Don't reformat or "improve" existing entries; one line per
note. If the category is ambiguous, pick the closest and say so — the user can
re-file by editing the file.
