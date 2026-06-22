#!/usr/bin/env python3
"""
Context-alert hook — PostToolUse (all tools) + UserPromptSubmit.

Alerts when the session's context usage crosses a threshold, while there is
still room to checkpoint cleanly (e.g. via the handoff skill) instead of
hitting an emergency auto-compact.

How it measures: reads the session transcript (transcript_path from the hook
payload) and takes the token `usage` the API reported on the most recent
main-chain assistant message — input + cache_creation + cache_read is what
the model actually held in context for that call. This is exact (lagging by
at most one API call), unlike file-size heuristics: the transcript file only
ever grows and includes sidechains, so size-based estimates overstate usage
and never recover after a compact.

Config (env):
  CONTEXT_ALERT_THRESHOLDS  comma-separated percentages, default "75"
  CONTEXT_ALERT_WINDOW      context window in tokens, default 200000.
                            Set 1000000 on a 1M-context ([1m]) model — this
                            CANNOT be auto-detected: the transcript records the
                            base model id (e.g. claude-opus-4-8) with no [1m]
                            marker, so an un-set 1M session would alert ~5x too
                            early. Configure it once if you run a 1M window.
  CONTEXT_ALERT_SILENT      set to suppress the OS notification (tests)
  CONTEXT_ALERT_DISABLED    set to disable the hook entirely (clean no-op exit)

Each threshold fires once per session (state in the temp dir) and re-arms
when usage drops back below the lowest threshold (i.e. after a compact or
clear), so a long-running session can alert again on the next climb.

Output contract: exit 0 + JSON on stdout only when a threshold is crossed:
  - hookSpecificOutput.additionalContext -> tells Claude to OFFER the user
    a handoff checkpoint (must be nested with hookEventName per the hooks
    schema — a top-level additionalContext is ignored)
  - systemMessage (top-level) -> the user-visible warning
Plus an OS notification (cmux if installed, else macOS osascript, else Linux
notify-send) so the alert lands even when the terminal isn't focused. Never
blocks; on ANY internal error it exits 0 silently.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

CMUX = "/Applications/cmux.app/Contents/Resources/bin/cmux"
TAIL_BYTES = 2 * 1024 * 1024  # usage lines are small; 2MB of tail is ample


def _config():
    raw = os.environ.get("CONTEXT_ALERT_THRESHOLDS", "75")
    thresholds = sorted({int(t) for t in raw.split(",") if t.strip()})
    window = int(os.environ.get("CONTEXT_ALERT_WINDOW", "200000"))
    return thresholds, window


def _tail_lines(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # drop the partial first line
        return f.read().decode("utf-8", errors="ignore").splitlines()


def context_tokens(transcript_path):
    """Tokens in context per the latest main-chain assistant usage, or None."""
    for line in reversed(_tail_lines(transcript_path)):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue  # subagent usage doesn't reflect the main context
        usage = (obj.get("message") or {}).get("usage")
        if isinstance(usage, dict) and "input_tokens" in usage:
            return (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
    return None


def _state_path(session_id):
    return os.path.join(tempfile.gettempdir(), f"claude-context-alert-{session_id}.json")


def crossed_threshold(pct, thresholds, session_id):
    """The highest newly-crossed threshold to fire, or None. Manages state:
    a threshold counts as fired only while usage stays at/above it, so any
    drop below a band (compact, clear) re-arms that band for the next climb."""
    state = _state_path(session_id)
    fired = []
    if os.path.exists(state):
        try:
            with open(state, encoding="utf-8") as f:
                fired = json.load(f).get("fired", [])
        except Exception:
            fired = []
    fired = [t for t in fired if pct >= t]  # re-arm bands usage dropped below
    due = [t for t in thresholds if pct >= t]
    new = [t for t in due if t not in fired]
    if not due:
        if os.path.exists(state):
            os.remove(state)
        return None
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"fired": due}, f)
    return max(new) if new else None


def _notify(title, body):
    if os.environ.get("CONTEXT_ALERT_SILENT"):
        return
    try:
        if os.path.exists(CMUX):
            subprocess.Popen(
                [CMUX, "notify", "--title", title, "--subtitle", "Context", "--body", body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            script = f'display notification "{body}" with title "{title}" sound name "Glass"'
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform.startswith("linux"):
            # notify-send is the de-facto Linux desktop notifier; if it isn't
            # installed the Popen raises and we fall through to the terminal msg.
            subprocess.Popen(
                ["notify-send", title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass  # the in-terminal message still lands


def main():
    if os.environ.get("CONTEXT_ALERT_DISABLED"):
        sys.exit(0)  # clean opt-out without disabling the whole plugin
    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    transcript = data.get("transcript_path")
    session_id = data.get("session_id", "")
    # session_id lands in a temp filename — reject anything path-shaped
    if not transcript or not os.path.isfile(transcript) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", session_id
    ):
        sys.exit(0)

    thresholds, window = _config()
    used = context_tokens(transcript)
    if used is None:
        sys.exit(0)
    pct = used * 100 // window

    fired = crossed_threshold(pct, thresholds, session_id)
    if fired is None:
        sys.exit(0)

    project = os.path.basename(data.get("cwd") or os.getcwd())
    _notify(
        f"Context {pct}%",
        f"{project} — {used // 1000}k of {window // 1000}k tokens. Consider a handoff.",
    )
    event = data.get("hook_event_name", "PostToolUse")
    output = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": (
                f"Context usage has crossed {fired}% of the window "
                f"({used:,} of {window:,} tokens, ~{pct}%). At a natural pause "
                "in the current work, offer the user the option to checkpoint "
                "now — running the handoff skill to write a PICKUP file, "
                "and/or compacting — before context runs low. Use "
                "AskUserQuestion to offer it; if they decline, continue "
                "normally and don't re-offer unless another context alert "
                "fires at a higher threshold."
            ),
        },
        "systemMessage": (
            f"⚠ context at {pct}% ({used // 1000}k of {window // 1000}k tokens) — "
            "Claude will offer a handoff checkpoint."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # an alerting helper must never disrupt a session
