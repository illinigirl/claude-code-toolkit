# claude-code-toolkit

A small toolkit of [Claude Code](https://code.claude.com) skills, distributed as
an installable **plugin marketplace**. Skills plus three hooks today (failure-mode
flagging, a context-threshold alert, and a coverage nudge); room to grow into
agents and MCP servers.

## Skills

| Skill | Command | What it does |
|---|---|---|
| [scaffold-mcp](skills/scaffold-mcp/) | `/scaffold-mcp` | Generate a new Python MCP server — a runnable, tested, ruff-clean skeleton in the pure-core + thin-adapters shape (FastMCP, dual stdio/HTTP transport, CLI adapter, one I/O module, bundled seed, tests, CI, CLAUDE.md, pyproject). |
| [verify-mcp](skills/verify-mcp/) | `/verify-mcp` | Health-check an MCP server: venv + ruff + pytest, import the server to prove its tools register, inventory the `@mcp.tool()` surface (count + missing docstrings — the contract Claude reads), then report a GREEN/RED verdict with the specific cause on failure. Scaffold builds it; verify proves it. |
| [public-ready](skills/public-ready/) | `/public-ready` | Audit a repo for public release — scan tracked files for secrets, PII, and interview/portfolio framing; verify tests + lint are green; check LICENSE / README / .gitignore / CI — then publish (`gh repo create`) on your approval. |
| [handoff](skills/handoff/) | `/handoff` | Write a `PICKUP-*.md` session handoff (task, what's done, what's in flight, next steps, key paths, working norms) so a fresh session resumes cold. Stays local, never committed. |
| [failure-scan](skills/failure-scan/) | `/failure-scan` | Review the current diff against the failure-mode catalog — the judgment classes a hook can't catch (plausible-but-wrong AI output, biased per-segment stats, dispatch-order coupling) — reporting concrete risks with each class's verify questions and fix pattern. |
| [design-note](skills/design-note/) | `/design-note` | Write a structured `<feature>-DESIGN.md` before building — problem, the core reframe, the design with options + tradeoffs, edge cases, and open questions to decide at build time. |
| [orchestrate](skills/orchestrate/) | `/orchestrate` | Recommend a good use of subagents — walk a 2-level decision tree (inline / single agent / multi-agent → pattern), defend item independence before any fan-out, hand back a copy-paste Agent/Workflow snippet, and run it only on your go-ahead. |
| [claude-md-audit](skills/claude-md-audit/) | `/claude-md-audit` | Audit a CLAUDE.md for health (concision, currency, usefulness, redundancy, length vs a budget) and, on approval, tighten it + move reference material to on-demand skills (stale guidance to `CLAUDE.archive.md`). CLAUDE.md is the index; skills are the chapters. |
| [memory-audit](skills/memory-audit/) | `/memory-audit` | Audit Claude Code's auto memory (`MEMORY.md` + topic files) for the 200-line / 25KB load cutoff (entries past it are silently dropped), staleness, and contradiction; on approval, tighten `MEMORY.md` to a lean index and move detail to on-demand topic files. |
| [note](skills/note/) | `/note` | Frictionless note-to-self — dump a thought and it's auto-classified into a bucket (`note`/`skill`/`mcp`/`todo`) under `~/.claude/notes/`, no category-picking. Bare `/note` lists everything; `/note <bucket>` lists one. |
| [coverage-audit](skills/coverage-audit/) | `/coverage-audit` | Audit a project's coverage for **negative space** — run line coverage, then judge the misses against the gaps agent-written suites predictably leave (empty, boundary, error paths, scale/pagination, time, untested adapters, tests that can't fail). Reports the top gaps ranked by silent-failure risk + the cheapest tests to add, then proves its own completeness with a shipped validator (`checklist.py`). Verify proves it runs; coverage-audit proves it's protected. |

## What `/scaffold-mcp` generates

It produces a complete, runnable project — not a snippet. One invocation gives a
tested, ruff-clean MCP server skeleton that passes its own suite out of the box:

