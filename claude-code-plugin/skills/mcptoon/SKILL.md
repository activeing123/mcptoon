---
name: mcptoon
description: Compress MCP tool discovery with the mcptoon CLI. Trigger when a session has a large MCP tool catalog (many servers/tools), when the user mentions token cost, tool discovery, mcptoon, or asks to list/call MCP tools efficiently. mcptoon compresses 71,929 tokens of tool schemas to 581 (-99.2%) and serves as an MCP 2026-07-28 stateless-first bridge.
---

# mcptoon — MCP tool-catalog compression

mcptoon is a zero-dependency CLI already on this machine (auto-installed by the
plugin's session hook). It gives you a compressed view of the user's MCP tools
and calls them back.

## When to use what

| Situation | Command |
|---|---|
| User asks "what tools do I have" / you need the tool catalog | `mcptoon manifest` (compact names only — ~2.2 tokens/tool) |
| You need one tool's real parameter schema before calling | `mcptoon inspect <server> <tool>` |
| Find a tool by capability | `mcptoon search <query>` |
| Call a tool | `mcptoon call <server> <tool> '{"arg":"value"}'` |
| You don't know which server owns the tool | `mcptoon call --auto <tool> '{...}'` |
| Huge JSON argument | `mcptoon call <server> <tool> --stdin` |
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
5. The bundled `mcptoon serve` bridge (auto-started via the plugin's
   `.mcp.json`) already compresses tool discovery for the host agent. Use the
   CLI commands above when working in a terminal context or when the bridge
   is not connected.

## Setup & repair

- Automatic: the plugin's SessionStart hook installs/updates nothing after
  the first successful run; it only reports status.
- Manual/repair: run the `/mcptoon-setup` command.
- Update the CLI: `pip install --upgrade mcptoon` (zero-dependency wheel,
  128KB, installs in seconds).
