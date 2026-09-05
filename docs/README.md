# Integration Guides

mcptoon works with any agent that can run shell commands.

| Agent | Guide |
|-------|-------|
| Claude Code | [claude-code.md](integrations/claude-code.md) |
| Cursor | [cursor.md](integrations/cursor.md) |
| OpenCode | [opencode.md](integrations/opencode.md) |
| Codex (OpenAI) | [codex.md](integrations/codex.md) |

## Quick start for any agent

```bash
pip install mcptoon
mcptoon init
mcptoon manifest --compact
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

## Tools

- **[MCP Context Tax calculator](tools/token-tax/)** — what your own tool listing costs
  in tokens, in dollars per month, and as a share of your context window. Sliders, not
  a blog post; it runs entirely in your browser and nothing is uploaded.

This page is published at <https://activeing123.github.io/mcptoon/>.
