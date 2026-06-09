#!/usr/bin/env bash
# One-command setup. Portable: works wherever the repo is cloned.
#   git clone … && cd book-tracker && ./setup.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Guard the macOS gotcha up front: a venv under Documents/Desktop/Downloads is
# unreadable by Claude Desktop (TCC), which fails with "Operation not permitted".
case "$DIR" in
  "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*)
    echo "⚠️  This repo is in a macOS-protected folder:"
    echo "      $DIR"
    echo "   Claude Desktop can't read a virtualenv here. Move the repo to a"
    echo "   normal location (e.g. ~/dev/book-tracker) and re-run ./setup.sh."
    echo "   (Continuing anyway — the CLI works, but the Desktop connector won't.)"
    echo ;;
esac

echo "Building virtualenv + installing…"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[test]" ruff

CMD="$DIR/.venv/bin/book-tracker"
cat <<CFG

✅ Installed.

To use it in Claude Desktop, add this under "mcpServers" in:
  ~/Library/Application Support/Claude/claude_desktop_config.json

  "book-tracker": { "command": "$CMD" }

then FULLY QUIT (⌘Q) and reopen Claude Desktop.

CFG

echo "Running preflight…"
bash "$DIR/preflight.sh"
