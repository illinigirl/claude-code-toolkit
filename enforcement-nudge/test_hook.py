#!/usr/bin/env python3
"""Regression tests for the enforcement-redundancy nudge (hook.py).

Self-contained: builds real fixture trees in a tempdir, invokes hook.py as a
subprocess with a PostToolUse payload on stdin, and asserts the trigger
(enforcement artifact + a context file nearby), the artifact classifier
(skill / hook impl / hook registration vs noise), the context-file guard, the
once-per-session debounce, the disable switch, and the fail-safes.

HOME and TMPDIR are pointed at the tempdir for every run so the ~/.claude
context-file fallback and the debounce state file are deterministic regardless
of the host machine.

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


def write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run(tool, file_path, *, new="enforce", session=None, home=None, tmp=None, **env_overrides):
    env = dict(os.environ)
    if home:
        env["HOME"] = home
    if tmp:
        env["TMPDIR"] = tmp
    env.update(env_overrides)
    ti = {"file_path": file_path}
    if tool == "Edit":
        ti["old_string"], ti["new_string"] = "", new
    elif tool == "Write":
        ti["content"] = new
    elif tool == "MultiEdit":
        ti["edits"] = [{"old_string": "", "new_string": new}]
    payload = json.dumps({
        "session_id": session or uuid.uuid4().hex,
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": ti,
    })
    p = subprocess.run([sys.executable, HOOK], input=payload,
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip()


def run_raw(stdin_text, **env_overrides):
    e = dict(os.environ)
    e.update(env_overrides)
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
        home = os.path.join(d, "home")          # empty -> no ~/.claude fallback
        os.makedirs(home, exist_ok=True)
        ctx = os.path.join(d, "ctx")            # a tree WITH a context file
        write(os.path.join(ctx, "CLAUDE.md"), "\n".join(f"l{i}" for i in range(20)))
        noctx = os.path.join(d, "noctx")        # a tree WITHOUT one
        os.makedirs(noctx, exist_ok=True)
        base = dict(home=home, tmp=d)

        # A skill written under a tree that has a CLAUDE.md -> fires, with the
        # documented schema and the compress-not-delete caveat.
        skill = os.path.join(ctx, "skills", "foo", "SKILL.md")
        write(skill)
        rc, out = run("Write", skill, **base)
        ok = rc == 0 and bool(out)
        if ok:
            p = json.loads(out)
            hso = p.get("hookSpecificOutput", {})
            ac = (hso.get("additionalContext") or "").lower()
            ok = (hso.get("hookEventName") == "PostToolUse"
                  and "/claude-md-audit" in ac
                  and "pointer" in ac and ("keep" in ac or "judgment" in ac)
                  and "delete" in ac
                  and "systemMessage" in p and "additionalContext" not in p)
        check("skill near CLAUDE.md -> nudge w/ compress-not-delete caveat", ok)

        # A hook implementation file -> fires.
        hook_impl = os.path.join(ctx, "myhook", "hook.py")
        write(hook_impl)
        rc, out = run("Write", hook_impl, **base)
        check("hook.py near CLAUDE.md -> fires", rc == 0 and bool(out))

        # A plugin hook registration file -> fires.
        hooks_json = os.path.join(ctx, "hooks", "hooks.json")
        write(hooks_json)
        rc, out = run("Write", hooks_json, **base)
        check("hooks.json near CLAUDE.md -> fires", rc == 0 and bool(out))

        # settings.json edit that registers a hook -> fires.
        settings = os.path.join(ctx, ".claude", "settings.json")
        write(settings)
        rc, out = run("Edit", settings, new='"PostToolUse": [ { "hooks": [] } ]', **base)
        check("settings.json touching a hook block -> fires", rc == 0 and bool(out))

        # settings.json edit that does NOT touch hooks (permissions only) -> silent.
        rc, out = run("Edit", settings, new='"permissions": { "allow": ["Bash"] }', **base)
        check("settings.json w/o hooks (permissions edit) -> silent", rc == 0 and not out)

        # An ordinary source file is not an enforcement artifact -> silent.
        src = os.path.join(ctx, "src", "thing.py")
        write(src)
        rc, out = run("Write", src, **base)
        check("ordinary .py file -> silent", rc == 0 and not out)

        # An enforcement artifact with NO context file anywhere up the tree, and
        # an empty HOME -> nothing to prune -> silent.
        lonely = os.path.join(noctx, "skills", "bar", "SKILL.md")
        write(lonely)
        rc, out = run("Write", lonely, **base)
        check("artifact w/ no context file nearby -> silent", rc == 0 and not out)

        # Once-per-session debounce: first fires, second (same session) silent,
        # even for a different artifact.
        s = "s_debounce"
        rc, out = run("Write", skill, session=s, **base)
        first = rc == 0 and bool(out)
        rc, out = run("Write", hook_impl, session=s, **base)
        second = rc == 0 and not out
        check("debounced once per session (2nd artifact silent)", first and second)

        # Disable switch: textbook trigger, clean no-op.
        rc, out = run("Write", skill, ENFORCEMENT_NUDGE_DISABLED="1", **base)
        check("ENFORCEMENT_NUDGE_DISABLED -> silent no-op", rc == 0 and not out)

        # Fail-safes.
        rc, out = run_raw("not json at all")
        check("garbage stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run_raw("123")
        check("non-object stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run("Write", skill, session="../../evil", **base)
        check("path-shaped session id -> rejected silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
