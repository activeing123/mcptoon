# ADR-0001: CLI Mode over MCP Protocol

## Status
Accepted (2026-08-16)

## Context
MCP protocol injects tool schemas into LLM context via schema injection. Each tool's JSON Schema consumes context tokens.

Industry research confirms:
- CLI Agent vs MCP Agent comparison (75 tests): CLI wins across the board
  - Token cost 10-32x lower
  - Reliability ~100% vs MCP's 72%
- Perplexity dropped MCP support (token overhead too high)
- Anthropic internal research: shell scripts save 98.7% tokens vs MCP
- 3-4 MCP servers consume ~150K tokens (before any work starts)

## Decision
mcptoon uses CLI mode instead of MCP client mode:
1. Agent calls MCP tools via shell commands (`mcptoon call <server> <tool>`)
2. Tool schemas stay on disk, never injected into LLM context
3. Only compact output (TOON/SLIM) enters context — when the user requests it
4. Direct-call mode: skill files write CLI commands → 0 tokens

## Consequences
- ✅ 0 schema token injection (vs Claude Desktop's 90K+ tokens)
- ✅ Any shell-capable agent can use it (no MCP SDK integration needed)
- ✅ Multiple agents share one config
- ⚠️ Agent needs to know tool names to call them (but can discover via `manifest`)
- ⚠️ Not a standard MCP client (but can export MCP format via `--format mcp`)
