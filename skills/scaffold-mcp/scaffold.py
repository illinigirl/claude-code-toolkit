#!/usr/bin/env python3
"""Generate a new MCP-server repo in the pure-core + thin-adapters shape.

Stdlib only — no install needed to run this. It reads the bundled `templates/`,
substitutes a handful of tokens (project / package / domain names), and writes a
runnable, ruff-clean, test-green skeleton: pure core + one I/O module + two thin
adapters (FastMCP server with dual stdio/HTTP transport, and a CLI), plus tests,
a bundled seed, CLAUDE.md, README, pyproject, license, and gitignore.

The generated repo is deliberately generic-but-real: it already exercises all
four reasons a capability earns an MCP (persist state, durable artifact, private
local data, exact compute), so its starter suite passes the moment it lands.
Every domain-specific spot is marked `# TODO(<domain>):` so you know where to
swap the toy core for your real logic.

    python scaffold.py --name trip-logger --domain trip --dest ~/dev

See the skill's SKILL.md for the conversational wrapper + the post-generate
verification (venv + pytest + ruff).
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"

# Each template (in templates/) maps to an output path. `{PACKAGE}` in a path is
# filled from the derived package name; file *contents* use `{{TOKEN}}` markers
# (substituted separately, below) so they never collide with these path braces.
MANIFEST: dict[str, str] = {
    "pyproject.toml.tmpl": "pyproject.toml",
    "requirements.txt.tmpl": "requirements.txt",
    "gitignore.tmpl": ".gitignore",
    "LICENSE.tmpl": "LICENSE",
    "README.md.tmpl": "README.md",
    "CLAUDE.md.tmpl": "CLAUDE.md",
    "seed.json.tmpl": "data/{PACKAGE}.seed.json",
    "init.py.tmpl": "src/{PACKAGE}/__init__.py",
    "models.py.tmpl": "src/{PACKAGE}/models.py",
    "core.py.tmpl": "src/{PACKAGE}/core.py",
    "exports.py.tmpl": "src/{PACKAGE}/exports.py",
    "store.py.tmpl": "src/{PACKAGE}/store.py",
    "server.py.tmpl": "src/{PACKAGE}/server.py",
    "cli.py.tmpl": "src/{PACKAGE}/cli.py",
    "conftest.py.tmpl": "tests/conftest.py",
    "test_core.py.tmpl": "tests/test_core.py",
    "test_server_tools.py.tmpl": "tests/test_server_tools.py",
    "test_server_imports.py.tmpl": "tests/test_server_imports.py",
}


def _identifier(text: str) -> str:
    """Lowercase, non-alphanumerics → underscore, collapse repeats, trim. Safe to
    drop into a Python function name (e.g. add_<this>)."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "record"


def derive_tokens(args: argparse.Namespace) -> dict[str, str]:
    """Compute every substitution from the CLI args, filling sensible defaults."""
    name = args.name.strip()
    package = args.package or re.sub(r"[^a-z0-9]+", "", name.lower()) or "server"
    domain = _identifier(args.domain or "record")
    domain_plural = _identifier(args.domain_plural) if args.domain_plural else f"{domain}s"
    env_prefix = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "MCP"
    description = args.description or (
        f"Self-contained MCP server for {domain_plural} — pure core + thin "
        f"adapters, deterministic data plane, dual stdio/HTTP transport."
    )
    return {
        "{{PROJECT_NAME}}": name,
        "{{PACKAGE}}": package,
        "{{DOMAIN}}": domain,
        "{{DOMAIN_PLURAL}}": domain_plural,
        "{{DOMAIN_TITLE}}": domain.capitalize(),
        "{{ENV_PREFIX}}": env_prefix,
        "{{DESCRIPTION}}": description,
        "{{AUTHOR}}": args.author,
        "{{YEAR}}": str(date.today().year),
    }


def render(text: str, tokens: dict[str, str]) -> str:
    for marker, value in tokens.items():
        text = text.replace(marker, value)
    return text


def generate(tokens: dict[str, str], dest: Path, force: bool) -> list[Path]:
    package = tokens["{{PACKAGE}}"]
    if dest.exists() and any(dest.iterdir()) and not force:
        raise SystemExit(
            f"refusing to write into non-empty {dest} (use --force to override)"
        )
    written: list[Path] = []
    for template_name, out_template in MANIFEST.items():
        src = TEMPLATES / template_name
        if not src.exists():
            raise SystemExit(f"missing template: {src}")
        out_path = dest / out_template.format(PACKAGE=package)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render(src.read_text(), tokens))
        written.append(out_path)
    return written


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scaffold-mcp",
        description="Scaffold a new MCP server in the pure-core + thin-adapters shape.",
    )
    p.add_argument("--name", required=True,
                   help="project / repo name, kebab-case (e.g. trip-logger)")
    p.add_argument("--package",
                   help="python package name (default: name with separators removed)")
    p.add_argument("--domain", default="record",
                   help="singular noun for the thing tracked (e.g. trip); drives tool names")
    p.add_argument("--domain-plural", dest="domain_plural",
                   help="plural form (default: domain + 's')")
    p.add_argument("--description", help="one-line project description for pyproject/README")
    p.add_argument("--author", default="Your Name", help="author name for pyproject/LICENSE")
    p.add_argument("--dest", default=".",
                   help="parent directory to create the project in (default: cwd)")
    p.add_argument("--force", action="store_true",
                   help="write even if the destination already has files")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    tokens = derive_tokens(args)
    dest = Path(args.dest).expanduser().resolve() / args.name
    written = generate(tokens, dest, args.force)

    name, package = tokens["{{PROJECT_NAME}}"], tokens["{{PACKAGE}}"]
    print(f"Scaffolded {name} → {dest}  ({len(written)} files)\n")
    print("Next steps (verify it's green):")
    print(f"  cd {dest}")
    print("  python3 -m venv .venv && .venv/bin/pip install -e '.[test]'")
    print("  .venv/bin/python -m pytest -q")
    print("  .venv/bin/ruff check .   # if ruff is installed")
    print()
    print("Demo it without an MCP client:")
    print(f"  PYTHONPATH=src python -m {package}.cli list")
    print(f"  PYTHONPATH=src python -m {package}.cli summary")
    print()
    print(f"Then open CLAUDE.md and replace the toy core (grep -rn 'TODO({tokens['{{DOMAIN}}']})').")


if __name__ == "__main__":
    main()
