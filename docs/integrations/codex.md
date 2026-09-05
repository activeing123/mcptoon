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
mcptoon manifest --slim              # names + param types (88.5% smaller than JSON)
mcptoon call <server> <tool> '<json>' --toon  # call with token-optimized output
```
```

## Auto-configure

```bash
export MCPTOON_AGENT_TYPE=codex
```
