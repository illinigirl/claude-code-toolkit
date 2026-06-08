#!/usr/bin/env python3
"""
Failure-mode hook — PostToolUse (Edit | Write | MultiEdit).

Reads the grep-able rules in rules.json (next to this file) and emits a
NON-BLOCKING warning when a just-edited file matches a risky pattern from
the failure-mode catalog. It never blocks an edit, and on ANY internal
error it exits 0 silently — a heuristic helper must never disrupt a session.

Output contract (PostToolUse): exit 0 + JSON on stdout:
  - additionalContext -> shown to Claude (so it can act / suggest a fix)
  - systemMessage      -> shown to the user in the transcript
Only emitted when there's a hit; silent otherwise.

A rule fires when, for a file matching its globs, ANY `any_match` pattern
is present AND NONE of the `absent` patterns are (the risky construct
without its mitigation).
"""
import json
import os
import re
import sys
from fnmatch import fnmatch


def _load_rules(here):
    with open(os.path.join(here, "rules.json"), encoding="utf-8") as f:
        return json.load(f).get("rules", [])


def _edited_paths(data):
    tool = data.get("tool_name")
    ti = data.get("tool_input", {}) or {}
    if tool in ("Edit", "Write"):
        p = ti.get("file_path")
        return [p] if p else []
    if tool == "MultiEdit":
        return [e.get("file_path") for e in ti.get("edits", []) if e.get("file_path")]
    return []


def _matches_globs(path, globs):
    base = os.path.basename(path)
    return any(fnmatch(base, g) or fnmatch(path, g) for g in globs)


def _rule_fires(content, rule):
    any_match = rule.get("any_match", [])
    absent = rule.get("absent", [])
    if any_match and not any(re.search(p, content) for p in any_match):
        return False
    if absent and any(re.search(p, content) for p in absent):
        return False
    return True


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        data = json.loads(sys.stdin.read() or "{}")
        rules = _load_rules(here)
    except Exception:
        sys.exit(0)  # fail-safe: never disrupt the session

    hits = []
    for path in _edited_paths(data):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue
        for rule in rules:
            globs = rule.get("globs", [])
            if globs and not _matches_globs(path, globs):
                continue
            try:
                if _rule_fires(content, rule):
                    hits.append((path, rule))
            except re.error:
                continue  # a malformed pattern shouldn't break the run

    if not hits:
        sys.exit(0)

    detail = "\n".join(
        f"- {os.path.basename(p)}: {r.get('message', r.get('id'))}" for p, r in hits
    )
    ids = sorted({r.get("id", "?") for _, r in hits})
    output = {
        "additionalContext": (
            "Failure-mode catalog flagged a possible issue in a file just "
            "edited (heuristic — may be a false positive):\n"
            + detail
            + "\n\nIf it's a real instance, address it; otherwise note why "
            "it's safe. For judgment-class checks, consider /failure-scan."
        ),
        "systemMessage": (
            f"⚠ failure-mode check: possible {', '.join(ids)} in "
            f"{len(hits)} edited file(s). Heuristic — review or run /failure-scan."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
