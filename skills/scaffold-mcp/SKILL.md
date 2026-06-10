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

## Choose a path

Ask first which the user wants:

> **"Do you have an MCP idea to talk through and build, or would you like a
> working demo MCP to drive right now?"**

- **An idea to build** → the **build path** (steps 1–4 below): gather a
  name/domain, generate the generic skeleton, prove it green, then adapt it to the
  real domain.
- **A working demo** → the **[demo path](#demo-path)**: stand up the bundled
  `book-tracker` worked example — a real reading-log MCP that clones already
  populated — so they can call a tool and see real output in under a minute.

## Demo path

A complete, tested reading-log MCP ships with this skill at
`${CLAUDE_SKILL_DIR}/examples/book-tracker`. It clones populated with ~15 sample
books, so every tool returns real output immediately. Copy it out (without the
local virtualenv/caches), prove it green, and drive the headline tool:

```bash
DEST=<dest>/book-tracker      # default: the current working directory
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude '.ruff_cache' "${CLAUDE_SKILL_DIR}/examples/book-tracker/" "$DEST/"
cd "$DEST"
export BOOKTRACKER_DATA_DIR=$(mktemp -d)   # fresh state → the demo always opens pristine

# 1. HEADLINE FIRST — zero install. The CLI is pure-stdlib, so it answers in
#    seconds with no venv, no pip, no network. Lead with this; nothing can fail.
PYTHONPATH=src python3 -m booktracker.cli top-genres

# 2. PROVE IT'S REAL — only now install deps and run the suite (the credibility
#    beat: 42 passing tests). This is the only part that needs the MCP SDK.
python3 -m venv .venv && .venv/bin/pip install -e ".[test]" ruff
.venv/bin/ruff check . && .venv/bin/python -m pytest -q            # expect 42 passed
```

Lead with the **zero-install headline** — a real tool answering in seconds, with
nothing to install and no network to fail. Then run the install + suite as the
"and it's real, not faked" beat. (The pure-stdlib CLI is why step 1 needs no
setup; only the MCP server and the tool-layer tests pull in the `mcp` SDK.)

**Always pin a fresh `BOOKTRACKER_DATA_DIR` (above) for a demo.** Mutable state —
added books, `reset_library`, imports — persists in that dir (default
`~/.book-tracker`) *across runs*, so a prior rehearsal can silently poison a fresh
demo (e.g. `reset_library` leaves `top-genres` empty). The throwaway dir isolates
each run; to reset a default-dir install instead, `rm -rf ~/.book-tracker` or run
`booktracker.cli samples on`.

`top-genres` prints one line of real insight ("You read Fantasy most"). Other
beats: `by-month` (a seasonality bar chart), `pace` (goal progress), `summary`.

Then **offer the user things to ask** — a demo should hand them a menu in plain
language, not a list of tool names. Surface a few of these (the full set is in the
example's README "Try asking it"), and run whichever they pick:

- *"What genres do I read most?"* · *"Which do I rate highest?"* · *"What months do
  I read most?"* · *"Am I on pace for my reading goal?"*
- *"Show me everything I've read by Le Guin."* · *"What's in my to-read pile?"*
- *"I just finished Babel by R.F. Kuang — five stars."* · *"Here's my Goodreads
  export — import it."* · *"Add this one"* + a photo of the cover.
- *"Make me a shareable reading list."* · *"Clear the samples — start my own library."*

Then narrate **why it's shaped this way** — that's the point of the demo, not the
output itself:

- **The four-part "does this need an MCP?" test** (persist / artifact / private
  data / exact compute) — every tool maps to one; the example's `CLAUDE.md` is the
  table. The honest move is naming a tool you *didn't* add and why.
- **The model is the importer.** `add_book` (one), `add_books` (a photographed
  shelf — Claude's *vision* extracts the rows), `import_goodreads_csv` (a whole
  back-catalog). All funnel into one dedupe-and-persist sink; the server never
  touches the image. Only bulk CSV uses a deterministic parser.
- **Pure core + thin adapters** — the CLI and the MCP server are two adapters over
  the same tested pure functions, which is *why* this runs without an MCP client.

To adopt it for real (or reset between demos): `reset_library` hides the samples
and clears added books; `use_sample_library on` brings them back. For the live
"drive it from Claude" version, use the README's Claude Desktop / custom-connector
setup — the photo-import beat is a live Claude moment (vision runs in the model, so
it isn't part of the CLI path).

---

The steps below are the **build path** — generating a new server for the user's
own idea.

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

## 1b. Check the reach — flag remote/mobile early

Before generating, reason from the described use case about **where it will run**,
and surface it — don't wait for a form. This is the cheapest place to catch a gap
that's expensive to notice late.

- If the tool would naturally be used **away from the user's computer or on a
  phone** (notes recalled at a restaurant, anything used out in the world), say so
  plainly: a local stdio server only runs as a subprocess of the desktop client,
  so **it won't reach them there.** Call it out as a gap to close before the tool
  is useful — not something the scaffold solves for them.
- The generated server already supports remote transport (`--http` →
  streamable-HTTP custom connector), so the *code* is ready. What remote use adds
  is **deployment**: a host the client can reach, **persistent state that doesn't
  live in `~/.<name>`** (a host or phone won't have that file), and **auth
  appropriate to the host** — network-level (a private network or VPN, where the
  network is the boundary and app-level auth may be unneeded) or app-level (OAuth /
  bearer for a public endpoint). Name these as the work remaining; don't template a
  specific host — a self-hosted box, a PaaS, and serverless differ too much to
  guess, and the right auth depends on which.

Infer and confirm; if it's clearly local-only (a personal desktop utility), skip it.

## 2. Generate

Run the bundled script (stdlib only — no install needed):

```bash
python3 "${CLAUDE_SKILL_DIR}/scaffold.py" \
  --name <name> --domain <domain> --dest <dest> --author "<author>"
```

Optional flags: `--package`, `--domain-plural` (if `domain + "s"` reads wrong),
`--description`, `--force` (write into a non-empty dir).

## 3. Prove it green — hand off to verify-mcp

Generating shouldn't end with a pile of files; it should end with a verdict. So
**run the `verify-mcp` skill on the new project** as the final step — it sets up
the venv, runs ruff + pytest, imports the server to confirm the tools register,
inventories the tool surface (count + missing docstrings), and prints a GREEN/RED
health report. This is the auto-verify: scaffold → report, in one flow.

If `verify-mcp` isn't available, run the same checks inline and report the result;
do not claim success without running them:

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

**After adapting the domain, re-run `verify-mcp`** (or at least `ruff check .` +
`pytest`). Verification isn't a one-time gate at generation — the green skeleton
only proves the *wiring*. Lint is intent-agnostic, so it always applies and
catches drift (unused imports, ordering) introduced while building the domain;
the toy tests, by contrast, should be *replaced* with real ones for the new
domain. Re-running verify after the real logic lands is the check that matters.

## Notes

- The generator is idempotent over its inputs; re-running with the same args
  reproduces the same tree. It refuses to write into a non-empty directory
  unless `--force` is passed.
- Keep the generated repo's own conventions: no portfolio/interview framing in
  committed files, a generic seed with no unverified claims, MIT license.
- Never commit or push the generated repo without the user's explicit ask.
