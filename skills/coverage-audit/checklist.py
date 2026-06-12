#!/usr/bin/env python3
"""
Completeness validator for /coverage-audit reports.

The skill's checklist lives in the agent's instructions, and an agent can
silently skip a dimension — the report still reads as thorough. This script
makes completeness deterministic: it parses the report's `## Checklist`
section and FAILS unless every dimension is present and explicitly marked,
either with findings or with an explicit "none found". "Not mentioned"
stops being indistinguishable from "checked and clean".

Usage:  python3 checklist.py <report.md>
Exit 0: all dimensions accounted for.
Exit 1: missing/unannotated dimensions (listed on stdout), or no
        checklist section at all.

Expected report lines (one per dimension, anywhere in the file):
  - [x] empty: <finding refs, or "checked — none found">
A dimension line with an empty annotation fails — the checker requires the
auditor to say what they looked at, not just tick the box.
"""
import re
import sys

DIMENSIONS = [
    "empty",
    "boundary",
    "error",
    "scale",
    "time",
    "adapters",
    "cant-fail",
]

LINE_RE = re.compile(
    r"^\s*[-*]\s*\[[xX]\]\s*(?P<dim>[a-z-]+)\s*:\s*(?P<note>\S.*)$"
)


def validate(text):
    """Return (ok, problems) for a report's checklist completeness."""
    found = {}
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            found[m.group("dim")] = m.group("note").strip()

    problems = []
    for dim in DIMENSIONS:
        if dim not in found:
            problems.append(f"missing dimension: {dim}")
    unknown = set(found) - set(DIMENSIONS)
    for dim in sorted(unknown):
        problems.append(f"unknown dimension (typo?): {dim}")
    return (not problems, problems)


def main():
    if len(sys.argv) != 2:
        print("usage: checklist.py <report.md>")
        return 1
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"cannot read report: {e}")
        return 1

    ok, problems = validate(text)
    if ok:
        print(f"checklist complete: all {len(DIMENSIONS)} dimensions accounted for")
        return 0
    for p in problems:
        print(p)
    print(f"\nchecklist INCOMPLETE — the audit is not done. "
          f"Required dimensions: {', '.join(DIMENSIONS)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
