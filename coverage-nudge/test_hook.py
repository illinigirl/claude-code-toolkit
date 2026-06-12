#!/usr/bin/env python3
"""Regression tests for the coverage-nudge hook (hook.py).

Self-contained: builds throwaway git repos in tempdirs, invokes hook.py as
a subprocess exactly as Claude Code would (Stop / SessionStart JSON payloads
on stdin), and asserts nudge / silent / fail-safe behavior. Staleness cases
control time via os.utime instead of sleeping.

Run:  python3 test_hook.py   (exit 0 = all pass, 1 = a failure)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.py")
REPORT = "COVERAGE-AUDIT.md"


def run(payload):
    p = subprocess.run(
        [sys.executable, HOOK],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout.strip()


def asym_nudged(out):
    return bool(out) and "coverage nudge" in out


def stale_nudged(out):
    return bool(out) and "coverage audit stale" in out


def git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


def make_repo(tmp, with_tests=True, name="repo"):
    repo = os.path.join(tmp, name)
    os.makedirs(os.path.join(repo, "src"))
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    with open(os.path.join(repo, "src", "foo.py"), "w") as f:
        f.write("def foo():\n    return 1\n")
    with open(os.path.join(repo, "README.md"), "w") as f:
        f.write("# demo\n")
    if with_tests:
        os.makedirs(os.path.join(repo, "tests"))
        with open(os.path.join(repo, "tests", "test_foo.py"), "w") as f:
            f.write("def test_foo():\n    assert True\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def touch(repo, rel, content="changed\n", mtime=None):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path) or path, exist_ok=True)
    with open(path, "a") as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def add_report(repo, mtime):
    """Drop a COVERAGE-AUDIT.md with a controlled timestamp (untracked,
    like a real local audit artifact)."""
    touch(repo, REPORT, "# Coverage audit: demo\n", mtime=mtime)


def main():
    failures = []
    now = time.time()

    def check(name, cond):
        (failures.append(name) if not cond else None)
        print(("ok  " if cond else "FAIL") + f"  {name}")

    # ── No-report repos: the original asymmetry behavior ──

    # 1. Source changed, no test changed -> nudge fires.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "src/foo.py", "# drift\n")
        code, out = run({"cwd": repo})
        check("asym: fires on source-only change", code == 0 and asym_nudged(out))

        # 2. Debounce: identical changed-set on the next stop -> silent.
        code, out = run({"cwd": repo})
        check("asym: debounces the same stop-state", code == 0 and not asym_nudged(out))

        # 3. A NEW source change re-arms the nudge (different changed-set).
        touch(repo, "src/bar.py", "def bar():\n    return 2\n")
        code, out = run({"cwd": repo})
        check("asym: re-arms when the changed-set grows", code == 0 and asym_nudged(out))

    # 4. Source AND test changed -> silent (no report to judge against).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "src/foo.py")
        touch(repo, "tests/test_foo.py", "def test_more():\n    assert True\n")
        code, out = run({"cwd": repo})
        check("asym: silent when tests changed too", code == 0 and not asym_nudged(out))

    # 5. Docs-only change -> silent.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "README.md", "more docs\n")
        code, out = run({"cwd": repo})
        check("asym: silent on docs-only change", code == 0 and not out)

    # 6. Repo with no test files at all -> silent (the tested-repo guard).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp, with_tests=False)
        touch(repo, "src/foo.py")
        code, out = run({"cwd": repo})
        check("asym: silent in repos with no tests", code == 0 and not out)

    # ── Repos WITH a report: staleness behavior ──

    # 7. Report older than the source commit -> stale nudge at Stop.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now - 3600)  # initial commit is newer
        code, out = run({"cwd": repo})
        check("stale: fires when commits postdate the report",
              code == 0 and stale_nudged(out))

    # 8. THE KEY CASE: stale fires even when tests ALSO changed
    #    (changed tests don't prove appropriate tests).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now + 100)  # fresh vs the commit...
        touch(repo, "src/foo.py", mtime=now + 200)        # ...then source drifts
        touch(repo, "tests/test_foo.py", "def test_more():\n    assert True\n",
              mtime=now + 200)                            # tests changed too
        code, out = run({"cwd": repo})
        check("stale: fires even when tests changed too",
              code == 0 and stale_nudged(out))

    # 9. Fresh report -> silent (commit predates it; uncommitted edit is
    #    older than the report, i.e. the audit already covered it).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "src/foo.py", mtime=now + 50)   # edit, then audit
        add_report(repo, mtime=now + 100)
        code, out = run({"cwd": repo})
        check("stale: silent when the report is fresh", code == 0 and not out)

    # 10. Docs drift after a fresh report -> still silent (not source).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now + 100)
        touch(repo, "README.md", mtime=now + 200)
        code, out = run({"cwd": repo})
        check("stale: silent on docs-only drift", code == 0 and not out)

    # 11. Debounce + re-arm: same stale state is quiet; refreshing the
    #     report then drifting again fires anew.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now + 100)
        touch(repo, "src/foo.py", mtime=now + 200)
        code, out = run({"cwd": repo})
        check("stale: fires on first detection", code == 0 and stale_nudged(out))
        code, out = run({"cwd": repo})
        check("stale: debounces the same state", code == 0 and not out)
        add_report(repo, mtime=now + 300)  # audit re-run (refresh)
        code, out = run({"cwd": repo})
        check("stale: silent right after a refresh", code == 0 and not out)
        touch(repo, "src/foo.py", mtime=now + 400)  # new drift
        code, out = run({"cwd": repo})
        check("stale: re-arms after refresh + new drift",
              code == 0 and stale_nudged(out))

    # ── SessionStart: the automatic-refresh instruction ──

    # 12. Stale report at session start -> additionalContext for Claude.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now - 3600)
        code, out = run({"cwd": repo, "hook_event_name": "SessionStart"})
        check("start: instructs Claude when stale",
              code == 0 and "additionalContext" in out and "/coverage-audit" in out)

    # 13. Fresh report at session start -> silent.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now + 100)
        code, out = run({"cwd": repo, "hook_event_name": "SessionStart"})
        check("start: silent when fresh", code == 0 and not out)

    # 14. No report at session start -> silent (opt-in by first manual run).
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "src/foo.py")
        code, out = run({"cwd": repo, "hook_event_name": "SessionStart"})
        check("start: silent with no report", code == 0 and not out)

    # ── Fail-safe + environment edges ──

    # 15. Not a git repo -> silent.
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run({"cwd": tmp})
        check("silent outside a git repo", code == 0 and not out)

    # 16. Garbage stdin must exit 0 silently.
    code, out = run("not json at all")
    check("fail-safe on garbage stdin", code == 0 and not out)
    code, out = run("42")
    check("fail-safe on non-object JSON", code == 0 and not out)

    # 17. Clean tree, no report -> silent.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        code, out = run({"cwd": repo})
        check("silent on a clean tree", code == 0 and not out)

    # ── Parent-of-repos sessions (cwd not a repo, projects one level down) ──

    # 18. Child repo with a stale report -> nudge fires, prefixed with the
    #     repo name so the message says WHICH project drifted.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now - 3600)  # initial commit is newer
        code, out = run({"cwd": tmp})
        check("parent: stale child fires with repo-name prefix",
              code == 0 and "repo: coverage audit stale" in out)

    # 19. Child repo with NO report + source-only uncommitted change ->
    #     silent. The asymmetry check never crosses into children: the
    #     report file is the opt-in, and a parent session must not nag
    #     about a repo it never touched.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        touch(repo, "src/foo.py", "# drift\n")
        code, out = run({"cwd": tmp})
        check("parent: no asymmetry nudge for un-opted-in children",
              code == 0 and not out)

    # 20. Child repo with a fresh report -> silent.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now + 100)
        code, out = run({"cwd": tmp})
        check("parent: silent when the child report is fresh",
              code == 0 and not out)

    # 21. SessionStart with a stale child report -> additionalContext
    #     naming the repo, so Claude knows where to run the audit.
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)
        add_report(repo, mtime=now - 3600)
        code, out = run({"cwd": tmp, "hook_event_name": "SessionStart"})
        check("parent: SessionStart instructs Claude with repo name",
              code == 0 and "additionalContext" in out and "repo" in out)

    # 22. Two stale children -> one merged message naming both.
    with tempfile.TemporaryDirectory() as tmp:
        a = make_repo(tmp, name="alpha")
        b = make_repo(tmp, name="beta")
        add_report(a, mtime=now - 3600)
        add_report(b, mtime=now - 3600)
        code, out = run({"cwd": tmp})
        check("parent: merges nudges across stale children",
              code == 0 and "alpha:" in out and "beta:" in out)

    if failures:
        print(f"\n{len(failures)} failure(s): {failures}")
        sys.exit(1)
    print("\nall coverage-nudge hook tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
