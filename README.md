# claude-code-toolkit

A small toolkit of [Claude Code](https://code.claude.com) skills, distributed as
an installable **plugin marketplace**. Skills and a failure-mode hook today;
room to grow into agents and MCP servers.

## Skills

| Skill | Command | What it does |
|---|---|---|
| [scaffold-mcp](skills/scaffold-mcp/) | `/scaffold-mcp` | Generate a new Python MCP server — a runnable, tested, ruff-clean skeleton in the pure-core + thin-adapters shape (FastMCP, dual stdio/HTTP transport, CLI adapter, one I/O module, bundled seed, tests, CI, CLAUDE.md, pyproject). |
| [public-ready](skills/public-ready/) | `/public-ready` | Audit a repo for public release — scan tracked files for secrets, PII, and interview/portfolio framing; verify tests + lint are green; check LICENSE / README / .gitignore / CI — then publish (`gh repo create`) on your approval. |
| [handoff](skills/handoff/) | `/handoff` | Write a `PICKUP-*.md` session handoff (task, what's done, what's in flight, next steps, key paths, working norms) so a fresh session resumes cold. Stays local, never committed. |
| [failure-scan](skills/failure-scan/) | `/failure-scan` | Review the current diff against the failure-mode catalog — the judgment classes a hook can't catch (plausible-but-wrong AI output, biased per-segment stats, dispatch-order coupling) — reporting concrete risks with each class's verify questions and fix pattern. |

## What `/scaffold-mcp` generates

It produces a complete, runnable project — not a snippet. One invocation gives a
tested, ruff-clean MCP server skeleton that passes its own suite out of the box:

```text
$ /scaffold-mcp   (→ scaffold.py --name book-tracker --domain book)

book-tracker/
├── src/booktracker/
│   ├── server.py      FastMCP server — dual stdio / HTTP transport
│   ├── core.py        pure domain logic, no I/O — the part you replace
│   ├── store.py       JSON-file persistence (the one I/O module)
│   ├── cli.py         thin CLI adapter over the same core
│   └── models.py · exports.py · __init__.py
├── tests/             conftest + core/server tests (green on generation)
├── data/…seed.json    bundled seed, so it runs immediately
├── .github/workflows/ CI (pytest)
├── CLAUDE.md          orientation: architecture + where to extend
└── pyproject.toml · requirements.txt · LICENSE · README.md

$ pytest -q      →  15 passed
$ ruff check .   →  All checks passed!
```

You swap in your own domain logic (the skill leaves `TODO(domain)` markers); the
structure, both transports, tests, CI, and packaging are already done.

## Failure-mode hook + `/failure-scan`

A small system for **classes of bugs you've hit before** — so you catch them by
default, not by remembering. Two halves over one catalog (`failure-modes/catalog.md`):

- **A PostToolUse hook** (auto-registered on install) flags the *grep-able*
  classes the moment you edit a file — e.g. a DynamoDB `Scan` / `FilterExpression`
  with no pagination, which works until a table outgrows one page and then
  silently returns partial results. Non-blocking, fail-safe (never disrupts an
  edit), and intentionally high-signal — a noisy hook gets ignored.
- **`/failure-scan`** reviews the current diff against the *judgment* classes a
  regex can't catch — plausible-but-wrong AI output, biased per-segment stats,
  implicit dispatch-order coupling — using each class's verify questions.

Add a class once to `catalog.md`, tagged `hook` (gets a grep rule in
`rules.json`) or `judgment` (reviewed by the skill). `failure-modes/test_hook.py`
keeps the hook honest.

## Install (as a plugin)

```text
/plugin marketplace add illinigirl/claude-code-toolkit
/plugin install claude-code-toolkit@claude-code-toolkit
```

Skills then invoke under the plugin namespace, e.g. `/claude-code-toolkit:scaffold-mcp`.
Run `/plugin marketplace update claude-code-toolkit` to pull updates.

## Or use a single skill directly

Skills are also plain `~/.claude/skills/` directories — symlink or copy one in:

```bash
ln -s "$PWD/skills/scaffold-mcp" ~/.claude/skills/scaffold-mcp
```

Then invoke it by name, e.g. `/scaffold-mcp`. A symlink during development means
edits take effect live.

## Layout

```
claude-code-toolkit/
  .claude-plugin/
    marketplace.json    catalogs the plugin (so it's /plugin install-able)
    plugin.json         the plugin manifest
  skills/
    scaffold-mcp/       SKILL.md · reference.md · scaffold.py · templates/
    public-ready/       SKILL.md · audit.sh
    handoff/            SKILL.md · template.md
    failure-scan/       SKILL.md — review a diff against the catalog
  hooks/
    hooks.json          registers the failure-mode PostToolUse hook
  failure-modes/
    catalog.md          the bug-class catalog (the shared brain)
    rules.json          grep-able rules the hook runs
    hook.py · test_hook.py
  README.md · LICENSE
```

Validate the manifests with `claude plugin validate .`.

## License

[MIT](LICENSE).
