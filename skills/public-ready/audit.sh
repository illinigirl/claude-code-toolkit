#!/usr/bin/env bash
# Public-readiness scanner: flags secrets, PII, and interview/portfolio framing in
# a repo's git-TRACKED files, plus a hygiene checklist. Read-only; prints findings
# for the agent to act on. Always exits 0 (it reports, it doesn't gate).
set -u

REPO="${1:-.}"
[ -z "$REPO" ] && REPO="."
cd "$REPO" 2>/dev/null || { echo "not a directory: $REPO"; exit 0; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not a git repo: $(pwd)"; exit 0; }

echo "== repo: $(pwd)  (tracked files: $(git ls-files | wc -l | tr -d ' ')) =="

echo
echo "== secrets / state files tracked in git (should be none) =="
# Flag real secret/state files; allow committed templates (.env.example etc.).
git ls-files | grep -iE '(^|/)(\.env|\.env\..+|.*\.pem|.*\.key|.*token.*|.*secret.*|.*credential.*|.*\.db|.*cache\.json)$' \
  | grep -viE '\.(example|sample|template|dist)$' \
  && echo "  ^ FLAGGED — these should usually be gitignored, not committed" || echo "  none ✓"

echo
echo "== key-looking / high-entropy strings in tracked text =="
git grep -nIE '(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,})' -- . 2>/dev/null \
  && echo "  ^ FLAGGED — looks like a credential" || echo "  none ✓"

echo
echo "== personal email addresses in tracked text =="
EMAILS=$(git grep -nIE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' -- . 2>/dev/null | grep -vE 'noreply|example\.(com|org)|@A-|your-?email')
[ -n "$EMAILS" ] && { echo "$EMAILS" | head -20; echo "  ^ review — is a personal email meant to be public?"; } || echo "  none ✓"

echo
echo "== interview / hiring / portfolio framing (strip from public artifacts) =="
FRAMING=$(git grep -niE 'interview|hiring|recruit(er|ing)?|portfolio|take-?home|for reviewers' -- . 2>/dev/null)
[ -n "$FRAMING" ] && { echo "$FRAMING" | head -20; echo "  ^ FLAGGED — neutralize this wording"; } || echo "  none ✓"

echo
echo "== hygiene =="
if ls LICENSE* >/dev/null 2>&1; then echo "  LICENSE ✓"; else echo "  LICENSE: MISSING"; fi
if ls README* >/dev/null 2>&1; then echo "  README ✓"; else echo "  README: MISSING"; fi
if [ -f .gitignore ]; then echo "  .gitignore ✓"; else echo "  .gitignore: MISSING"; fi
if ls .github/workflows/*.y*ml >/dev/null 2>&1; then echo "  CI workflow ✓"; else echo "  CI workflow: none (offer to add one)"; fi
if [ -z "$(git status --porcelain)" ]; then echo "  working tree clean ✓"; else echo "  working tree: uncommitted changes present"; fi

echo
echo "== done — resolve any FLAGGED items before publishing =="
