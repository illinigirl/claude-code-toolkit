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

- **Bundled seed** (`src/<pkg>/data/<pkg>.seed.json`) ships read-only *inside
  the package* — resolved via importlib.resources, so it's found from a clone,
  an editable install, or a built wheel alike. Keep it small, generic, and free
  of private data or unverified claims — it's in a public repo.
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

## When this shape doesn't fit — and what survives anyway

The layout encodes three assumptions: **state is local and file-shaped**
(`store.py` writing JSON), **the interesting logic is deterministic compute
over that state** (a `core.py` worth unit-testing on stdlib), and **the server
is single-user** (whoever launched the process owns the data). That's the
personal-data class of MCP, and it's what the scaffold targets. Three other
classes strain the literal file list — the seams generalize, the files don't.

**API-wrapper servers** — the "store" is someone else's service (a music API,
a finance aggregator, a SaaS). Keep the one-I/O-module rule but read it as
"the ONLY module that talks to the outside world": `store.py` becomes
`<service>_client.py`, and auth, token refresh, rate limits, caching, and
pagination live there. Expect the balance to invert: the pure core shrinks to
whatever scoring/merging math you have, and the tests that matter most become
contract tests against recorded responses rather than stdlib unit tests.
*Still a good starting point* — scaffold, then replace `store.py`'s internals;
the adapters, dual transport, and test layering carry over unchanged.

**Stateful-session servers** — the resource is a live connection (a held
websocket, a browser, a long-lived DB session, a device). There's little pure
compute to extract; the hard problem is lifecycle — connect, hold, recover,
disconnect — and this layout has no opinion about it. *Partial starting
point* — the adapter layer, transport selection, and docstring discipline
still apply, but plan a session/lifecycle module the scaffold doesn't give
you, and accept that the "runs without an MCP client" CLI may shrink to a
smoke script.

**Multi-user remote servers** — shared database, per-user identity, OAuth.
The data-dir model is wrong by construction: state is shared and remote,
identity comes from the request, and the read path inherits data-growth
failure modes a local JSON file never has. *Starting point for development
only* — beginning local-and-stdio with the pure core extracted is the right
first move, and the dual-transport server is the bridge to remote, but the
store layer gets replaced wholesale and auth + deployment are net-new work
the scaffold deliberately doesn't template (hosts differ too much to guess).

One more assumption worth naming: **tools-only.** MCP also has resources,
prompts, sampling, and elicitation. A server whose value is exposing
resources (say, a documentation server) or long-running jobs with progress
notifications needs a different `server.py` surface regardless of how pure
the core is.

What survives in *every* class — the actual invariants:

1. **One seam to the outside world** — file, API, DB, or device; everything
   else stays testable without it.
2. **Pure functions wherever exactness matters** — the fraction varies, the
   move doesn't.
3. **Thin tool layer, docstrings as the contract** — that's what the model
   reads.
4. **A second way to drive it without an MCP client** — a CLI when the core
   is fat, a smoke script when it isn't.
5. **Remote-safe I/O** — inline content, pasted input, confined paths, the
   moment the server might leave the laptop.

In short: the scaffold's transferable value is the seams plus the green
wiring, not the file list. What varies by class is how much of `store.py`
and `core.py` survive contact with the real domain.

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
