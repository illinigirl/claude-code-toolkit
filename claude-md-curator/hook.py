#!/usr/bin/env python3
"""
CLAUDE.md curator hook — PostToolUse (Edit | Write | MultiEdit).

Keeps an auto-loaded context file (CLAUDE.md / CLAUDE.local.md / AGENTS.md)
lean. A deterministic hook can't *judge* prose, so it does only the cheap,
mechanical part and points at the `/claude-md-audit` skill for the judgment:

  • Prevention (every addition): when an edit ADDS lines (>= CLAUDE_MD_ADD_LINES,
    default 1 — i.e. every net addition) to a context file, nudge Claude to check
    the NEW content on two axes — KIND (directive=keep / reference=-> a skill /
    area-specific=-> a nested CLAUDE.md or .claude/rules) and SCOPE (team
    convention=project CLAUDE.md / personal=~/.claude/CLAUDE.md / secret-or-local
    =CLAUDE.local.md, gitignored). Cheapest bloat to remove is the bloat that
    never lands. (Pure tweaks that replace text net zero added lines, so they
    don't fire.)
  • Budget (over the line cap): when the file exceeds CLAUDE_MD_LINE_BUDGET
    (default 200), nudge a full /claude-md-audit (triage: keep / extract to a
    skill / archive). Debounced once per session per file so it doesn't nag —
    and so the skill's own curating edits don't re-trigger it.
  • Leak guard: when CLAUDE.local.md is edited but is NOT gitignored, warn — it
    holds personal/secret content and will otherwise be committed. Once per
    session; uses `git check-ignore`, fails quiet outside a repo.

The principle it enforces: CLAUDE.md is the index (always-relevant directives);
skills are the chapters (on-demand reference).

Config (env):
  CLAUDE_MD_LINE_BUDGET    soft line cap, default 200
  CLAUDE_MD_ADD_LINES      min net lines added to evaluate, default 1 (every add)
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

# Context files this hook curates. CLAUDE.md + CLAUDE.local.md auto-load every
# session; AGENTS.md bears context only when a CLAUDE.md @imports or symlinks it
# (Claude Code doesn't read AGENTS.md directly) — but that import is eager, so
# it's still worth curating. CLAUDE.archive.md is the demotion target and is
# intentionally NOT here — editing the archive must not nudge.
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


def _fired_once(session_id, path, key):
    """Once per session per (key, file). `key` namespaces independent debounces
    (e.g. over-budget vs gitignore warning) in one state file without clobbering
    each other."""
    state = _state_path(session_id)
    data = {}
    if os.path.exists(state):
        try:
            with open(state, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    fired = data.get(key, [])
    if path in fired:
        return True
    fired.append(path)
    data[key] = fired
    with open(state, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return False


def _local_not_gitignored(path):
    """True if a CLAUDE.local.md is NOT gitignored (so personal/secret content
    risks being committed). Uses `git check-ignore`; fail toward quiet — if git
    is absent, it's not a repo, or anything errors, return False (no warning)."""
    import subprocess
    d = os.path.dirname(os.path.abspath(path))
    try:
        inside = subprocess.run(
            ["git", "-C", d, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return False  # not a git repo -> nothing to commit into, stay quiet
        ignored = subprocess.run(
            ["git", "-C", d, "check-ignore", "-q", path],
            capture_output=True, timeout=5,
        )
        return ignored.returncode == 1  # 0=ignored, 1=not ignored, other=error
    except Exception:
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
    add_threshold = _int_env("CLAUDE_MD_ADD_LINES", 1)
    added = _added_lines(data)

    notes, files = [], []
    for path in _edited_targets(data):
        try:
            lines = _line_count(path)
        except Exception:
            continue
        name = os.path.basename(path)
        over = lines > budget
        has_add = added >= add_threshold

        if has_add:
            # Prevention fires on EVERY net addition (not debounced).
            notes.append(
                f"{name}: you just added ~{added} line(s). Check the NEW content "
                "on two axes. (1) KIND: always-relevant *directive* (keep), "
                "*reference* (war story / how-to — move to an on-demand skill), "
                "or *area-specific* (move to a nested CLAUDE.md / .claude/rules "
                "for that subtree). (2) SCOPE: a team convention -> project "
                "CLAUDE.md; your personal preference -> ~/.claude/CLAUDE.md; a "
                "sandbox URL / personal test data / anything secret -> "
                "CLAUDE.local.md (gitignored), never the committed file. Move it "
                "to its right home rather than growing this file — and check it "
                "isn't already covered above."
            )
            files.append(name)
        if over and not _fired_once(session_id, path, "budget_fired"):
            notes.append(
                f"{name}: now {lines} lines, over the {budget}-line budget. "
                "Run /claude-md-audit to triage (keep & tighten / extract to a "
                "skill / archive stale)."
            )
            if name not in files:
                files.append(name)
        # CLAUDE.local.md holds personal/secret content — it MUST be gitignored
        # or it gets committed. Check once per session per file (status is stable).
        if (name == "CLAUDE.local.md"
                and _local_not_gitignored(path)
                and not _fired_once(session_id, path, "local_gitignore_fired")):
            notes.append(
                f"{name} is NOT gitignored — it's meant for personal/secret "
                "content (sandbox URLs, test data) and will be committed as-is. "
                "Add it to .gitignore before it leaks into source control."
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
