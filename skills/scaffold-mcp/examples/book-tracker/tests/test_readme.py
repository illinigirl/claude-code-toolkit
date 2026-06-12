"""README freshness — stated facts must match reality or the build goes red.

The disease this guards against: a count stated in prose ("The tools (17)")
silently drifts when the code changes, because nothing ties the claim to the
thing it describes. Policy (same triage as protected coverage): a volatile
fact in the README is either PINNED by a test here, DERIVED by tooling, or
DELETED from the prose — never just stated.

This pins README tool-count == @mcp.tool() decorators (stdlib, runs without
the MCP SDK). test_server_imports.py separately pins decorators == FastMCP's
live tool surface, so the README claim is transitively checked against what
a connected Claude actually sees.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_README = _ROOT / "README.md"
_SERVER = _ROOT / "src" / "booktracker" / "server.py"

_CLAIM = re.compile(r"^## The tools \((\d+)\)$", re.MULTILINE)


def test_readme_tool_count_matches_the_decorators():
    readme = _README.read_text()
    m = _CLAIM.search(readme)
    # Two distinct failures on purpose: a reworded heading must not silently
    # unguard the claim.
    assert m, ("README tool-count claim not found — if the '## The tools (N)' "
               "heading was reworded, update _CLAIM here so the count stays pinned")
    claimed = int(m.group(1))

    actual = len(re.findall(r"^@mcp\.tool\(\)", _SERVER.read_text(), re.MULTILINE))
    assert claimed == actual, (
        f"README claims {claimed} tools; server.py registers {actual} — "
        "update the README heading (or you added/removed a tool and the "
        "docs didn't move with it)")
