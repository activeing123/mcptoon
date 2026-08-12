# Integration Guides

mcptoon works with any agent that can run shell commands.

| Agent | Guide |
|-------|-------|
| Claude Code | [claude-code.md](integrations/claude-code.md) |
| Cursor | [cursor.md](integrations/cursor.md) |
| OpenCode | [opencode.md](integrations/opencode.md) |
| CatPaw | [catpaw.md](integrations/catpaw.md) |
| Codex (OpenAI) | [codex.md](integrations/codex.md) |

## Quick start for any agent

```bash
pip install mcptoon
mcptoon init
mcptoon manifest --compact
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```
