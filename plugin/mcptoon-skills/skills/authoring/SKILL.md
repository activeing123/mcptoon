---
name: authoring
description: Add or edit an MCP server entry in mcptoon's config correctly — stdio/streamable-http/sse shapes, command rules, placeholders, and validation.
---

# Author an MCP server entry for mcptoon

All servers live in `~/.mcptoon/config.json` under `mcpServers`. Edit there,
never in agent-side files, then run `mcptoon sync`.

## Entry shapes

stdio (local process):

```json
{
  "filesystem": {
    "type": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    "env": {"NODE_ENV": "production"}
  }
}
```

streamable-http / sse (remote):

```json
{
  "remote-tools": {
    "type": "streamable-http",
    "url": "https://example.com/mcp"
  }
}
```

## Hard rules for stdio commands

- `command` is ONE executable token: a bare name (`npx`, `uvx`, `mcptoon`) or a
  `./`-relative path inside a plugin. Never a shell string, never `bash -c`.
- Absolute paths in `command` are forbidden; use PATH or `./` relative.
- `args` is a list of strings. Shell metacharacters belong in args, not in
  `command`.

## Plugin entries

Agent Plugins are installed under `~/.mcptoon/plugins/<plugin>/` and merged
automatically with `"<plugin>:<server>"` names. Their paths can use
placeholders, expanded at install time:

- `${PLUGIN_ROOT}` — the installed plugin directory
- `${PLUGIN_DATA}` — the plugin's persistent data directory (survives upgrades)

Plugin-managed entries should be edited by updating the plugin (reinstall with
`--force`), not by hand-editing the merged config.

## Validation loop (always run after writing)

```bash
mcptoon doctor       # catches syntax, missing binaries, bad urls
mcptoon list         # confirm the server is visible
mcptoon health       # per-server connectivity, exit 1 if anything is dead
```

If you generated the entry from documentation, prefer `mcptoon install --npm /
--pip / --url` over hand-writing JSON — it fills the correct shape for you.

## Good tool hygiene (for server authors)

- Prefer fewer, well-described tools over many overlapping ones; agents pick
  tools by description.
- When a server ships a `SKILL.md` (Agent Plugins), keep the body actionable:
  concrete commands, exact flags, no marketing text.
