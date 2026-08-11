# Reddit Post Draft — r/LocalLLaMA

## Title
MCP tool schemas eat 10,000+ tokens per call. I built a CLI that brings it to 350. Zero deps, pure Python, works with every agent.

## Body

If you use MCP servers with Claude Code, Cursor, or any agent, you're burning a huge chunk of your context window on JSON structure — brackets, quotes, commas, repeated `"type":"object","properties":` declarations — before any actual thinking happens.

**The problem:** A single manifest call listing 96 tools costs ~2,000 tokens of JSON. With 5 MCP servers, that's 10,000+ tokens gone just on tool discovery. Every tool call returns results wrapped in `{"content":[{"type":"text","text":"..."}]}`. Over a conversation, you lose 30-55% of your 128K context to pure syntax.

**What I built:** [mcptoon](https://github.com/activeing123/mcptoon) — a CLI client that connects to any MCP server (stdio or HTTP) and outputs TOON (Token-Optimized Object Notation) instead of JSON.

| Operation | JSON tokens | mcptoon tokens | Savings |
|---|---|---|---|
| Tool discovery (96 tools) | ~2,000 | ~60 | **97%** |
| Tool result (structured data) | ~800 | ~350 | **56%** |
| Tool result (raw HTML/text) | ~1,000 | ~900 | **10%** |

The remaining tokens are real data (repo names, star counts, search results, web page content) — you can't compress that without losing information. What mcptoon strips is the JSON scaffolding.

**Key points:**

- **Zero dependencies** — pure Python stdlib, 50KB install
- **Works with every agent** — it's a CLI tool. If your agent can run shell commands, it can use mcptoon. Claude Code, Codex, OpenCode, Cursor, CatPaw — all of them.
- **One config for all agents** — configure MCP servers once in `~/.mcptoon/config.json`, every agent shares the same config
- **Cross-platform** — Windows, macOS, Linux
- **Safety features** — blocks dangerous operations (delete, drop, purge) by default, no telemetry, no credential storage

**Quick start:**

```bash
pip install git+https://github.com/activeing123/mcptoon.git

mcptoon init
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon manifest --toon
# → fetch:fetch

mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**How TOON works:**

```
JSON: {"name":"search","count":3,"active":true,"error":null}
TOON: name:search|count:3|active:T|error:∅
```

Pipes replace braces + quotes. Spaces replace brackets + commas. `T`/`F` for booleans. Same data, same semantics, fewer tokens.

**Repo:** https://github.com/activeing123/mcptoon

It's v0.1.0, ~1,700 lines of Python, zero third-party imports. Not on PyPI yet — install from GitHub for now.

Feedback welcome. Especially if you find it doesn't work with your MCP server setup — I want to fix that.
