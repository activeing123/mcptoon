# Cursor Integration

## Setup

```bash
pip install mcptoon
```

## Usage in AGENTS.md

Add `mcptoon` commands to your `AGENTS.md` file (Cursor's current rules system
reads `AGENTS.md` and `.cursor/rules/*.mdc`; the legacy `.cursorrules` file is no
longer documented and may be ignored):

```
When you need to search the web, run:
  mcptoon call brave-search search '{"query":"..."}' --toon

When you need to fetch a URL, run:
  mcptoon call fetch fetch '{"url":"..."}' --toon

To see available tools:
  mcptoon manifest --compact
```

## Auto-configure

```bash
export MCPTOON_AGENT_TYPE=claude  # Cursor uses Claude under the hood
```

## Config location

mcptoon config lives at `~/.mcptoon/config.json`, shared across all agents.
Project-level override at `./.mcptoon.json`.
