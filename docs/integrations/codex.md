# Codex (OpenAI) Integration

## Setup

```bash
pip install mcptoon
```

## Usage in AGENTS.md

Add `mcptoon` commands to your `AGENTS.md` file:

```markdown
## Tool Usage

When you need MCP tools, use mcptoon:

```bash
mcptoon manifest --compact           # list available tools
mcptoon manifest --slim              # get schemas (93% smaller)
mcptoon call <server> <tool> '<json>' --toon  # call with token-optimized output
```
```

## Auto-configure

```bash
export MCPTOON_AGENT_TYPE=codex
```
