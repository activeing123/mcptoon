# OpenCode Integration

## Setup

```bash
pip install mcptoon
```

## Usage in custom commands

Add `mcptoon` to your OpenCode custom commands:

```bash
# In your command definitions:
mcptoon manifest --slim          # list tools with schemas
mcptoon call <server> <tool> '{"key":"value"}' --toon
```

## Auto-configure

```bash
export MCPTOON_AGENT_TYPE=opencode
```

## Sharing config

mcptoon uses `~/.mcptoon/config.json` — the same file works for Claude Code, Cursor, OpenCode, and any other agent. Configure once, use everywhere.
