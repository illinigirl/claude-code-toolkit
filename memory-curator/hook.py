#!/usr/bin/env python3
"""
Memory curator hook — PostToolUse (Edit | Write | MultiEdit).

Auto memory's MEMORY.md (in ~/.claude/projects/<project>/memory/) is loaded into
context each session — but only its FIRST 200 lines / 25 KB, whichever comes
first. Content past that is SILENTLY not loaded: a hard truncation, not a soft
budget. Since Claude writes this file itself across sessions, it grows without
anyone deciding to — and the dropped tail is memory you thought was active.

This hook does the cheap mechanical part: when an edited MEMORY.md crosses the
load cutoff, it warns that the tail is now silently dropped and points at the
`/memory-audit` skill (which does the judgment: index↔topic split, staleness,
contradiction). It never edits; on ANY internal error it exits 0 silently.

Only MEMORY.md has the cutoff — topic files load on-demand in full — so moving
detail OUT of MEMORY.md into topic files is the fix, and topic-file edits don't
fire this hook.

Config (env):
  MEMORY_LINE_BUDGET     line cutoff, default 200
  MEMORY_BYTE_BUDGET     byte cutoff, default 25600 (25 KB)
  MEMORY_AUDIT_DISABLED  set to disable the hook entirely (clean no-op exit)

Output (PostToolUse): exit 0 + JSON on stdout only when over the cutoff:
  - hookSpecificOutput.additionalContext (nested with hookEventName)
  - systemMessage (top-level, user-visible)
"""
import json
import os
import re
import sys
import tempfile

BYTE_BUDGET_DEFAULT = 25 * 1024  # 25 KB, per the docs' MEMORY.md load limit


def _int_env(name, default):
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _is_memory_md(path):
    """True only for an auto-memory MEMORY.md — not a repo file that happens to
    be named MEMORY.md. Auto memory lives in a `memory/` dir, canonically under
    ~/.claude/projects/<project>/memory/. Conservative: when unsure, return
    False (fail toward quiet)."""
    if os.path.basename(path) != "MEMORY.md":
        return False
    norm = path.replace("\\", "/")
    parent = os.path.basename(os.path.dirname(norm))
    return parent == "memory" or "/.claude/projects/" in norm


def _edited_memory_files(data):
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
        if p and p not in seen and _is_memory_md(p):
            seen.add(p)
            out.append(p)
    return out


def _state_path(session_id):
    return os.path.join(tempfile.gettempdir(), f"claude-memory-curator-{session_id}.json")


def _already_fired(session_id, path):
    """Once per session per file."""
    state = _state_path(session_id)
    fired = []
    if os.path.exists(state):
        try:
            with open(state, encoding="utf-8") as f:
                fired = json.load(f).get("fired", [])
        except Exception:
            fired = []
    if path in fired:
        return True
    fired.append(path)
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"fired": fired}, f)
    return False


def main():
    if os.environ.get("MEMORY_AUDIT_DISABLED"):
        sys.exit(0)  # clean opt-out without disabling the whole plugin

    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    session_id = data.get("session_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        sys.exit(0)  # session_id lands in a temp filename — reject path-shaped

    line_budget = _int_env("MEMORY_LINE_BUDGET", 200)
    byte_budget = _int_env("MEMORY_BYTE_BUDGET", BYTE_BUDGET_DEFAULT)

    notes = []
    for path in _edited_memory_files(data):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue
        lines = len(content.splitlines())
        nbytes = len(content.encode("utf-8"))
        if lines <= line_budget and nbytes <= byte_budget:
            continue
        if _already_fired(session_id, path):
            continue
        why = []
        if lines > line_budget:
            why.append(f"{lines} lines (> {line_budget})")
        if nbytes > byte_budget:
            why.append(f"{nbytes // 1024} KB (> {byte_budget // 1024} KB)")
        notes.append(
            f"MEMORY.md is {' and '.join(why)} — only the first {line_budget} "
            f"lines / {byte_budget // 1024} KB load each session, so entries past "
            "the cutoff are SILENTLY not loaded. Run /memory-audit to tighten the "
            "index and move detail into on-demand topic files."
        )

    if not notes:
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "Memory curator:\n- " + "\n- ".join(notes)
                + "\n\nMEMORY.md is the index (loaded, capped); topic files are "
                "the chapters (on-demand, uncapped). Surface this to the user "
                "and, on approval, run /memory-audit — don't edit memory "
                "unprompted."
            ),
        },
        "systemMessage": (
            "🧠 memory curator: MEMORY.md is over the load cutoff — tail is "
            "silently dropped. Consider /memory-audit."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # an advisory hook must never disrupt a session
