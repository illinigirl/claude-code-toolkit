---
name: public-ready
description: Audit a repo for public release and, on approval, publish it. Scans tracked files for secrets, PII, and interview/hiring/portfolio framing; verifies tests + lint are green; checks LICENSE / README / .gitignore / CI; then (only when you say so) runs gh repo create --public --push. Use when the user wants to make a repo public, open-source it, ship it, or run a pre-publish / public-readiness check.
argument-hint: [path]
allowed-tools: Bash(git:*), Bash(gh:*), Bash(grep:*), Bash(rg:*), Bash(ruff:*), Bash(pytest:*), Bash(npm:*)
---

# Make a repo public-ready

Run the publish-readiness audit, fix or surface findings, then publish **only on
explicit approval**. Publishing is outward-facing and hard to undo — never run the
`gh repo create` / push step without a clear "yes".

## 1. Scope the target
Target repo = `$1` (a path) or the current working directory. Confirm it's a git
repo before proceeding.

## 2. Run the deterministic scan
Run the bundled scanner over the repo's *tracked* files and read its output:

```
bash "${CLAUDE_SKILL_DIR}/audit.sh" "$1"
```

It flags: secrets/keys/`.env`/state files tracked in git, high-entropy token
patterns, personal email addresses, and interview/hiring/portfolio framing, plus
a hygiene checklist (LICENSE / README / .gitignore / CI / clean tree). Treat any
flag as a **blocker** until resolved.

## 3. Verify green (language-aware)
Detect the project type and run what applies — report real output, never claim
green without running:
- **Python:** `ruff check .` and `python -m pytest -q` (or the project's configured commands).
- **Node:** the configured lint + `npm test`.
- Other: the project's documented test/lint commands.

## 4. Hygiene + framing review
- LICENSE present? README accurate (no stale scaffold/boilerplate text)?
- `.gitignore` covers state, secrets, and build artifacts?
- A CI workflow under `.github/workflows/`? Offer to add a minimal one if missing.
- Working tree clean — is everything intended actually committed?
- **Framing:** strip interview / hiring / portfolio / "for reviewers" language from
  anything public. This is a hard rule; suggest neutral wording ("Try it yourself").

## 5. Report, then publish on approval
Summarize: blockers found (and fixed), green status, hygiene gaps. Offer to fix
small issues in place. Then, **only if the user explicitly approves**, publish —
confirming the authenticated account first so it lands in the right place:

```
gh api user --jq .login          # confirm the target account
gh repo create <name> --public --source . --remote origin --push --description "<one-liner>"
```

For a private-first workflow, use `--private` and tell the user how to flip it
public later. After pushing, confirm CI is green (`gh run list`).

## Notes
- No secrets, tokens, `.env`, or personal data in tracked files — ever.
- Prefer fixing in place; surface anything you can't safely auto-fix rather than
  publishing around it.
- If something you find contradicts how the repo was described, stop and say so.
