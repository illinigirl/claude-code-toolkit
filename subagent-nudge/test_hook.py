#!/usr/bin/env python3
"""Regression tests for the subagent-nudge hook (hook.py).

Self-contained: invokes hook.py as a subprocess exactly as Claude Code would
(a UserPromptSubmit JSON payload on stdin) and asserts fire / silent / debounce
/ disable / fail-safe behavior, plus the conservative-trigger boundary
(breadth fires, narrow stays silent).

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


def run(prompt, session_id=None, **env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    payload = json.dumps(
        {
            "session_id": session_id or uuid.uuid4().hex,
            "transcript_path": "/tmp/none.jsonl",
            "hook_event_name": "UserPromptSubmit",
            "cwd": "/tmp/some-project",
            "prompt": prompt,
        }
    )
    p = subprocess.run(
        [sys.executable, HOOK], input=payload, capture_output=True, text=True, env=env
    )
    return p.returncode, p.stdout.strip()


def run_raw(stdin_text, **env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    p = subprocess.run(
        [sys.executable, HOOK], input=stdin_text, capture_output=True, text=True, env=env
    )
    return p.returncode, p.stdout.strip()


def main():
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as d:
        os.environ["TMPDIR"] = d  # state files land in the fixture dir

        # A clearly subagent-shaped prompt fires with the documented schema.
        rc, out = run("Please audit every endpoint in the service for auth gaps")
        ok = rc == 0 and bool(out)
        if ok:
            p = json.loads(out)
            hso = p.get("hookSpecificOutput", {})
            ac = hso.get("additionalContext", "")
            ok = (
                hso.get("hookEventName") == "UserPromptSubmit"
                and "/orchestrate" in ac
                and "independent" in ac.lower()
                and "systemMessage" in p
                and "additionalContext" not in p  # must be nested, not top-level
            )
        check("subagent-shaped prompt -> fires with documented schema", ok)

        # Various breadth phrasings each fire (fresh session each time).
        for phrase in [
            "fix all the failing tests",
            "go across the whole codebase and rename the symbol",
            "for each module, add a docstring",
            "do a comprehensive review of the data layer",
            "update every component to the new API",
        ]:
            rc, out = run(phrase)
            check(f"breadth fires: {phrase!r}", rc == 0 and bool(out))

        # Narrow / single-target prompts must stay SILENT (no false positives).
        for phrase in [
            "audit this function for off-by-one errors",
            "fix the bug in parse_date",
            "review my last commit",
            "add a test for the new endpoint",
            "what does this regex do?",
        ]:
            rc, out = run(phrase)
            check(f"narrow stays silent: {phrase!r}", rc == 0 and not out)

        # Per-distinct-prompt debounce: the SAME prompt won't re-fire, but a
        # DIFFERENT qualifying prompt in the same session still does (the point
        # is to flag every parallelizable request, not just the first).
        s = uuid.uuid4().hex
        rc, out = run("audit every route", session_id=s)
        check("first qualifying prompt -> fires", rc == 0 and bool(out))
        rc, out = run("audit every route", session_id=s)
        check("same prompt resubmitted -> debounced silent", rc == 0 and not out)
        rc, out = run("now check all the handlers too", session_id=s)
        check("different qualifying prompt, same session -> still fires", rc == 0 and bool(out))

        # Disable switch: even a textbook match is a clean no-op.
        rc, out = run("audit every single endpoint", SUBAGENT_NUDGE_DISABLED="1")
        check("SUBAGENT_NUDGE_DISABLED -> silent no-op", rc == 0 and not out)

        # Fail-safes.
        rc, out = run_raw("not json at all")
        check("garbage stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run_raw("123")
        check("non-object stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run("", session_id=uuid.uuid4().hex)
        check("empty prompt -> silent", rc == 0 and not out)
        rc, out = run("audit every endpoint", session_id="../../evil")
        check("path-shaped session id -> rejected silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
