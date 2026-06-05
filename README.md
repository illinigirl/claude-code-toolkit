# claude-code-toolkit

A small toolkit of [Claude Code](https://code.claude.com) capabilities — skills
today, with room to grow into hooks, agents, and plugins. Each lives in its own
directory under `skills/` and can be used on its own.

## Skills

| Skill | Command | What it does |
|---|---|---|
| [scaffold-mcp](skills/scaffold-mcp/) | `/scaffold-mcp` | Generate a new Python MCP server in the pure-core + thin-adapters shape — a runnable, tested, ruff-clean skeleton (FastMCP server with dual stdio/HTTP transport, a CLI adapter, one I/O module, a bundled seed, tests, CLAUDE.md, pyproject). |

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

## Install a skill

Skills are discovered from `~/.claude/skills/` (personal, all projects) or a
repo's `.claude/skills/` (project-scoped). To use one from this collection,
symlink or copy its directory into one of those locations:

```bash
# Personal (available in every project):
ln -s "$PWD/skills/scaffold-mcp" ~/.claude/skills/scaffold-mcp

# Or project-scoped, from inside a repo:
ln -s /path/to/claude-code-toolkit/skills/scaffold-mcp .claude/skills/scaffold-mcp
```

Then invoke it by name, e.g. `/scaffold-mcp`. A symlink during development means
edits to the skill take effect live.

## Layout

```
claude-code-toolkit/
  skills/
    scaffold-mcp/
      SKILL.md        the skill definition (frontmatter + instructions)
      reference.md    the deep pattern rationale (progressive disclosure)
      scaffold.py     the generator (stdlib only)
      templates/      the files it writes, with token markers
  README.md
  LICENSE
```

The structure is plugin-ready: adding a `.claude-plugin/plugin.json` would let
this be installed as a Claude Code plugin, with the same `skills/` directory
picked up automatically.

## License

[MIT](LICENSE).
