#!/usr/bin/env python3
"""
Coverage-nudge hook — Stop + SessionStart.

Keeps test coverage honest with two deterministic checks around the
/coverage-audit skill. The hook only states facts git can verify; judging
whether the *right* tests exist is the skill's job. Hook detects, skill
judges.

Opt-in per repo: staleness tracking keys off COVERAGE-AUDIT.md, the report
/coverage-audit writes. Run the audit once by hand and the automation takes
over; repos with no report fall back to the simpler asymmetry check.

Stop (mid-session watcher; emits a user-facing systemMessage):
  - Repo HAS a COVERAGE-AUDIT.md: nudge when any source file changed after
    the report was written (committed or not, whether or not tests also
    changed — changed tests don't prove *appropriate* tests).
  - Repo has NO report: nudge only on the asymmetry case — source changed,
    zero test files changed.

SessionStart (removes the manual step; emits additionalContext to Claude):
  - If a COVERAGE-AUDIT.md exists and is stale, instruct Claude to run
    /coverage-audit at the first natural point. Running the audit rewrites
    the report, which clears staleness — the loop is self-limiting.
  - No report -> silent: auto-running audits in every repo ever visited
    would be noise; the first audit is a deliberate opt-in.

A changed file counts as a TEST if any path segment is tests/test/
__tests__/spec or its name matches test_*.py / *_test.py / *.test.* /
*.spec.*; SOURCE is any code file (by extension) that isn't a test. Docs,
config, and data changes are neither and never fire anything.

Debounce: each distinct (repo, reason, changed-set, report-mtime) state
fires once (marker file in the system temp dir), so a long session isn't
nagged on every turn; refreshing the report re-arms.

Output contract: exit 0 + JSON. It NEVER blocks (no "decision" key), and
on ANY internal error it exits 0 silently — a heuristic helper must never
disrupt a session.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

REPORT_NAME = "COVERAGE-AUDIT.md"
SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".rb"
}
TEST_DIR_SEGMENTS = {"tests", "test", "__tests__", "spec"}


def _git(args, cwd):
    """Run a git command; return stdout or None on any failure."""
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def _is_test_path(path):
    parts = path.replace("\\", "/").split("/")
    if any(seg.lower() in TEST_DIR_SEGMENTS for seg in parts[:-1]):
        return True
    base = parts[-1]
    stem, _, _ = base.partition(".")
    return (
        base.startswith("test_")
        or stem.endswith("_test")
        or ".test." in base
        or ".spec." in base
        or base == "conftest.py"
    )


def _is_source_path(path):
    _, ext = os.path.splitext(path)
    return ext.lower() in SOURCE_EXTS and not _is_test_path(path)


def _changed_paths(cwd):
    """Parse `git status --porcelain` into a list of changed paths."""
    out = _git(["status", "--porcelain"], cwd)
    if out is None:
        return None
    paths = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # Rename entries read "R  old -> new"; the new path is what changed.
        if " -> " in path:
            path = path.split(" -> ")[-1]
        paths.append(path.strip('"'))
    return paths


def _repo_has_tests(cwd):
    out = _git(["ls-files"], cwd)
    if not out:
        return False
    return any(_is_test_path(p) for p in out.splitlines())


def _stale_sources(root, report_mtime):
    """Source files changed after the report: commits since + working tree.

    Working-tree changes are filtered by file mtime so an uncommitted edit
    the audit already covered (file older than the report) doesn't mark a
    fresh report stale.
    """
    out = _git(
        ["log", f"--since=@{int(report_mtime)}", "--name-only", "--format="],
        root,
    )
    files = set(filter(None, (out or "").splitlines()))
    for p in _changed_paths(root) or []:
        try:
            if os.path.getmtime(os.path.join(root, p)) > report_mtime:
                files.add(p)
        except OSError:
            files.add(p)  # deleted since the audit — that's a change too
    return sorted({f for f in files if _is_source_path(f)})


def _already_nudged(root, reason, key_parts):
    """Debounce: one nudge per distinct (repo, reason, state)."""
    key = hashlib.sha1(
        "\n".join([root, reason, *key_parts]).encode()
    ).hexdigest()[:16]
    marker = os.path.join(
        tempfile.gettempdir(), f"claude-coverage-nudge-{key}.marker"
    )
    if os.path.exists(marker):
        return True
    try:
        with open(marker, "w") as f:
            f.write("")
    except Exception:
        pass  # debounce is best-effort; a nudge twice beats crashing
    return False


def _names(paths, limit=4):
    names = ", ".join(os.path.basename(p) for p in paths[:limit])
    if len(paths) > limit:
        names += f", +{len(paths) - limit} more"
    return names


def _emit(payload):
    print(json.dumps(payload))
    sys.exit(0)


def _handle_stop(root):
    report = os.path.join(root, REPORT_NAME)
    if os.path.exists(report):
        mtime = os.path.getmtime(report)
        stale = _stale_sources(root, mtime)
        if not stale:
            sys.exit(0)
        if _already_nudged(root, "stale", [str(int(mtime)), *stale]):
            sys.exit(0)
        _emit({
            "systemMessage": (
                f"🧪 coverage audit stale: {len(stale)} source file(s) "
                f"changed since the last audit ({_names(stale)}). "
                "Run /coverage-audit to refresh."
            )
        })

    # No report yet — fall back to the asymmetry check.
    changed = _changed_paths(root)
    if not changed:
        sys.exit(0)
    src_changed = [p for p in changed if _is_source_path(p)]
    test_changed = [p for p in changed if _is_test_path(p)]
    if not src_changed or test_changed:
        sys.exit(0)
    if not _repo_has_tests(root):
        sys.exit(0)
    if _already_nudged(root, "asym", src_changed):
        sys.exit(0)
    _emit({
        "systemMessage": (
            f"🧪 coverage nudge: {len(src_changed)} source file(s) changed "
            f"with no test changes ({_names(src_changed)}). If this lands "
            "behavior, consider /coverage-audit to check the negative space."
        )
    })


def _handle_session_start(root):
    report = os.path.join(root, REPORT_NAME)
    if not os.path.exists(report):
        sys.exit(0)  # no opt-in audit yet — stay quiet
    stale = _stale_sources(root, os.path.getmtime(report))
    if not stale:
        sys.exit(0)
    _emit({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"This repo's {REPORT_NAME} is STALE: {len(stale)} source "
                f"file(s) changed since it was written ({_names(stale)}). "
                "Run /coverage-audit at the first natural point in this "
                "session — before calling any new work ship-ready — unless "
                "the user directs otherwise. Refreshing the report clears "
                "this notice."
            ),
        },
        "systemMessage": (
            f"🧪 coverage audit stale ({len(stale)} source change(s) since "
            "last report) — Claude has been asked to refresh it this session."
        ),
    })


def main():
    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        sys.exit(0)
    cwd = data.get("cwd") or os.getcwd()

    root = _git(["rev-parse", "--show-toplevel"], cwd)
    if not root:
        sys.exit(0)  # not a git repo — nothing to say
    root = root.strip()

    event = data.get("hook_event_name", "Stop")
    if event == "SessionStart":
        _handle_session_start(root)
    else:
        _handle_stop(root)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # fail-safe: a heuristic helper must never disrupt a session
