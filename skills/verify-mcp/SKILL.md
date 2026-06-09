---
name: verify-mcp
description: Verify an MCP server (in the scaffold-mcp pure-core + thin-adapters shape) is green and well-formed — set up a venv, run ruff + pytest, import the server to confirm its tools register, and inventory the @mcp.tool() surface (count + any missing docstrings, since docstrings are the contract Claude reads). Reports a readable health summary with a GREEN/RED verdict and, on failure, the specific cause. Use when checking an MCP project is ready to demo, commit, or ship. Pairs with scaffold-mcp ("scaffold builds it, verify proves it").
argument-hint: [project-dir] [--run "<command>"]
---

# /verify-mcp

Run a full health check on an MCP server and report **detailed, interpreted**
results — not just an exit code. Built for projects in the `scaffold-mcp` shape
(pure core + thin adapters, `src/<pkg>/server.py`, `tests/`, `pyproject.toml`),
but the checks degrade gracefully on any Python MCP.

The point versus a shell script: you **interpret** the output — name which test
failed and why, list the ruff findings, flag undocumented tools — and assemble a
single readable verdict.

## 1. Locate the project

- Target dir = the first argument, or the current working directory.
- Confirm it looks like the pattern: a `pyproject.toml`, a `src/<pkg>/` package,
  and a `tests/` dir. Find the package: `ls src` (the single entry is `<pkg>`).
- If there's no `src/<pkg>/server.py`, say so and check what's there before
  proceeding — don't assume.

## 2. Set up + install

Use a venv inside the project (reuse `.venv` if present):

```bash
cd <project-dir>
python3 -m venv .venv
.venv/bin/pip install -q -e ".[test]" ruff
```

If `pip install` can't reach the network, note it: the tool-layer tests
`importorskip("mcp")` and skip rather than fail, so a partial result is still
meaningful — report it as such rather than calling it green.

## 3. Run the checks

Run all of these, capturing output (don't stop at the first failure — you want
the full picture for the report):

- **Lint:** `.venv/bin/ruff check .` → clean, or capture the findings.
- **Tests:** `.venv/bin/python -m pytest -q` → parse the `N passed` / `N failed`
  line; on failure capture which tests and their assertions.
- **Smoke (import):** confirm the server module imports and registers its tools:
  ```bash
  PYTHONPATH=src .venv/bin/python -c "import <pkg>.server; print('import OK')"
  ```
  A clean import means the `@mcp.tool()` wiring loaded without error.
- **Tool inventory + contract** (no deps needed — static parse of `server.py`):
  ```bash
  .venv/bin/python - "src/<pkg>/server.py" <<'PY'
  import ast, sys
  tree = ast.parse(open(sys.argv[1]).read())
  tools = []
  for node in ast.walk(tree):
      if isinstance(node, ast.FunctionDef):
          for d in node.decorator_list:
              f = d.func if isinstance(d, ast.Call) else d
              if isinstance(f, ast.Attribute) and f.attr == "tool":
                  tools.append((node.name, ast.get_docstring(node) is not None))
  documented = sum(1 for _, ok in tools if ok)
  print(f"tools={len(tools)} documented={documented}")
  undoc = [n for n, ok in tools if not ok]
  if undoc:
      print("undocumented=" + ",".join(undoc))
  PY
  ```
  Docstrings matter here specifically: they're the contract Claude reads at
  runtime, so an undocumented tool is a real (if non-fatal) gap.

## 4. Optional: drive a real command (`--run`)

If `--run "<command>"` is passed, also execute it from the project with the venv
and `src/` on the path, and include its output as a "Smoke (run)" line — this is
the convincing "call a real tool, watch it answer" beat:

```bash
PYTHONPATH=src .venv/bin/<command>      # e.g. --run "python -m booktracker.cli top-genres"
```

Report the command's exit status and a few lines of its output. Without `--run`,
the smoke check stays import-only (universal — never guesses an entry command).

## 5. Report

Assemble one readable health summary. Use ✅ for pass, ❌ for fail, ⚠️ for a
caveat (e.g. tests skipped offline, or undocumented tools). Example:

```
<project> — MCP health check
  ✅ Install        deps resolved
  ✅ Lint (ruff)    All checks passed
  ✅ Tests          28 passed, 0 failed
  ✅ Smoke          server imports cleanly
  ✅ Contract       15 tools, 15 documented
  ──────────────────────────────────────────
  Verdict: GREEN — ready to demo / ship
```

On a failure, keep the same shape but put the **specific** cause under the ❌ line
and add your read on the likely fix. Examples:

```
  ❌ Tests          26 passed, 2 failed
       test_top_genres_over_seed — expected Fantasy=4, got 3
       likely: a seed book's status or genre changed
```
```
  ⚠️ Contract       15 tools, 13 documented
       undocumented: mark_status, set_goal — add a docstring (Claude reads it)
```

The **verdict** is GREEN only if install + lint + tests + smoke all pass. Tests
skipped for lack of the SDK, or undocumented tools, are ⚠️ caveats — call it
"GREEN with caveats," not a clean green. Be honest; the value is an accurate
picture, not a green light.

## Notes

- Read-only on the project's source — it installs into `.venv` and may create
  `.pytest_cache` / `.ruff_cache`, all gitignored by the scaffold. It does not
  modify tracked files.
- Pairs with `scaffold-mcp`: scaffold generates the server, `verify-mcp` proves
  it's green and well-formed before you demo, commit, or publish.
- Don't claim a result you didn't run. If a step errored for an environmental
  reason (no network, missing python), say that plainly instead of guessing.
