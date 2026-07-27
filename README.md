# mcptoon

<p align="center">
  <strong>Stop feeding JSON to your LLM. Save 40-60% tokens on every MCP tool call.</strong>
</p>

<p align="center">
  <a href="#installation"><img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg" /></a>
  <a href="https://pypi.org/project/mcptoon/"><img alt="PyPI" src="https://img.shields.io/pypi/v/mcptoon.svg" /></a>
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/license-Apache%202.0-green.svg" /></a>
  <a href="#why-mcptoon"><img alt="zero deps" src="https://img.shields.io/badge/dependencies-zero-orange.svg" /></a>
  <a href="README.zh-CN.md">中文文档</a>
</p>

---

## The Problem

You're using [MCP](https://modelcontextprotocol.io/) servers — fetch, GitHub, filesystem, search — and every time an AI agent calls a tool, it gets back a wall of JSON. That JSON eats your context window. A 96-tool manifest? **2,000+ tokens.** Search results? **3,000+ tokens.** Half your context is gone before the agent even starts thinking.

## The Solution

**mcptoon** is a CLI client that talks to any MCP server — but outputs **TOON**, a token-efficient notation that compresses JSON by 40-60%:

```
❌ JSON (2,034 tokens):
  [{"name":"search","description":"Search the web..."},
   {"name":"fetch","description":"Fetch a URL..."},
   {"name":"crawl","description":"Crawl a site..."}]

✅ TOON (812 tokens):
  search fetch crawl
```

Same data. Same semantics. **60% fewer tokens.**

## Why mcptoon?

| | mcptoon | Other MCP clients |
|---|---|---|
| **Token output** | TOON (40-60% smaller) | JSON only |
| **Dependencies** | **Zero** (stdlib only) | 5-20 packages |
| **stdio transport** | ✅ | ✅ |
| **HTTP transport** | ✅ (SSE + session) | Some |
| **Safety guard** | Dangerous-op blocking | ❌ |
| **Usage tracking** | ✅ | ❌ |
| **Schema cache** | ✅ (5min TTL) | ❌ |
| **Custom handlers** | ✅ (bypass MCP) | ❌ |
| **Windows support** | ✅ | Often broken |

## Installation

```bash
pip install mcptoon
```

That's it. Zero dependencies, zero config. Python 3.10+.

## 30-Second Quick Start

```bash
# 1. Initialize with sample servers
mcptoon init

# 2. Add any MCP server — npx works out of the box
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# 3. See all available tools (one line, ~15 tokens)
mcptoon manifest --toon
# → fetch:fetch

# 4. Call a tool — TOON output saves tokens
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon

# 5. Need JSON for scripts? One flag.
mcptoon call fetch fetch '{"url":"https://example.com"}' --json
```

## TOON Format — How It Works

TOON (Token-Optimized Object Notation) strips JSON's structural overhead while preserving full semantic fidelity:

| Python value | JSON | TOON | Savings |
|---|---|---|---|
| `{"name":"search","count":3}` | `{"name":"search","count":3}` | `name:search|count:3` | 33% |
| `[1, 2, 3]` | `[1, 2, 3]` | `1 2 3` | 50% |
| `True` / `False` | `true` / `false` | `T` / `F` | 60% |
| `None` | `null` | `∅` | 50% |
| `"line1\nline2"` | `"line1\nline2"` | `line1↲line2` | — |

**Real-world example — 96-tool manifest:**

```
JSON:  2,034 tokens
TOON:    812 tokens  ← 60% reduction
Compact:  62 tokens  ← 97% reduction (names only)
```

## Agent Integration

Set one environment variable — mcptoon auto-selects the optimal format:

```bash
# Claude Code, CatPaw, Anthropic agents (token-sensitive)
export MCPTOON_AGENT_TYPE=claude   # → auto --toon

# OpenAI, scripts, CI pipelines
export MCPTOON_AGENT_TYPE=openai   # → auto --json

# Human terminal use
export MCPTOON_AGENT_TYPE=human    # → auto (pretty print)
```

### In Claude Code / CatPaw skill files:

```markdown
Search the web using Exa:
`mcptoon call exa search '{"query":"AI news"}' --toon`

List available tools:
`mcptoon manifest --toon`
```

Your agent gets the same information in half the tokens. **This means: longer conversations, more tool calls, less cost.**

## Server Configuration

### stdio (most MCP servers)

```bash
# Any npx-based MCP server — zero friction
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
```

### HTTP

```bash
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

### Config file: `~/.mcptoon/config.json`

```json
{
  "servers": {
    "fetch": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-fetch"]
    },
    "myapi": {
      "transport": "http",
      "url": "http://localhost:3001/mcp",
      "headers": {"Authorization": "Bearer xxx"}
    }
  }
}
```

## Safety First

mcptoon blocks dangerous operations by default:

```bash
# ❌ Blocked — "delete" matches dangerous pattern
mcptoon call db delete_table '{"name":"users"}'
# Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

# ✅ Explicit confirmation required
mcptoon call db delete_table '{"name":"users"}' --destructive
```

Dangerous patterns: `delete`, `remove`, `drop`, `destroy`, `purge`, `wipe`, `kill`, `force=true`, `confirm=true`.

## Usage Analytics

```bash
mcptoon usage
```

```
Total calls: 142
Success rate: 138/142
Tokens (est): 84,200

By server:
  fetch                   89
  github                  53

Top tools:
  fetch:fetch             45
  github:search_repos     38
```

## Advanced: Custom Handlers

Bypass MCP entirely for specific servers — call any API directly:

```python
from mcptoon.router import register

@register("my-database", "db")
def handle(tool, args):
    if tool == "query":
        return {"rows": my_db.execute(args["sql"])}
    return None  # fall through to MCP
```

## Architecture

```
src/mcptoon/
├── cli.py        # Entry point + arg parsing
├── client.py     # Universal MCP client (HTTP + stdio)
├── router.py     # Tool call routing + custom handlers
├── config.py     # Server config management (~/.mcptoon/config.json)
├── manifest.py   # Tool discovery
├── output.py     # TOON / JSON / compact rendering ← the magic
├── cache.py      # Schema cache (5min TTL)
├── usage.py      # Usage tracking
└── errors.py     # Structured error envelopes
```

**Zero third-party dependencies.** Pure Python stdlib. Install on any system with Python 3.10+.

## Comparison with Other Tools

| Feature | mcptoon | mcp-cli (proxy-based) | mcporter |
|---|---|---|---|
| Output format | TOON + JSON + compact | JSON only | JSON only |
| Dependencies | **0** | proxy server + SDK | npm ecosystem |
| stdio transport | ✅ | ❌ | ✅ |
| HTTP transport | ✅ | ✅ (proxy) | ✅ |
| Token optimization | **40-60%** | 0% | 0% |
| Safety guard | ✅ | ❌ | ❌ |
| Usage tracking | ✅ | ❌ | ❌ |
| Schema cache | ✅ | ❌ | ❌ |
| Windows support | ✅ | Often broken | ✅ |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome!

## License

Apache License 2.0 — see [LICENSE](LICENSE). Commercial use OK, modification OK, but **attribution required**.

---

<p align="center">
  <sub>Built by developers who got tired of JSON eating their context window.</sub><br>
  <sub>★ Star this repo if mcptoon saved you tokens.</sub>
</p>
