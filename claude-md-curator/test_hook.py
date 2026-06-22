#!/usr/bin/env python3
"""Regression tests for the CLAUDE.md curator hook (hook.py).

Self-contained: builds real fixture files in a tempdir, invokes hook.py as a
subprocess with a PostToolUse payload on stdin, and asserts the two triggers
(sizable-addition prevention, over-budget audit), the budget debounce, target
scoping, the disable switch, and fail-safes.

Run:  python3 test_hook.py   (exit 0 = all pass, 1 = a failure)
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.py")


def block(newlines):
    """A string containing exactly `newlines` newline characters."""
    return "\n".join(["x"] * (newlines + 1))


def write_file(path, n_lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(f"line {i}" for i in range(n_lines)))


def run(tool, file_path, *, old="", new="", session=None, **env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    ti = {"file_path": file_path}
    if tool == "Edit":
        ti["old_string"], ti["new_string"] = old, new
    elif tool == "Write":
        ti["content"] = new
    elif tool == "MultiEdit":
        ti["edits"] = [{"old_string": old, "new_string": new}]
    payload = json.dumps({
        "session_id": session or uuid.uuid4().hex,
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": ti,
    })
    p = subprocess.run([sys.executable, HOOK], input=payload,
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip()


def run_raw(stdin_text, **env):
    e = dict(os.environ)
    e.update(env)
    p = subprocess.run([sys.executable, HOOK], input=stdin_text,
                       capture_output=True, text=True, env=e)
    return p.returncode, p.stdout.strip()


def main():
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as d:
        os.environ["TMPDIR"] = d  # state files land here
        claude = os.path.join(d, "CLAUDE.md")

        # Sizable addition (under budget) -> prevention nudge, documented schema.
        write_file(claude, 50)
        rc, out = run("Edit", claude, old=block(0), new=block(14))
        ok = rc == 0 and bool(out)
        if ok:
            p = json.loads(out)
            hso = p.get("hookSpecificOutput", {})
            ac = hso.get("additionalContext", "")
            ok = (hso.get("hookEventName") == "PostToolUse"
                  and "skill" in ac.lower() and "directive" in ac.lower()
                  and "systemMessage" in p and "additionalContext" not in p)
        check("sizable addition -> prevention nudge w/ schema", ok)

        # Tiny addition, under budget -> silent.
        write_file(claude, 50)
        rc, out = run("Edit", claude, old=block(0), new=block(2))
        check("tiny addition under budget -> silent", rc == 0 and not out)

        # Over budget (small edit) -> audit nudge mentioning the budget + skill.
        write_file(claude, 250)
        rc, out = run("Edit", claude, old=block(0), new=block(1), session="s_over")
        ok = rc == 0 and out and "budget" in json.loads(out)["systemMessage"].lower() \
            or (out and "/claude-md-audit" in json.loads(out)["hookSpecificOutput"]["additionalContext"])
        check("over budget -> audit nudge", rc == 0 and bool(out) and bool(ok))

        # Budget nudge debounced: second over-budget edit same session -> silent.
        rc, out = run("Edit", claude, old=block(0), new=block(1), session="s_over")
        check("over-budget debounced same session -> silent", rc == 0 and not out)

        # Combined: over budget AND a big add (fresh session) -> both notes.
        write_file(claude, 250)
        rc, out = run("Edit", claude, old=block(0), new=block(20), session="s_combo")
        ok = False
        if rc == 0 and out:
            ac = json.loads(out)["hookSpecificOutput"]["additionalContext"]
            ok = "added" in ac.lower() and "budget" in ac.lower()
        check("over budget + big add -> both notes", ok)

        # Non-target file ignored even with a big add.
        readme = os.path.join(d, "README.md")
        write_file(readme, 300)
        rc, out = run("Edit", readme, old=block(0), new=block(20))
        check("non-target (README.md) -> silent", rc == 0 and not out)

        # The archive file must NOT be curated.
        arch = os.path.join(d, "CLAUDE.archive.md")
        write_file(arch, 400)
        rc, out = run("Edit", arch, old=block(0), new=block(20))
        check("CLAUDE.archive.md -> silent (not a target)", rc == 0 and not out)

        # AGENTS.md is a target.
        agents = os.path.join(d, "AGENTS.md")
        write_file(agents, 50)
        rc, out = run("Edit", agents, old=block(0), new=block(15))
        check("AGENTS.md sizable add -> fires", rc == 0 and bool(out))

        # Write of a large new file: no diff, but budget check still fires.
        big = os.path.join(d, "CLAUDE.md")
        write_file(big, 250)
        rc, out = run("Write", big, new="whatever", session="s_write")
        check("Write over budget -> audit nudge", rc == 0 and bool(out))

        # Configurable budget: raise it so 250 lines is fine.
        write_file(claude, 250)
        rc, out = run("Edit", claude, old=block(0), new=block(1),
                      session="s_hibudget", CLAUDE_MD_LINE_BUDGET="500")
        check("raised budget -> under cap -> silent", rc == 0 and not out)

        # Disable switch: textbook trigger, clean no-op.
        write_file(claude, 250)
        rc, out = run("Edit", claude, old=block(0), new=block(20),
                      CLAUDE_MD_AUDIT_DISABLED="1")
        check("CLAUDE_MD_AUDIT_DISABLED -> silent no-op", rc == 0 and not out)

        # Fail-safes.
        rc, out = run_raw("not json at all")
        check("garbage stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run_raw("123")
        check("non-object stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run("Edit", claude, old=block(0), new=block(20), session="../../evil")
        check("path-shaped session id -> rejected silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
