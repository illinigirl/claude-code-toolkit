#!/usr/bin/env python3
"""
Enforcement-redundancy nudge — PostToolUse (Edit | Write | MultiEdit).

The complementary trigger to the `claude-md-curator` hook. The curator fires
when you *edit CLAUDE.md* (catching "this new line duplicates an existing
line"). But the opposite redundancy is invisible to it: when you write a HOOK
or a SKILL that mechanically enforces a rule, you are NOT touching CLAUDE.md —
so nothing re-evaluates the now-redundant prose. The doc sits static while the
world underneath it changed. This hook watches that other event.

It fires when an *enforcement artifact* is created or edited:
  • a skill          — a written `SKILL.md`
  • a hook impl      — a `hook.py`
  • a hook reg        — `hooks.json`, or a `settings.json` / `settings.local.json`
                        edit that touches a `hooks` block / a hook event name

…and a context file (CLAUDE.md / AGENTS.md / CLAUDE.local.md) actually exists
nearby (else there's nothing to prune — stay silent). When it fires it nudges
toward `/claude-md-audit`, which now carries a doc-vs-enforcement lens.

THE ONE RULE IT CARRIES: a hook/skill almost never *fully* replaces prose. It
mechanizes the *mechanical half* of a rule while the *judgment half* (the why,
the teaching, when to surface it) stays valuable. So the nudge says **compress
the mechanical instruction to a one-line pointer at the enforcement — never
delete the judgment.** Suggestion only; the audit (and the user) decide.

Debounced ONCE PER SESSION (not per artifact): the action it asks for — a
redundancy pass — is done once per session regardless of how many artifacts you
wrote, so one reminder is enough. Minimises nag in a repo that authors hooks.

Config (env):
  ENFORCEMENT_NUDGE_DISABLED  set to disable the hook entirely (clean no-op exit)

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

# Context files worth pruning. Same set the curator guards — if none of these
# exist near the artifact, there is nothing to make redundant, so stay quiet.
CONTEXT_FILES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"}

# Hook event names — their presence in a settings edit signals a hook
# registration (vs an unrelated permissions/env edit to the same file).
HOOK_EVENTS = (
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop",
    "SessionStart", "SessionEnd", "Notification", "PreCompact",
)
_HOOK_KEY_RE = re.compile(r'"hooks"|' + "|".join(HOOK_EVENTS))


def _new_text(data):
    """The text this edit introduced — what we scan to tell a hook registration
    from an unrelated settings edit. Edit→new_string, MultiEdit→all new_strings,
    Write→content."""
    tool = data.get("tool_name")
    ti = data.get("tool_input", {}) or {}
    if tool == "Edit":
        return ti.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string") or "" for e in ti.get("edits", []))
    if tool == "Write":
        return ti.get("content") or ""
    return ""


def _edited_paths(data):
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
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _classify(path, new_text):
    """Return a human label if `path` is an enforcement artifact, else None."""
    base = os.path.basename(path)
    if base == "SKILL.md":
        return "a skill"
    if base == "hook.py":
        return "a hook"
    if base == "hooks.json":
        return "a hook registration"
    if base in ("settings.json", "settings.local.json") and _HOOK_KEY_RE.search(new_text or ""):
        return "a hook registration"
    return None


def _context_file_near(path):
    """True if a CLAUDE.md / AGENTS.md / CLAUDE.local.md exists from the
    artifact's directory up to the filesystem root, or at ~/.claude/. Walks up a
    bounded number of levels (cheap stat checks); no nudge if nothing to prune."""
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(40):  # bounded: deepest real trees are nowhere near this
        for name in CONTEXT_FILES:
            if os.path.exists(os.path.join(d, name)):
                return True
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    home = os.path.expanduser("~/.claude")
    return any(os.path.exists(os.path.join(home, n)) for n in CONTEXT_FILES)


def _state_path(session_id):
    return os.path.join(tempfile.gettempdir(), f"enforcement-nudge-{session_id}.json")


def _fired_this_session(session_id):
    """Once per session, full stop. The reminder asks for a single redundancy
    pass, so writing five hooks in one session should nudge once."""
    state = _state_path(session_id)
    if os.path.exists(state):
        return True
    try:
        with open(state, "w", encoding="utf-8") as f:
            json.dump({"fired": True}, f)
    except Exception:
        pass  # if we can't persist, better to risk a repeat than to error
    return False


def main():
    if os.environ.get("ENFORCEMENT_NUDGE_DISABLED"):
        sys.exit(0)

    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    session_id = data.get("session_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        sys.exit(0)  # session_id lands in a temp filename — reject path-shaped

    new_text = _new_text(data)
    hits = []  # (path, label)
    for path in _edited_paths(data):
        label = _classify(path, new_text)
        if label and _context_file_near(path):
            hits.append((os.path.basename(path), label))
    if not hits:
        sys.exit(0)

    # One reminder per session regardless of how many artifacts landed.
    if _fired_this_session(session_id):
        sys.exit(0)

    name, label = hits[0]
    extra = f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"Enforcement-redundancy nudge: you just created/edited {label} "
                f"({name}{extra}). A rule it now MECHANICALLY enforces may be "
                "redundant as prose in CLAUDE.md (the curator hook won't catch "
                "this — it only fires when CLAUDE.md itself is edited). Consider "
                "/claude-md-audit, which checks doc-vs-enforcement redundancy. "
                "IMPORTANT: a hook/skill usually enforces only the *mechanical* "
                "half of a rule — compress that instruction to a one-line pointer "
                "at the enforcing hook/skill and KEEP the judgment/why. Don't "
                "delete the prose wholesale. Surface this to the user; only run "
                "the audit, and only edit CLAUDE.md, on their go-ahead."
            ),
        },
        "systemMessage": (
            f"✎ enforcement-nudge: {name} added — a CLAUDE.md rule may now be "
            "enforced in code. Consider /claude-md-audit (compress to a pointer, "
            "keep the why)."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # an advisory hook must never disrupt a session
