#!/usr/bin/env bash
# Pre-demo / post-setup check. Reproduces what Claude Desktop does and verifies
# the server will actually run on THIS machine. GREEN = safe to demo. Portable:
# resolves its own location, so it works wherever the repo is cloned.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="$DIR/.venv/bin/book-tracker"
DATA="${BOOKTRACKER_DATA_DIR:-$HOME/.book-tracker}"
fail=0
ok(){ echo "  ✅ $1"; }
bad(){ echo "  ❌ $1"; fail=1; }

echo "── book-tracker preflight ──"

# 1. Not in a macOS-protected folder (Documents/Desktop/Downloads) — Claude
#    Desktop can't read a venv there ("Operation not permitted").
case "$DIR" in
  "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*)
    bad "repo is in a macOS-protected folder ($DIR) — move it (e.g. ~/dev) and re-run setup";;
  *) ok "repo location is outside protected folders";;
esac

# 2. The exact command Claude Desktop launches exists + is executable
[ -x "$CMD" ] && ok "launch command present" || bad "launch command missing — run ./setup.sh: $CMD"

# 3. Clean MCP stdio handshake (no PermissionError / fatal import)
if [ -x "$CMD" ]; then
  resp="$( ( printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"preflight","version":"1"}}}'; sleep 1 ) | env BOOKTRACKER_DATA_DIR="$(mktemp -d)" "$CMD" 2>/tmp/bt_preflight_err.txt | head -c 400 )"
  if grep -qiE "PermissionError|Fatal Python error|not permitted" /tmp/bt_preflight_err.txt; then
    bad "server crashed on launch:"; sed 's/^/      /' /tmp/bt_preflight_err.txt | head -4
  elif echo "$resp" | grep -q '"serverInfo"'; then ok "MCP handshake clean (responds to initialize)"
  else bad "no valid MCP response; stderr:"; sed 's/^/      /' /tmp/bt_preflight_err.txt | head -4; fi
fi

# 4. Library has data so live tools return real output
genres="$(cd "$DIR" && PYTHONPATH=src BOOKTRACKER_DATA_DIR="$DATA" python3 -m booktracker.cli top-genres 2>/dev/null)"
echo "$genres" | grep -q "You read" \
  && ok "library has books (data dir: $DATA)" \
  || bad "library EMPTY at $DATA — run: PYTHONPATH=src python3 -m booktracker.cli samples on"

echo "───────────────────────────"
[ "$fail" = 0 ] && echo "GREEN — safe to demo" || echo "RED — fix above first"
exit $fail
