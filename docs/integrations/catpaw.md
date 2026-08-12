# CatPaw Integration

## Setup

```bash
pip install mcptoon
```

## Usage in skill files

Write `mcptoon` commands in SKILL.md files:

```markdown
---
name: mcp-tools
description: Use MCP tools via mcptoon
---

## Execution

```bash
mcptoon manifest --compact
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```
```

## Auto-configure

```bash
export MCPTOON_AGENT_TYPE=claude
```
