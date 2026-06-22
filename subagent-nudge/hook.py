#!/usr/bin/env python3
"""
Subagent-nudge hook — UserPromptSubmit.

Spots a *subagent-shaped* prompt (broad, decomposable, "do X across all Y")
and nudges Claude to consider delegating — parallel Explore agents for
read-heavy fan-out, a Workflow pipeline for find→verify, etc. — instead of a
single-threaded inline pass. It does NOT orchestrate anything itself; it points
Claude at the `/orchestrate` decision tree, which advises and (on the user's
go-ahead) executes.

Deliberately conservative and quiet:
  - pure regex on the prompt text only (no FS scan, no LLM call, ~no latency);
  - flag-for-review, never prescriptive — the nudge says "this MIGHT
    parallelize; if the items aren't independent, ignore me";
  - fires once per DISTINCT prompt (a resubmit of the same request won't
    re-fire), so every parallelizable request gets flagged — the conservative
    triggers are the noise control, not a session-wide cap;
  - fully silenceable.

The load-bearing caveat it always carries: parallelism is only valid when the
items are INDEPENDENT (no shared state / ordering). See the
`parallel-without-independence` entry in the failure-mode catalog.

Config (env):
  SUBAGENT_NUDGE_DISABLED   set to disable the hook entirely (clean no-op exit)

Output contract: exit 0 + JSON on stdout only when it fires:
  - hookSpecificOutput.additionalContext -> tells Claude to weigh delegation
    via /orchestrate (nested with hookEventName per the hooks schema)
  - systemMessage (top-level) -> the user-visible one-liner
Never blocks; on ANY internal error it exits 0 silently.
"""
import hashlib
import json
import os
import re
import sys
import tempfile

# Conservative, breadth-requiring triggers. Each needs a sense of *multiplicity*
# so "audit this function" stays silent while "audit every endpoint" fires.
# (label, compiled pattern) — start narrow; widen only if it under-fires.
_TRIGGERS = [
    ("across-codebase",
     r"\bacross (the )?(whole |entire )?(code ?base|repo(sitory)?|project)\b"),
    ("for-each",
     r"\bfor (each|every)\b"),
    ("verb-all-every",
     r"\b(find|fix|update|check|review|migrate|refactor|rename|audit|convert|"
     r"replace|remove|delete|add) (all|every)\b"),
    ("every-X",
     r"\bevery (single )?(file|module|component|endpoint|service|package|test|"
     r"function|usage|occurrence|instance|route|handler|model)\b"),
    ("all-Xs",
     r"\ball (the |of the )?(files|modules|components|endpoints|services|"
     r"packages|tests|usages|occurrences|call ?sites|routes|handlers)\b"),
    ("comprehensive",
     r"\b(comprehensive(ly)?|exhaustive(ly)?)\b"),
]
_TRIGGERS = [(label, re.compile(pat, re.IGNORECASE)) for label, pat in _TRIGGERS]


def matched_triggers(prompt):
    """Labels of every trigger the prompt hits (empty list = no nudge)."""
    return [label for label, pat in _TRIGGERS if pat.search(prompt)]


def _state_path(session_id):
    return os.path.join(
        tempfile.gettempdir(), f"claude-subagent-nudge-{session_id}.json"
    )


def already_nudged(session_id, prompt):
    """Per DISTINCT prompt: True if we've already nudged for this exact prompt
    this session (so resubmitting the same request doesn't re-fire). A different
    qualifying prompt still nudges — flagging every parallelizable request is the
    point; the conservative triggers handle noise, not a session-wide cap."""
    state = _state_path(session_id)
    fp = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:16]
    fired = []
    if os.path.exists(state):
        try:
            with open(state, encoding="utf-8") as f:
                fired = json.load(f).get("fired", [])
        except Exception:
            fired = []
    if fp in fired:
        return True
    fired.append(fp)
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"fired": fired}, f)
    return False


def main():
    if os.environ.get("SUBAGENT_NUDGE_DISABLED"):
        sys.exit(0)  # clean opt-out without disabling the whole plugin

    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    prompt = data.get("prompt") or ""
    session_id = data.get("session_id", "")
    # session_id lands in a temp filename — reject anything path-shaped.
    if not prompt or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        sys.exit(0)

    hits = matched_triggers(prompt)
    if not hits:
        sys.exit(0)
    if already_nudged(session_id, prompt):
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "This request looks potentially parallelizable (matched: "
                f"{', '.join(hits)}). Before answering, weigh delegation using "
                "the /orchestrate decision tree: does the work decompose into a "
                "known list of INDEPENDENT items? If so, suggest the right shape "
                "(parallel Explore agents for read-heavy fan-out; a Workflow "
                "pipeline for find→verify; loop-until-dry for unknown-size "
                "discovery; adversarial verify when a wrong answer is costly) "
                "and offer to run it — execute only on the user's go-ahead. "
                "CRITICAL: only recommend parallelism if you can state WHY the "
                "items are independent (no shared state, no ordering, no "
                "implicit coordination) — see the parallel-without-independence "
                "catalog entry; if you can't, prefer a pipeline or stay inline. "
                "If this isn't actually parallelizable, ignore this nudge "
                "entirely and proceed normally."
            ),
        },
        "systemMessage": (
            "↹ this looks parallelizable — Claude will weigh delegating it "
            "(via /orchestrate) before diving in."
        ),
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # an advisory nudge must never disrupt a session
