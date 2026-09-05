---
name: connect
description: Connect any AI agent to MCP servers through mcptoon — one config synced everywhere, one stdio gateway, 99.2% fewer tokens on tool discovery.
---

# Connect agents to MCP servers with mcptoon

mcptoon keeps one config (`~/.mcptoon/config.json`) as the single source of truth
for every MCP server an agent may use. It syncs that config into Claude Desktop,
Claude Code, Cursor, Codex, Cline, Windsurf and VS Code, and can expose all
servers through one stdio gateway (`mcptoon serve`).

## First move: look before you change anything

```bash
mcptoon list            # what servers are configured right now
mcptoon doctor          # config syntax + connectivity diagnosis
```

If `doctor` reports problems, fix those before adding anything new.

## Add servers

```bash
mcptoon discover                  # scan + probe locally installed MCP servers
mcptoon discover --write          # and write what was found into config
mcptoon add <name> --help         # see add options for stdio/http servers
mcptoon install <name> --npm @scope/pkg   # from npm
mcptoon install <name> --pip pkg          # from pip
mcptoon install <name> --url https://host/mcp   # streamable-http / sse
```

After editing `~/.mcptoon/config.json` by hand, validate with `mcptoon doctor`.

## Sync one config to every agent

```bash
mcptoon sync              # write config into all detected agents
mcptoon sync --dry        # preview only
mcptoon sync --agent claude   # one agent only
```

## Expose everything through one gateway (recommended for agents)

Instead of registering N servers in an agent, register ONE:

```json
{ "mcpServers": { "mcptoon": { "command": "mcptoon", "args": ["serve"] } } }
```

`mcptoon serve` speaks MCP over stdio and forwards to every configured server.
Benefits: one entry in the agent config, tool lists stay compact, and Plugin
skills appear as MCP prompts automatically.

## Token efficiency flags

Tool manifests can be huge. When calling mcptoon from a terminal, keep output
small on purpose:

```bash
mcptoon manifest --toon        # standard TOON format (30-60% saved)
mcptoon manifest --slim        # ultra-compact schemas (93% saved)
mcptoon manifest --compact     # names only (99.2% saved)
mcptoon search <query>         # find a tool without dumping the whole manifest
mcptoon inspect <server> <tool>   # full schema for exactly one tool
```

## Toggles

Single tools can be disabled without removing the server (agents then never see
them): toggle in `~/.mcptoon/config.json` on the server entry, then `mcptoon sync`.

## Rules of thumb

- Never edit agent-side config files directly; edit mcptoon's config and `sync`.
- `mcptoon watch` (if running) syncs on every save.
- Verify with `mcptoon health` — exit code 1 means something is down (CI-friendly).
