#!/usr/bin/env python3
"""Regression tests for the memory curator hook (hook.py).

Builds fake MEMORY.md fixtures in a memory-dir layout, invokes hook.py as a
subprocess with a PostToolUse payload on stdin, and asserts the load-cutoff
warning (lines and bytes), debounce, memory-dir detection (no false fire on a
bare repo MEMORY.md, no fire on topic files), the disable switch, and fail-safes.

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


def write_lines(path, n, width=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join("x" * width for _ in range(n)))


def run(path, *, tool="Edit", session=None, **env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    ti = {"file_path": path}
    if tool == "Edit":
        ti["old_string"], ti["new_string"] = "a", "b"
    elif tool == "Write":
        ti["content"] = "x"
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
        os.environ["TMPDIR"] = d
        memdir = os.path.join(d, "proj", "memory")
        mem = os.path.join(memdir, "MEMORY.md")

        # Under both budgets -> silent.
        write_lines(mem, 50)
        rc, out = run(mem)
        check("under cutoff -> silent", rc == 0 and not out)

        # Over the line budget -> warns, documented schema.
        write_lines(mem, 250)
        rc, out = run(mem)
        ok = rc == 0 and bool(out)
        if ok:
            p = json.loads(out)
            hso = p.get("hookSpecificOutput", {})
            ac = hso.get("additionalContext", "")
            ok = (hso.get("hookEventName") == "PostToolUse"
                  and "/memory-audit" in ac and "silently" in ac.lower()
                  and "systemMessage" in p and "additionalContext" not in p)
        check("over line budget -> warns w/ schema", ok)

        # Debounce: second edit same session -> silent.
        rc, out = run(mem, session="s_dbl")
        rc, out = run(mem, session="s_dbl")
        check("debounced same session -> silent", rc == 0 and not out)

        # Over the BYTE budget but under the line budget -> still warns.
        # 30 lines * ~1100 chars = ~33KB, well over 25KB, but only 30 lines.
        write_lines(mem, 30, width=1100)
        rc, out = run(mem, session="s_bytes")
        ok = rc == 0 and out and "KB" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
        check("over byte budget (few lines) -> warns", bool(ok))

        # Configurable budget: raise it so 250 lines is fine.
        write_lines(mem, 250)
        rc, out = run(mem, session="s_hi", MEMORY_LINE_BUDGET="1000", MEMORY_BYTE_BUDGET="999999")
        check("raised budgets -> silent", rc == 0 and not out)

        # A bare repo MEMORY.md (not in a memory/ dir) must NOT fire.
        repo_mem = os.path.join(d, "repo", "MEMORY.md")
        write_lines(repo_mem, 400)
        rc, out = run(repo_mem)
        check("repo MEMORY.md (not a memory dir) -> silent", rc == 0 and not out)

        # A topic file in the memory dir is uncapped -> must NOT fire.
        topic = os.path.join(memdir, "debugging.md")
        write_lines(topic, 400)
        rc, out = run(topic)
        check("topic file (not MEMORY.md) -> silent", rc == 0 and not out)

        # Canonical .claude/projects path fires even if parent isn't 'memory'
        # named differently — here parent IS memory, but assert the path branch.
        proj_mem = os.path.join(d, ".claude", "projects", "x", "memory", "MEMORY.md")
        write_lines(proj_mem, 250)
        rc, out = run(proj_mem)
        check(".claude/projects MEMORY.md over budget -> warns", rc == 0 and bool(out))

        # Disable switch.
        write_lines(mem, 250)
        rc, out = run(mem, MEMORY_AUDIT_DISABLED="1")
        check("MEMORY_AUDIT_DISABLED -> silent no-op", rc == 0 and not out)

        # Fail-safes.
        rc, out = run_raw("not json")
        check("garbage stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run_raw("123")
        check("non-object stdin -> fail-safe silent", rc == 0 and not out)
        write_lines(mem, 250)
        rc, out = run(mem, session="../../evil")
        check("path-shaped session id -> rejected silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
