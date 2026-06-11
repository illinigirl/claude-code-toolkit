#!/usr/bin/env python3
"""Regression tests for the context-alert hook (hook.py).

Self-contained: builds fake transcript JSONL fixtures in a tempdir, invokes
hook.py as a subprocess exactly as Claude Code would (a hook JSON payload on
stdin), and asserts fire / silent / debounce / re-arm / fail-safe behavior.
CONTEXT_ALERT_SILENT suppresses OS notifications during the run.

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


def usage_line(tokens, sidechain=False):
    """One transcript line whose usage totals `tokens` in context."""
    entry = {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "usage": {
                "input_tokens": 1,
                "cache_creation_input_tokens": 99,
                "cache_read_input_tokens": tokens - 100,
                "output_tokens": 50,
            }
        },
    }
    return json.dumps(entry)


def write_transcript(path, *lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(stdin_text, **env_overrides):
    env = dict(os.environ)
    env.update(
        CONTEXT_ALERT_SILENT="1",
        CONTEXT_ALERT_WINDOW="100000",
        CONTEXT_ALERT_THRESHOLDS="75",
    )
    env.update(env_overrides)
    p = subprocess.run(
        [sys.executable, HOOK], input=stdin_text, capture_output=True, text=True, env=env
    )
    return p.returncode, p.stdout.strip()


def payload(transcript, session_id, event="PostToolUse"):
    return json.dumps(
        {
            "session_id": session_id,
            "transcript_path": transcript,
            "hook_event_name": event,
            "cwd": "/tmp/some-project",
        }
    )


def sid():
    return uuid.uuid4().hex


def main():
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory() as d:
        os.environ["TMPDIR"] = d  # hook state files land in the fixture dir, not real /tmp
        t = os.path.join(d, "transcript.jsonl")

        # Below threshold -> silent.
        write_transcript(t, usage_line(50_000))
        rc, out = run(payload(t, sid()))
        check("below threshold -> silent", rc == 0 and not out)

        # Crossing -> fires with the documented schema, mentions handoff.
        s = sid()
        write_transcript(t, usage_line(80_000))
        rc, out = run(payload(t, s))
        ok = rc == 0 and bool(out)
        if ok:
            p = json.loads(out)
            hso = p.get("hookSpecificOutput", {})
            ok = (
                hso.get("hookEventName") == "PostToolUse"
                and "handoff" in hso.get("additionalContext", "")
                and "systemMessage" in p
                and "additionalContext" not in p
            )
        check("crossing -> fires with documented schema", ok)

        # Same session, still high -> debounced silent.
        rc, out = run(payload(t, s))
        check("second crossing same session -> debounced", rc == 0 and not out)

        # Usage drops (compact) -> silent + re-armed; next climb fires again.
        write_transcript(t, usage_line(20_000))
        rc, out = run(payload(t, s))
        check("post-compact drop -> silent", rc == 0 and not out)
        write_transcript(t, usage_line(90_000))
        rc, out = run(payload(t, s))
        check("re-climb after compact -> fires again", rc == 0 and bool(out))

        # Sidechain usage after the main-chain line must be ignored.
        write_transcript(t, usage_line(80_000), usage_line(5_000, sidechain=True))
        rc, out = run(payload(t, sid()))
        check("trailing sidechain usage ignored -> fires on main-chain", rc == 0 and bool(out))

        # Multiple thresholds: 80% fires the 75 band; 50 is marked too, so a
        # later read at 60% must not retro-fire the lower band.
        s = sid()
        write_transcript(t, usage_line(80_000))
        rc, out = run(payload(t, s), CONTEXT_ALERT_THRESHOLDS="50,75")
        fired_75 = (
            rc == 0
            and out
            and "crossed 75%" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
        )
        check("multi-threshold -> fires highest band", bool(fired_75))
        write_transcript(t, usage_line(60_000))
        rc, out = run(payload(t, s), CONTEXT_ALERT_THRESHOLDS="50,75")
        check("lower band already covered -> silent", rc == 0 and not out)

        # Partial compact: drop below ONE band (90) but not the other (75)
        # must re-arm just that band — the next climb past 90 alerts again.
        s = sid()
        write_transcript(t, usage_line(95_000))
        rc, out = run(payload(t, s), CONTEXT_ALERT_THRESHOLDS="75,90")
        check("95% with 75,90 -> fires", rc == 0 and bool(out))
        write_transcript(t, usage_line(80_000))
        rc, out = run(payload(t, s), CONTEXT_ALERT_THRESHOLDS="75,90")
        check("partial drop to 80% -> silent (75 still covered)", rc == 0 and not out)
        write_transcript(t, usage_line(95_000))
        rc, out = run(payload(t, s), CONTEXT_ALERT_THRESHOLDS="75,90")
        ok = rc == 0 and out and "crossed 90%" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
        check("re-climb past 90 after partial drop -> fires 90 again", bool(ok))

        # Event name passes through for UserPromptSubmit.
        write_transcript(t, usage_line(80_000))
        rc, out = run(payload(t, sid(), event="UserPromptSubmit"))
        ok = rc == 0 and out and json.loads(out)["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        check("UserPromptSubmit event name passes through", bool(ok))

        # No usage lines yet (fresh session) -> silent.
        write_transcript(t, json.dumps({"type": "user", "message": {"role": "user"}}))
        rc, out = run(payload(t, sid()))
        check("no usage yet -> silent", rc == 0 and not out)

        # Fail-safes: garbage stdin, non-object stdin, missing transcript,
        # path-shaped session id (lands in a tmp filename).
        rc, out = run("not json at all")
        check("garbage stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run("123")
        check("non-object stdin -> fail-safe silent", rc == 0 and not out)
        rc, out = run(payload(os.path.join(d, "nope.jsonl"), sid()))
        check("missing transcript -> silent", rc == 0 and not out)
        write_transcript(t, usage_line(80_000))
        rc, out = run(payload(t, "../../evil"))
        check("path-shaped session id -> rejected silent", rc == 0 and not out)

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
