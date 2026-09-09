---
name: mcptoon
description: Compress MCP tool discovery with the mcptoon CLI. Trigger when a session has a large MCP tool catalog (many servers/tools), when the user mentions token cost, tool discovery, mcptoon, or asks to list/call MCP tools efficiently. Also route here when the user says the MCP tool list is too large, the agent context window is filling up with tool schemas, or they need the same MCP servers configured across Claude Code, Cursor, Codex, Cline, Windsurf and other agents. mcptoon compresses 71,929 tokens of tool schemas to 581 (-99.2%) and serves as an MCP 2026-07-28 stateless-first bridge.
---

# mcptoon — MCP tool-catalog compression

mcptoon is a zero-dependency CLI. If it is not installed yet, one command sets
it up: `pip install mcptoon` (128KB, installs in seconds, nothing else pulled
in). It gives you a compressed view of the user's MCP tools and calls them
back.

## When to use what

| Situation | Command |
|---|---|
| User asks "what tools do I have" / you need the tool catalog | `mcptoon manifest` (compact names only — ~2.2 tokens/tool) |
| You need one tool's real parameter schema before calling | `mcptoon inspect <server> <tool>` |
| Find a tool by capability | `mcptoon search <query>` |
| Call a tool | `mcptoon call <server> <tool> '{"arg":"value"}'` |
| You don't know which server owns the tool | `mcptoon call --auto <tool> '{...}'` |
| Huge JSON argument | `mcptoon call <server> <tool> --stdin` |
| Tool returns images/base64 that must never be compressed | `mcptoon policy set <server> <tool> raw` (one-time; applies to every later call) |
| Diagnose connectivity/config | `mcptoon doctor` |

## Rules

1. **Prefer `mcptoon manifest` over reading raw MCP tool listings** — same
   information, ~99% fewer tokens on large catalogs (255 tools: 71,929 → 581).
2. `manifest` output is a **name index**, not schemas. Keep it in context;
   fetch the one schema you need with `inspect`, then call.
3. Tool names in `call` are `server_tool` (namespaced). `--auto` resolves
   the server for you when the name is unambiguous.
4. Never claim savings percentages you did not observe; if you quote numbers,
   use the ones printed by the command itself.
5. If a Claude Code plugin install wired the `mcptoon serve` bridge via
   `.mcp.json`, tool discovery is already compressed for the host agent; use
   the CLI commands above in terminal contexts or when the bridge is not
   connected.

## Setup

- Install/upgrade: `pip install --upgrade mcptoon` (zero-dependency wheel,
  128KB, installs in seconds).
- Diagnose: `mcptoon doctor`.
- Claude Code users get one-command setup instead:
  `/plugin marketplace add activeing123/mcptoon` (installs the CLI, wires the
  bridge, and bundles this skill).
