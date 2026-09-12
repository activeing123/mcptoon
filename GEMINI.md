# mcptoon for Gemini CLI

mcptoon is a zero-dependency Python CLI that manages and calls MCP servers
with token-efficient discovery. This extension registers `mcptoon serve` as
one stdio MCP bridge: a single connection exposes every server in your
mcptoon config, so Gemini CLI does not need a separate MCP entry per server.

## Prerequisites

```bash
pip install mcptoon
mcptoon discover --write   # or: mcptoon add <name> --command ... --args ...
```

## Bridge mode (this extension)

Servers from `~/.mcptoon/config.json` appear as tools on one MCP server
(server-prefixed names). Per-tool output compression is configurable:
`mcptoon policy <server> <tool> toon|slim|raw`.

## CLI mode (shell, zero injected schemas)

From a shell tool, mcptoon keeps full tool schemas out of the prompt
entirely; discovery costs a compact name index instead of JSON schemas:

```bash
mcptoon manifest                 # compact tool index across all servers
mcptoon inspect <server> <tool>  # full schema, on demand
mcptoon call <server> <tool> '{"k":"v"}'
mcptoon call --auto <tool> ...   # auto-find the server
```

## Notes

- The first `tools/list` on the bridge pre-warms every configured server;
  with slow npx-based servers this can take tens of seconds. CLI mode has
  no such up-front cost.
- Config lives at `~/.mcptoon/config.json`; docs and releases:
  https://github.com/activeing123/mcptoon
