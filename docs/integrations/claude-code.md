# Claude Code Integration

## Setup

```bash
pip install mcptoon
```

## Usage in SKILL.md

Write `mcptoon` commands directly in skill files:

```markdown
---
name: web-search
description: Search the web using MCP tools
---

## Execution

```bash
# Discover available tools (97% smaller than JSON)
mcptoon manifest --compact

# Call a search tool
mcptoon call brave-search search '{"query":"AI token optimization"}' --toon

# Get tool schemas in compact form
mcptoon manifest --slim
```
```

## Auto-configure

Set environment variable so all calls use TOON automatically:

```bash
export MCPTOON_AGENT_TYPE=claude
```

## Common patterns

### Add a tool mid-task

Your agent can self-serve MCP tools without human intervention:

```bash
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon doctor  # verify
mcptoon call github search_repos '{"query":"token optimization"}' --toon
```

### List all configured tools

```bash
mcptoon manifest --compact
# Output: search_web fetch_url create_issue read_file ...
```

### Get schemas for tool selection

```bash
mcptoon manifest --slim
# Output: search_web|query:s*|num:n fetch_url|url:s* ...
```
