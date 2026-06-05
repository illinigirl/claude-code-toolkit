# The MCP-server pattern this skill scaffolds

Background for adapting a scaffolded repo. The skeleton is generic on purpose;
these are the principles that make it worth starting from, so keep them intact as
you replace the toy domain.

## The four-part "does this need an MCP?" test

A tool is justified only if it gives the model something it **cannot do alone**.
There are exactly four such things. If a proposed tool does none of them, it's
overkill — let Claude just answer in plain language.

1. **Persist state across sessions.** Claude forgets between chats; a tool that
   writes to `state.json` (and reads it back) is real memory. *(Scaffold:
   `add_<domain>`.)*
2. **Cause a side effect / create a durable artifact.** Claude can't write a
   file, hit an API, or change the world; a tool can. *(Scaffold: `export_report`.)*
3. **Access private or live data.** Claude doesn't know your local library, your
   account, or today's numbers; a tool grounds it in real data. *(Scaffold:
   reading the seed + state.)*
4. **Compute something exact.** Claude hand-waves arithmetic; a deterministic
   function doesn't. *(Scaffold: `summarize`.)*

Put this table in the generated `CLAUDE.md` (the scaffold already does) so it's
the standing contract for every future tool.

## Pure core + thin adapters

```
models.py    dataclasses, no I/O
core.py      domain logic — pure functions, inputs in / values out
exports.py   rendering — pure string building
store.py     the ONLY module that touches the filesystem
server.py    FastMCP adapter — thin @mcp.tool wrappers over the core
cli.py       a second adapter over the same core (runs without an MCP client)
```

Why it matters:

- **Testable without a runtime.** The pure modules are unit-tested directly; the
  tool layer is integration-tested in-process against a sandboxed data dir. No
  server boot, no network.
- **One I/O module.** All persistence lives in `store.py`, so the rest of the
  code stays pure. This is also the seam where a data-shape assumption ("the
  whole table fits in one read") can silently rot as data grows — keep that
  assumption written down as an expiring contract, and revisit it before it
  breaks. (See the generated CLAUDE.md note.)
- **Two adapters, one core.** The CLI proves the project runs and demos without
  any MCP client; the server is just the second adapter. Adding a third surface
  later (an HTTP API, a cron job) is the same move.

## Deterministic math in the data plane; the LLM narrates

Counts, totals, scoring, scheduling — anything that must be *exact* — lives in
pure functions, never in the model's head. The model's job is selection,
phrasing, and conversation. This is reason #4 above, and it's the single biggest
reliability win: the data plane can't hallucinate a sum.

## Bundled seed vs. gitignored mutable state

- **Bundled seed** (`data/<pkg>.seed.json`) ships read-only so the repo
  clones-and-runs cold. Keep it small, generic, and free of private data or
  unverified claims — it's in a public repo.
- **Mutable state** (`state.json`) lives in a user data dir (an env-var override,
  default `~/.<name>`) and is gitignored. A reviewer's experiments never dirty
  the repo; real user data never lands in a commit.

## Dual transport from one codebase

`_resolve_transport` picks stdio by default (Claude Desktop launches the server
as a subprocess) or streamable-HTTP via `--http` / `<PREFIX>_HTTP=1` (so the same
server can be added as a remote custom connector by URL). It's factored out from
`main()` so transport selection is unit-testable without binding a port.

## Remote-safe I/O

Once someone *runs* the server remotely (not just reads the repo), server-side
file paths stop being reachable by the caller. So:

- **Return content inline**, not just a path. `export_report` writes the file
  *and* returns the rendered text, so a remote caller who can't read the server's
  disk still gets the result.
- **Accept pasted content**, not only a server-side path. When you add an
  importer, take the data as text in addition to (or instead of) a file path.
- **Default writes to a known location** under the data dir, not the process cwd
  — which is unpredictable when a desktop client launches the process.

## Tests that match the architecture

- `test_core.py` — the pure functions, on stdlib alone. The bulk of domain
  coverage belongs here.
- `test_server_tools.py` — the tool *contract*, called in-process against a
  sandboxed data dir: happy-path round-trip, that state flows through to the
  summary/export, and error paths. `importorskip("mcp")` so it skips cleanly
  without the SDK.
- `test_server_imports.py` — tools-present smoke test + transport selection.

When you add a tool, add a tool-layer test for it; when you add domain logic, add
a pure-core test. Don't rely on the import smoke test alone.
