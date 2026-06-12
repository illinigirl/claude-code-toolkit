#!/usr/bin/env python3
"""Regression tests for the coverage-audit completeness validator.

Self-contained: invokes checklist.py as a subprocess on fixture reports,
exactly as the skill (or CI) would.

Run:  python3 test_checklist.py   (exit 0 = all pass, 1 = a failure)
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "checklist.py")

COMPLETE = """# Coverage audit: demo

## Checklist
- [x] empty: tests pass [] to plan_week — none missing
- [x] boundary: rating bounds tested at 1 and 5
- [x] error: corrupt state.json untested — finding #2
- [x] scale: query stub forces 2 pages via page_size
- [x] time: clock injected everywhere; no direct reads
- [x] adapters: CLI at 0% — finding #1
- [x] cant-fail: hasattr registration test — finding #3
"""

MISSING_TWO = """# Coverage audit: demo

## Checklist
- [x] empty: checked — none found
- [x] boundary: checked — none found
- [x] error: corrupt state.json untested
- [x] time: clock injected everywhere
- [x] adapters: CLI at 0%
"""

NO_CHECKLIST = """# Coverage audit: demo

Looks pretty good overall! 95% coverage.
"""

TYPO = COMPLETE.replace("- [x] scale:", "- [x] scales:")


def run_on(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        p = subprocess.run(
            [sys.executable, CHECKER, path], capture_output=True, text=True
        )
        return p.returncode, p.stdout
    finally:
        os.unlink(path)


def main():
    failures = []

    def check(name, cond):
        (failures.append(name) if not cond else None)
        print(("ok  " if cond else "FAIL") + f"  {name}")

    code, out = run_on(COMPLETE)
    check("complete report passes", code == 0 and "complete" in out)

    code, out = run_on(MISSING_TWO)
    check("missing dimensions fail", code == 1)
    check("names the missing dimensions", "scale" in out and "cant-fail" in out)

    code, out = run_on(NO_CHECKLIST)
    check("report with no checklist fails", code == 1)

    code, out = run_on(TYPO)
    check("typo'd dimension fails as missing", code == 1 and "scale" in out)
    check("typo'd dimension flagged as unknown", "scales" in out)

    p = subprocess.run(
        [sys.executable, CHECKER, "/nonexistent/report.md"],
        capture_output=True, text=True,
    )
    check("unreadable report fails cleanly", p.returncode == 1)

    p = subprocess.run([sys.executable, CHECKER], capture_output=True, text=True)
    check("no-args prints usage and fails", p.returncode == 1)

    if failures:
        print(f"\n{len(failures)} failure(s): {failures}")
        sys.exit(1)
    print("\nall checklist validator tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