```text
$ /scaffold-mcp   (→ scaffold.py --name trip-logger --domain trip)

trip-logger/
├── src/triplogger/
│   ├── server.py      FastMCP server — dual stdio / HTTP transport
│   ├── core.py        pure domain logic, no I/O — the part you replace
│   ├── store.py       JSON-file persistence (the one I/O module)
│   ├── cli.py         thin CLI adapter over the same core
│   ├── data/…seed.json   bundled seed, packaged so any install runs immediately
│   └── models.py · exports.py · __init__.py
├── tests/             conftest + core/server tests (green on generation)
├── .github/workflows/ CI (pytest)
├── CLAUDE.md          orientation: architecture + where to extend
├── setup.sh · preflight.sh   one-command venv setup + lint/test gate
└── pyproject.toml · requirements.txt · .gitignore · LICENSE · README.md

$ pytest -q      →  all passed
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

## Context-alert hook

Long sessions die ugly: context fills mid-task and auto-compact decides what
survives. This hook (auto-registered on install) alerts **while there's still
room to checkpoint on your terms** — pairing naturally with `/handoff`.

It fires on every tool call and prompt submit, reading the **actual token
`usage`** the API reported on the session's latest main-chain assistant message
(exact, lagging at most one call — unlike transcript-file-size heuristics,
which only ever grow and never recover after a compact). When usage crosses a
threshold it does three things once per crossing:

1. **OS notification** (`cmux` if installed, else macOS `osascript`) — so the
   alert lands even when the terminal isn't focused.
2. **In-terminal warning** via `systemMessage`.
3. **Tells Claude** (via `additionalContext`) to offer you the option of
   running the handoff skill at the next natural pause — accept and you get a
   PICKUP file; decline and the session continues normally.

Thresholds re-arm when usage drops back down (i.e. after a compact), so a
multi-day session can alert again on the next climb. Configure via env (e.g.
in `settings.json` `"env"`):

```jsonc
"CONTEXT_ALERT_THRESHOLDS": "75",     // comma-separated %, default "75"
"CONTEXT_ALERT_WINDOW": "1000000",    // tokens; default 200000
"CONTEXT_ALERT_DISABLED": "1"         // set to turn the hook off entirely
```

**If you run a 1M-context (`[1m]`) model, set `CONTEXT_ALERT_WINDOW` to
`1000000`.** It defaults to 200000 and can't be auto-detected — the transcript
records the base model id (e.g. `claude-opus-4-8`) with no `[1m]` marker — so
an un-set 1M session would alert at ~15% full. The OS notification works on
macOS (`cmux`/`osascript`) and Linux (`notify-send`); on other platforms the
in-terminal warning and handoff offer still fire. To silence just the desktop
popup, set `CONTEXT_ALERT_SILENT`; to turn the hook off completely, set
`CONTEXT_ALERT_DISABLED`.

`context-alert/test_hook.py` keeps it honest.

## Coverage-nudge hook + `/coverage-audit`

The same deterministic/judgment split as the failure-mode system, applied to
test coverage. The empirical observation behind it: agent-written coverage has
a predictable fingerprint — pure cores near 100%, while the same five gaps
recur everywhere (untested CLI adapters, never-exercised error branches,
single-page pagination stubs, dark seams to external APIs, tests that can't
fail).

- **A Stop + SessionStart hook** (auto-registered on install), with an
  opt-in-per-repo escalation keyed off the audit's own artifact:
  - *No `COVERAGE-AUDIT.md` in the repo yet:* at session pauses, the basic
    asymmetry check — source files changed but no test files → a one-line
    nudge. Quiet in repos with no tests at all.
  - *Repo has a `COVERAGE-AUDIT.md`* (you've run the audit once): the hook
    tracks **staleness** instead — any source change after the report fires
    the nudge, *whether or not tests also changed* (changed tests don't
    prove appropriate tests). At **session start**, a stale report tells
    Claude to run `/coverage-audit` at the first natural point — so after
    the first manual run, refreshes happen without you asking. Running the
    audit rewrites the report, which is what buys silence.
  - Either way: states only facts git can verify, never blocks, fails
    silent, debounced per distinct state (re-arms after a refresh or new
    drift).
- **`/coverage-audit`** is the judgment half: run real line coverage, read the
  misses against the eight-dimension checklist, rank findings by *how quietly
  the failure would ship*, and name the cheapest high-value tests to add. It
  reports **two numbers — raw and protected coverage**: every dark line must
  be covered, deleted, `pragma: no cover`-excluded *with a reason*, or on an
  accepted-residuals ledger. Protected = 100% is the GREEN bar; raw never
  needs to be, because an honest 94% with a full ledger beats a gamed 100%.
  The audit must then prove **its own** completeness: `checklist.py` parses
  the report and fails unless every dimension (including `residuals`) was
  explicitly checked — "not mentioned" can't masquerade as "checked and
  clean."

`coverage-nudge/test_hook.py` and `skills/coverage-audit/test_checklist.py`
keep both halves honest.

## Subagent-nudge hook + `/orchestrate`

The mechanisms for delegation (Agent, Workflow) exist and Claude is prompted to
use them — but nothing *proactively suggests* "this task is subagent-shaped,"
and the judgment of **whether to fan out, and in what shape** lives implicitly
in the model's head. This pair externalizes it, in the toolkit's usual
nudge-hook + judgment-skill shape.

- **A UserPromptSubmit hook** (auto-registered on install) that spots a
  subagent-shaped prompt — breadth/decomposition signals like "across the whole
  codebase", "for each X", "find/fix all Y", "comprehensive". Pure regex on the
  prompt text (no FS scan, no LLM call, ~no latency), **flag-for-review** not
  prescriptive ("this *might* parallelize; if the items aren't independent,
  ignore me"), fires **once per session**, and is fully silenceable with
  `SUBAGENT_NUDGE_DISABLED`. It doesn't orchestrate — it points Claude at
  `/orchestrate`.
- **`/orchestrate`** is the judgment half: a **2-level decision tree** — Level 1
  the quick call (inline / single agent / multi-agent), Level 2 the pattern
  (parallel-read, worktree-mutate, pipeline, loop-until-dry, adversarial-verify,
  judge-panel). It **advises → offers → executes only on your go-ahead**, hands
  back a copy-paste Agent/Workflow snippet, and surfaces the rough token cost +
  Workflow opt-in.
- Its load-bearing rule: **parallelism is only valid over INDEPENDENT items.**
  The skill must state *why* items are independent before recommending fan-out;
  if it can't, it picks a pipeline or stays inline. This is pinned to the
  `parallel-without-independence` entry in the failure-mode catalog.

`subagent-nudge/test_hook.py` keeps the trigger boundary honest — breadth fires,
single-target prompts (`audit this function`) stay silent.

## CLAUDE.md curator hook + `/claude-md-audit`

`CLAUDE.md` is injected into context **every session**, but nothing
re-evaluates it — so it only grows: reference material, restated lessons, and
stale facts accumulate, and every line is paid for on every session. The
guideline is ≤~200 lines. This pair keeps it there, on the principle **CLAUDE.md
is the index (always-relevant directives); skills are the chapters (on-demand
reference).**

- **A PostToolUse hook** (auto-registered on install) that fires only on
  `CLAUDE.md` / `AGENTS.md` edits (pure mechanical work — no FS scan beyond a
  line count, no LLM call). Two triggers: **prevention** — on *every* net
  addition (≥ `CLAUDE_MD_ADD_LINES`, default 1), it checks the new content on two
  axes: **kind** (directive=keep / reference=→ a skill / area-specific=→ a nested
  `CLAUDE.md` or `.claude/rules`) and **scope** (team→project file / personal→
  `~/.claude/CLAUDE.md` / secret-or-local→ `CLAUDE.local.md`). Cheapest bloat to
  remove is the bloat that never lands. **Budget** — when the file exceeds
  `CLAUDE_MD_LINE_BUDGET` (default 200), it nudges a full audit (debounced once
  per session). Silenceable with `CLAUDE_MD_AUDIT_DISABLED`; never auto-edits.
- **`/claude-md-audit`** is the judgment half: reads the whole file (+
  `CLAUDE.archive.md` if present) and reports per-section verdicts on concision,
  currency (stale facts vs the repo), usefulness, redundancy (incl. whether a new
  addition is already covered), scope, and length. On approval it routes each
  section: **keep / condense / extract-to-skill** (the primary release valve) **/
  move-to-nested-CLAUDE.md** (area-specific; `.claude/rules` for path-scoped) **/
  re-scope** (personal or secret content to `~/.claude/CLAUDE.md` or
  `CLAUDE.local.md`) **/ archive** (stale → `CLAUDE.archive.md`, not auto-loaded)
  **/ remove**. It never splits via `@import` (those load eagerly). Pairs with the
  `context-doc-bloat` + `stated-not-derived-doc-facts` catalog entries.

`claude-md-curator/test_hook.py` keeps the triggers honest — any net addition
and over-budget fire; pure tweaks (net-0), non-targets, and the archive file
stay silent.

## Memory curator hook + `/memory-audit`

The auto-memory twin of the CLAUDE.md pair. Claude Code's auto memory lives at
`~/.claude/projects/<project>/memory/` — a `MEMORY.md` index plus topic files —
and only the **first 200 lines / 25 KB of `MEMORY.md` load each session;
anything past that is silently not loaded.** A *hard* truncation, not a soft
budget — and since Claude writes this file itself across sessions, it grows on
its own, leaving tail entries that look stored but never reach context.

- **A PostToolUse hook** (auto-registered on install) that fires only on
  `MEMORY.md` edits inside a memory dir (mechanical: line + byte count). When the
  file crosses `MEMORY_LINE_BUDGET` (default 200) or `MEMORY_BYTE_BUDGET`
  (default 25 KB), it warns that the tail is now silently dropped and nudges
  `/memory-audit`. Debounced once per session; `MEMORY_AUDIT_DISABLED` off-switch;
  never auto-edits. Topic-file edits don't fire (only `MEMORY.md` truncates); a
  bare repo `MEMORY.md` outside a memory dir is ignored.
- **`/memory-audit`** is the judgment half: reads `MEMORY.md` + topic files and
  reports what's **below the cutoff (silently dropped now)**, staleness, and
  redundancy/contradiction (likely, since Claude wrote the notes incrementally).
  On approval it tightens `MEMORY.md` to a lean index and moves detail into
  on-demand topic files — the same **index/chapters** principle as CLAUDE.md.
  Catalog: `memory-index-overflow` (the hard-cutoff sibling of `context-doc-bloat`).

`memory-curator/test_hook.py` keeps it honest — over-budget by lines or bytes
fires; topic files, a non-memory-dir `MEMORY.md`, and net under-budget stay silent.

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
    verify-mcp/         SKILL.md — health-check an MCP server (GREEN/RED verdict)
    public-ready/       SKILL.md · audit.sh
    handoff/            SKILL.md · template.md
    failure-scan/       SKILL.md — review a diff against the catalog
    design-note/        SKILL.md — write a <feature>-DESIGN.md
    note/               SKILL.md — frictionless note-to-self capture
    coverage-audit/     SKILL.md · checklist.py · test_checklist.py
    orchestrate/        SKILL.md — the subagent-orchestration decision tree
    claude-md-audit/    SKILL.md — audit + trim a CLAUDE.md (index vs chapters)
    memory-audit/       SKILL.md — audit auto memory vs the load cutoff
  hooks/
    hooks.json          registers the failure-mode, context-alert, subagent-nudge, claude-md-curator, memory-curator + coverage-nudge hooks
  failure-modes/
    catalog.md          the bug-class catalog (the shared brain)
    rules.json          grep-able rules the hook runs
    hook.py · test_hook.py
  context-alert/
    hook.py · test_hook.py   context-threshold alert -> offers /handoff
  subagent-nudge/
    hook.py · test_hook.py   parallelizable-task nudge -> offers /orchestrate
  claude-md-curator/
    hook.py · test_hook.py   CLAUDE.md bloat nudge -> offers /claude-md-audit
  memory-curator/
    hook.py · test_hook.py   MEMORY.md load-cutoff nudge -> offers /memory-audit
  coverage-nudge/
    hook.py · test_hook.py   source-changed-without-tests nudge -> offers /coverage-audit
  .github/workflows/
    test.yml            CI — scaffolds + verifies a generated project end-to-end,
                        tests the worked example (and drives its demo), runs the
                        hook regression suite, validates manifests + frontmatter
  README.md · LICENSE
```

Validate the manifests with `claude plugin validate .`.

## License

[MIT](LICENSE).
