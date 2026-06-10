#!/usr/bin/env python3
"""Regression tests for the failure-mode hook (hook.py).

Self-contained: builds fixtures in a tempdir, invokes hook.py as a
subprocess exactly as Claude Code would (a PostToolUse JSON payload on
stdin), and asserts warn / silent / fail-safe behavior.

Run:  python3 test_hook.py   (exit 0 = all pass, 1 = a failure)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.py")

RISKY = """export async function getThings() {
  const resp = await client.send(new ScanCommand({
    TableName: "Data", FilterExpression: "SK = :s",
  }));
  return resp.Items;
}
"""
SAFE = """export async function getThings() {
  let ExclusiveStartKey; const out = [];
  do {
    const resp = await client.send(new ScanCommand({ TableName: "Data", ExclusiveStartKey }));
    out.push(...resp.Items); ExclusiveStartKey = resp.LastEvaluatedKey;
  } while (ExclusiveStartKey);
  return out;
}
"""


def run(stdin_text):
    p = subprocess.run(
        [sys.executable, HOOK], input=stdin_text, capture_output=True, text=True
    )
    return p.returncode, p.stdout.strip()


def fired(out):
    return bool(out) and "silent-data-growth" in out


def main():
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as d:
        risky = os.path.join(d, "risky.ts")
        safe = os.path.join(d, "safe.ts")
        md = os.path.join(d, "notes.md")
        for path, body in ((risky, RISKY), (safe, SAFE), (md, "ScanCommand FilterExpression")):
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)

        rc, out = run(json.dumps({"tool_name": "Write", "tool_input": {"file_path": risky}}))
        check("risky Write -> warns", rc == 0 and fired(out))

        # The warn payload must match the hooks schema exactly: Claude-facing
        # context nested under hookSpecificOutput, user-facing systemMessage
        # top-level. A top-level additionalContext is silently ignored.
        payload = json.loads(out)
        hso = payload.get("hookSpecificOutput", {})
        check(
            "warn payload -> documented schema",
            hso.get("hookEventName") == "PostToolUse"
            and "additionalContext" in hso
            and "systemMessage" in payload
            and "additionalContext" not in payload,
        )

        rc, out = run(json.dumps({"tool_name": "Write", "tool_input": {"file_path": safe}}))
        check("safe (paginated) Write -> silent", rc == 0 and not out)

        rc, out = run(json.dumps({"tool_name": "Edit", "tool_input": {"file_path": md}}))
        check("non-code .md -> silent", rc == 0 and not out)

        # Real MultiEdit schema: one top-level file_path; edits hold old/new strings.
        rc, out = run(json.dumps({"tool_name": "MultiEdit", "tool_input": {
            "file_path": risky, "edits": [{"old_string": "a", "new_string": "b"}]}}))
        check("MultiEdit (top-level path) -> warns", rc == 0 and fired(out))

        rc, out = run(json.dumps({"tool_name": "MultiEdit", "tool_input": {"edits": [{"file_path": risky}]}}))
        check("MultiEdit (nested path fallback) -> warns", rc == 0 and fired(out))

        rc, out = run(json.dumps({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(d, "nope.ts")}}))
        check("missing file -> silent, no crash", rc == 0 and not out)

        rc, out = run("not json at all")
        check("garbage stdin -> fail-safe exit 0, silent", rc == 0 and not out)

        # Valid JSON that isn't a payload object — the fail-safe must cover
        # the whole run, not just the parse.
        for label, weird in (("bare number", "123"), ("null", "null")):
            rc, out = run(weird)
            check(f"non-object stdin ({label}) -> fail-safe exit 0, silent", rc == 0 and not out)

        rc, out = run(json.dumps({"tool_name": "MultiEdit", "tool_input": {"edits": "oops"}}))
        check("malformed edits shape -> fail-safe exit 0, silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
