#!/usr/bin/env python3
"""
CLAUDE.md curator hook — PostToolUse (Edit | Write | MultiEdit).

Keeps an auto-loaded context file (CLAUDE.md / CLAUDE.local.md / AGENTS.md)
lean. A deterministic hook can't *judge* prose, so it does only the cheap,
mechanical part and points at the `/claude-md-audit` skill for the judgment:

  • Prevention (every sizable addition): when an edit ADDS a substantial block
    (>= CLAUDE_MD_ADD_LINES, default 10) to a context file, nudge Claude to ask
    "directive or reference?" — and if reference, suggest a skill INSTEAD of
    growing the file. Cheapest bloat to remove is the bloat that never lands.
  • Budget (over the line cap): when the file exceeds CLAUDE_MD_LINE_BUDGET
    (default 200), nudge a full /claude-md-audit (triage: keep / extract to a
    skill / archive). Debounced once per session per file so it doesn't nag —
    and so the skill's own curating edits don't re-trigger it.

The principle it enforces: CLAUDE.md is the index (always-relevant directives);
skills are the chapters (on-demand reference).

Config (env):
  CLAUDE_MD_LINE_BUDGET    soft line cap, default 200
  CLAUDE_MD_ADD_LINES      "substantial block" threshold, default 10
  CLAUDE_MD_AUDIT_DISABLED set to disable the hook entirely (clean no-op exit)

Output (PostToolUse): exit 0 + JSON on stdout only when it fires:
  - hookSpecificOutput.additionalContext (nested with hookEventName)
  - systemMessage (top-level, user-visible)
Never blocks; on ANY internal error it exits 0 silently.
"""
import json
import os
import re
import sys
import tempfile

# Auto-loaded context files this hook curates. CLAUDE.archive.md is the demotion
# target and is intentionally NOT here — editing the archive must not nudge.
TARGETS = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"}


def _int_env(name, default):
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _edited_targets(data):
    """Edited paths whose basename is a curated context file."""
    tool = data.get("tool_name")
    ti = data.get("tool_input", {}) or {}
    paths = []
    if tool in ("Edit", "Write"):
        if ti.get("file_path"):
            paths.append(ti["file_path"])
    elif tool == "MultiEdit":
        if ti.get("file_path"):
            paths.append(ti["file_path"])
        paths += [e.get("file_path") for e in ti.get("edits", []) if e.get("file_path")]
    seen, out = set(), []
    for p in paths:
        if p and p not in seen and os.path.basename(p) in TARGETS:
            seen.add(p)
            out.append(p)
    return out


def _added_lines(data):
    """Net lines added by this edit (Edit/MultiEdit). Write gives no prior, so
    addition can't be diffed — return 0 and let the budget check carry it."""
    tool = data.get("tool_name")
    ti = data.get("tool_input", {}) or {}

    def delta(old, new):
        return (new or "").count("\n") - (old or "").count("\n")

    if tool == "Edit":
        return max(0, delta(ti.get("old_string"), ti.get("new_string")))
    if tool == "MultiEdit":
        return max(0, sum(delta(e.get("old_string"), e.get("new_string"))
                          for e in ti.get("edits", [])))
    return 0


def _line_count(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return len(f.read().splitlines())


def _state_path(session_id):
    return os.path.join(tempfile.gettempdir(), f"claude-md-curator-{session_id}.json")


def _budget_already_fired(session_id, path):
    """Once per session per file for the over-budget audit nudge."""
    state = _state_path(session_id)
    fired = []
    if os.path.exists(state):
        try:
            with open(state, encoding="utf-8") as f:
                fired = json.load(f).get("budget_fired", [])
        except Exception:
            fired = []
    if path in fired:
        return True
    fired.append(path)
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"budget_fired": fired}, f)
    return False


def main():
    if os.environ.get("CLAUDE_MD_AUDIT_DISABLED"):
        sys.exit(0)  # clean opt-out without disabling the whole plugin

    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    session_id = data.get("session_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        sys.exit(0)  # session_id lands in a temp filename — reject path-shaped

    budget = _int_env("CLAUDE_MD_LINE_BUDGET", 200)
    add_threshold = _int_env("CLAUDE_MD_ADD_LINES", 10)
    added = _added_lines(data)

    notes, files = [], []
    for path in _edited_targets(data):
        try:
            lines = _line_count(path)
        except Exception:
            continue
        name = os.path.basename(path)
        over = lines > budget
        big_add = added >= add_threshold

        if big_add:
            # Prevention fires on EVERY sizable addition (not debounced).
            notes.append(
                f"{name}: you just added ~{added} lines. Is this an "
                "always-relevant *directive*, or *reference*? If reference "
                "(a war story, how-to-run-X, operational detail), prefer a "
                "skill that loads on-demand INSTEAD of growing the file — "
                "and check it isn't already covered above."
            )
            files.append(name)
        if over and not _budget_already_fired(session_id, path):
            notes.append(
                f"{name}: now {lines} lines, over the {budget}-line budget. "
                "Run /claude-md-audit to triage (keep & tighten / extract to a "
                "skill / archive stale)."
            )
            if name not in files:
                files.append(name)

    if not notes:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "CLAUDE.md curator (a context file was just edited):\n- "
                + "\n- ".join(notes)
                + "\n\nPrinciple: CLAUDE.md is the index (always-relevant "
                "directives); skills are the chapters (on-demand reference). "
                "Surface this to the user and, on their approval, run "
                "/claude-md-audit — don't edit the file unprompted."
            ),
        },
        "systemMessage": (
            f"✎ CLAUDE.md curator: {', '.join(dict.fromkeys(files))} — "
            "consider /claude-md-audit (directives stay; reference → a skill)."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # an advisory hook must never disrupt a session
