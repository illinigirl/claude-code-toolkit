---
name: scaffold-mcp
description: Scaffold a new Python MCP server in the pure-core + thin-adapters shape — a runnable, tested, ruff-clean skeleton with a FastMCP server (dual stdio/HTTP transport), a CLI adapter, one I/O module, a bundled seed, tests, CLAUDE.md, and pyproject. Use when the user wants to start/create/bootstrap a new MCP server or tool server and wants a solid project skeleton rather than a single file.
argument-hint: [server-name] [domain]
---

# Scaffold an MCP server

Generate a new MCP-server repo that is **green and ruff-clean the moment it's
created**, in the pure-core + thin-adapters pattern. A bundled generator script
does the file writing; your job is to gather the parameters, run it, prove it
green, then help adapt the generic toy core to the user's real domain.

The deep rationale for the pattern (the four-part "does this need an MCP?" test,
why one I/O module, why dual transport, remote-safe I/O) lives in
[reference.md](reference.md) — read it before adapting domain logic.

## 1. Gather the parameters

Ask only for what's missing; infer sensible defaults and confirm them.

- **name** (required) — kebab-case project/repo name, e.g. `trip-logger`. Becomes
  the project name, the `[project.scripts]` entry point, and the FastMCP server name.
- **domain** — singular noun for the thing tracked, e.g. `trip`. Drives the
  example tool names (`add_trip`, `list_trips`, `summarize_trips`). Default `record`.
- **dest** — parent directory to create the project in. Default: the current
  working directory. The project goes in `<dest>/<name>`.
- **package** — Python package name. Default: `name` with separators removed
  (`trip-logger` → `triplogger`). Only ask if the default reads badly.
- **author** — for `pyproject.toml` / `LICENSE`. Default `Your Name`; use the
  git user name if you can read it.

## 2. Generate

Run the bundled script (stdlib only — no install needed):

```bash
python3 "${CLAUDE_SKILL_DIR}/scaffold.py" \
  --name <name> --domain <domain> --dest <dest> --author "<author>"
```

Optional flags: `--package`, `--domain-plural` (if `domain + "s"` reads wrong),
`--description`, `--force` (write into a non-empty dir).

## 3. Prove it green

From the generated project dir, create a venv, install, and run the suite +
linter. Report the result to the user; do not claim success without running these.

```bash
cd <dest>/<name>
python3 -m venv .venv && .venv/bin/pip install -e ".[test]" ruff
.venv/bin/python -m pytest -q          # expect all green
.venv/bin/ruff check .                 # expect "All checks passed!"
```

The pure-core tests run on stdlib; the tool-layer tests need the MCP SDK, which
the editable install pulls in. If `pip install` can't reach the network, the
tool-layer tests `importorskip("mcp")` and skip cleanly rather than fail — note
that to the user if it happens.

## 4. Hand off to the real domain

The scaffold ships a deliberately generic toy core (records with a `value` and a
`category`, a deterministic `summarize`, a Markdown export) so it's runnable and
tested cold. Point the user at the swap-in work:

```bash
grep -rn "TODO(<domain>)" <dest>/<name>/src
```

Offer to adapt it: replace `Record`'s fields, the `summarize` logic, the seed
data, and the tool names with the user's real domain — keeping the architecture
(pure core, one I/O module, thin adapters, deterministic data plane). When you
add or rename a tool, apply the four-part test in [reference.md](reference.md):
a tool earns its place only if it persists state, causes a side effect / durable
artifact, accesses private/live data, or computes something exact.

## Notes

- The generator is idempotent over its inputs; re-running with the same args
  reproduces the same tree. It refuses to write into a non-empty directory
  unless `--force` is passed.
- Keep the generated repo's own conventions: no portfolio/interview framing in
  committed files, a generic seed with no unverified claims, MIT license.
- Never commit or push the generated repo without the user's explicit ask.
