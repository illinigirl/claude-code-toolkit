"""book-tracker — a worked example of the scaffold-mcp pattern.

A self-contained MCP server in the pure-core + thin-adapters shape: a
deterministic data plane (exact compute over your reading log, persisted state,
a durable export) that the LLM narrates, exposed over dual stdio/HTTP transport.

This is the "after" the scaffold's generic skeleton grows into — a real domain
(books you've read / are reading / want to read) wired through the same
architecture, so you can see what adapting the toy core actually looks like."""

__version__ = "0.1.0"
