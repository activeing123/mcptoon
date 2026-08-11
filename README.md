<div align="center">

# mcptoon

**MCP tool discovery costs 10,000+ tokens. mcptoon's costs 350.**

*One MCP client for every AI agent. Cross-platform. Zero dependencies. Battle-tested with 255+ tools.*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon)

[English](README.md) · [中文文档](README.zh-CN.md)

**[What's new in v0.2.0](#whats-new-in-v020)** — stdin support, doctor command, tool poisoning guard, fuzzy match, cross-agent format export

</div>

---

Here's what happens in a typical MCP-enabled conversation:

- Your agent connects to 5 MCP servers. Listing their tools: **~10,000 tokens** of JSON — `{"name":"...","description":"...","inputSchema":{"type":"object","properties":{...}}}` repeated for every tool.
- Your agent calls 20 tools. Each returns 500-3,000 tokens wrapped in `{"content":[{"type":"text","text":"..."}]}`.
- Total MCP overhead: **40,000-70,000 tokens** — brackets, quotes, commas, schema declarations — before any actual thinking happens.

On a 128K context window, that's 30-55% gone. Not on work. On syntax.

mcptoon fixes this. It's a CLI client that connects to any MCP server (stdio or HTTP transport) and outputs **TOON** (Token-Optimized Object Notation) instead of JSON.

| Operation | JSON tokens | mcptoon tokens | Savings |
|---|---|---|---|
| Tool discovery (96 tools) | ~2,000 | ~60 | **97%** |
| Tool result (structured data) | ~800 | ~350 | **56%** |
| Tool result (raw HTML/text) | ~1,000 | ~900 | **10%** |

TOON strips JSON syntax — brackets, quotes, commas, repeated type declarations. What remains is **real data**: repo names, star counts, search results, web page content. That's the part you actually need.

Zero dependencies. Pure Python. 50KB. And because it's a CLI tool, it works with **every AI agent** — Claude Code, Codex, OpenCode, Cursor, CatPaw, anything that runs shell commands. One config, one command, every agent gets MCP access.

## Show me

**JSON (287 tokens)** — what every other MCP client returns:

```json
[
  {"name": "search_web", "description": "Search the web for information",
   "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}, "num_results": {"type": "number", "default": 5}}, "required": ["query"]}},
  {"name": "fetch_url", "description": "Fetch content from a URL",
   "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
]
```

**TOON (5 tokens)** — what mcptoon returns:

```
search_web fetch_url
```

**TOON with full schema (115 tokens)** — when you need the details:

```
name:search_web|description:Search_the_web|inputSchema:type:object|properties:query:type:string|description:Search_query|num_results:type:number|default:5|required:query||
name:fetch_url|description:Fetch_content_from_a_URL|inputSchema:type:object|properties:url:type:string|required:url
```

98% reduction for tool discovery, 60% for full schema, zero information lost.

## Install

```bash
pip install mcptoon
```

Zero dependencies. 50KB. Python 3.10+. Windows, macOS, Linux. Done.

## 30 seconds to your first saved tokens

```bash
mcptoon init
# Sample config created: ~/.mcptoon/config.json

mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

mcptoon manifest --toon
# → fetch:fetch

mcptoon call fetch fetch '{"url":"https://example.com"}' --toon

mcptoon call fetch fetch '{"url":"https://example.com"}' --json   # when you need JSON
```

That's it. Every `--toon` call saves tokens: 97% on tool discovery, 40-60% on structured results, 10-20% on raw content.

## How TOON works

TOON strips the structural scaffolding JSON needs for machine parsing — brackets, quotes, commas, repeated type declarations — none of which adds semantic value for an LLM.

| JSON | TOON | Why |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | Pipes replace braces + quotes + colons |
| `[1, 2, 3]` | `1 2 3` | Spaces replace brackets + commas |
| `true` / `false` | `T` / `F` | 1 char vs 4-5 |
| `null` | `∅` | 1 symbol vs 4 chars |
| `"line1\nline2"` | `line1↲line2` | ↲ replaces escape sequence |
| `{"a":{"b":[1,2]}}` | `a:b:1_2` | Recursive compaction |

The AI gets the same data. It can reconstruct the full structure from TOON output. We just stopped charging you tokens for `{"type":"object","properties":` over and over.

## Output formats

| Flag | What you get | Token footprint |
|---|---|---|
| `--toon` | Compact notation, full semantics | 40-60% less than JSON |
| `--compact` | Tool names only, space-separated | 97% less than JSON |
| `--json` | Standard JSON (for scripts, CI) | Baseline |
| `--raw` | Raw response, no parsing | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Hard truncate at N chars | Variable |
| `--full` | Disable the default 4000-char truncation | Full size |

Set `MCPTOON_AGENT_TYPE=claude` and every call auto-selects `--toon`. No need to add the flag manually.

## Examples

### GitHub repo search — 287 → 115 tokens (60% saved)

```
$ mcptoon call github search_repos '{"query":"mcp"}' --toon
total_count:234|items:name:mcp-server|full_name:anthropic/mcp-server|stargazers_count:1234|description:Official_MCP_server name:mcp-client|full_name:anthropic/mcp-client|stargazers_count:567|description:MCP_client_library
```

```
$ mcptoon call github search_repos '{"query":"mcp"}' --compact
mcp-server mcp-client
```

### 96-tool manifest discovery — 2,034 → 62 tokens (97% saved)

```
$ mcptoon manifest --toon
fetch:fetch filesystem:read_file filesystem:write_file github:search_repos github:create_issue ...
```

Your agent now knows all 96 available tools and still has 97% of its context left to actually use them.

### Web fetch — strips the MCP wrapper

```
$ mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
<!DOCTYPE html><html><head><title>Example</title>...</html>
```

No `{"content":[{"type":"text","text":"..."}]}` wrapper. Just the content.

## What's new in v0.2.0

Battle-tested features from production use with 255+ MCP tools across 23+ servers:

### `--stdin` for large payloads

OS command-line limits (32,767 chars on Windows, ~128KB on Linux) break MCP calls with large content. Now you can pipe arguments via stdin:

```bash
# This fails on Windows if content > 32KB:
mcptoon call fetch put '{"content":"...huge..."}'

# This always works:
echo '{"content":"...huge..."}' | mcptoon call fetch put --stdin --toon
mcptoon call fetch put --stdin --toon < payload.json
```

### `doctor` — one-command self-diagnosis

```bash
$ mcptoon doctor
  ✓ Python 3.12.0 (>=3.10 required)
  ✓ Config: ~/.mcptoon/config.json (5 servers)
  ✓ Cache dir: ~/.cache/mcptoon
  ✓ fetch              [stdio]  1 tools
  ✓ github             [stdio]  12 tools
  ✗ myapi              [http]   ERROR: Connection refused
  - MCPTOON_AGENT_TYPE not set (defaulting to auto)

  5 checks, 1 issue(s)
```

### `discover` — server health check

```bash
$ mcptoon discover
Discovered 3 server(s):

  ✓ fetch                [stdio]   1 tools  ok
  ✓ github               [stdio]  12 tools  ok
  ✗ myapi                [http]    0 tools  error
    └─ Connection refused
```

### Tool poisoning guard

MCP servers return arbitrary content. A compromised server could inject instructions into your agent's context. mcptoon now detects and blocks common prompt injection patterns:

```bash
$ mcptoon call malicious get_data '{}'
Error [TOOL_POISONING]: Tool result may contain prompt injection:
  potential prompt injection detected: contains 'ignore previous instructions'
```

Patterns detected: instruction overrides, hidden `<!-- assistant:` directives, `[INST]`/`<<SYS>>` tags, data exfiltration attempts.

### Fuzzy match "Did you mean?"

Tool names across MCP servers follow no naming convention. When you mistype:

```bash
$ mcptoon call exa sarch '{"query":"AI"}'
Error [METHOD_NOT_FOUND]: Unknown tool: sarch
Did you mean: search, search_all
```

### Cross-agent format export

Export your tool manifest for non-CLI agents:

```bash
# OpenAI function calling
mcptoon manifest --format openai > functions.json

# OpenAPI 3.0 spec
mcptoon manifest --format openapi > openapi.json

# MCP tools/list format
mcptoon manifest --format mcp > mcp-tools.json
```

## vs. other MCP clients

| | mcptoon | mcp-cli | mcporter | raw MCP SDK |
|---|---|---|---|---|
| Token savings | **97% manifest, 40-60% results** | 0% | 0% | 0% |
| Works with all agents | **yes** (Claude Code, Codex, OpenCode, Cursor, any) | Claude only | Claude only | varies |
| One config for all agents | **yes** | no | no | no |
| Output formats | TOON + JSON + compact + **openai + openapi + mcp** | JSON | JSON | JSON |
| Dependencies | **0** | 5-20 | npm | 3-8 |
| stdio transport (MCP servers) | yes | no | yes | yes |
| HTTP transport (MCP servers) | yes | yes (proxy) | yes | yes |
| Dangerous-op blocking | yes | no | no | no |
| Tool poisoning guard | **yes** | no | no | no |
| Fuzzy match suggestions | **yes** | no | no | no |
| `--stdin` large payloads | **yes** | no | no | no |
| `doctor` self-diagnosis | **yes** | no | no | no |
| Usage tracking | yes (local) | no | no | no |
| Schema cache | yes (5min) | no | no | no |
| Custom handlers | yes | no | no | no |
| Install size | ~50KB | ~50MB+ | ~30MB | ~10MB |
| Platform support | **Windows, macOS, Linux** | Linux/macOS | macOS | varies |

Same MCP servers. Same MCP protocol. Same results. 97% less tokens on discovery, 40-60% on results. Works on Windows, macOS, and Linux.

## Works with every agent

mcptoon is a CLI tool. If your agent can run shell commands, it can use mcptoon. No SDK integration, no plugin, no per-agent config.

You configure your MCP servers **once** in `~/.mcptoon/config.json`. Every agent shares the same servers, the same tools, the same token savings.

| Agent | How to use |
|---|---|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files or custom instructions |
| **Codex (OpenAI)** | Add `mcptoon` to your AGENTS.md or prompt instructions |
| **OpenCode** | Use `mcptoon` in your custom commands or system prompt |
| **Cursor** | Add `mcptoon` to your .cursorrules or custom prompt |
| **CatPaw** | Write `mcptoon` commands in skill files |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

### Claude Code

```bash
export MCPTOON_AGENT_TYPE=claude   # auto-select --toon
```

```markdown
# In ~/.claude/skills/mcp-tools/SKILL.md

Search the web:
`mcptoon call exa search '{"query":"AI news"}'`

List available tools:
`mcptoon manifest --toon`

Fetch a URL:
`mcptoon call fetch fetch '{"url":"https://example.com"}'`
```

### Codex (OpenAI)

```markdown
# In AGENTS.md or system prompt

Use mcptoon to call MCP tools. It saves 60% tokens vs JSON.

- List tools: `mcptoon manifest --toon`
- Call a tool: `mcptoon call <server> <tool> '{"args":"here"}' --toon`
- Inspect a tool: `mcptoon inspect <server> <tool>`
```

### OpenCode

```bash
# In your OpenCode config or system prompt
export MCPTOON_AGENT_TYPE=claude
```

```
## Available MCP tools
Run `mcptoon manifest --toon` to see all tools.
Run `mcptoon call <server> <tool> '<json_args>' --toon` to call one.
```

### Why one unified layer?

Without mcptoon, you configure MCP servers separately for each agent — Claude Code's `claude_desktop_config.json`, Cursor's MCP settings, OpenCode's config, etc. Same servers, different formats, different setups.

With mcptoon, you configure once. `~/.mcptoon/config.json` is your single source of truth. Every agent calls `mcptoon` the same way. Add a server, every agent sees it instantly. Remove a server, it's gone everywhere.

Plus: every call saves 97% tokens on manifest discovery and 40-60% on tool results, no matter which agent you're using.

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon(tools))         # compact TOON
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon(result))
```

## Custom handlers — bypass MCP entirely

```python
from mcptoon.router import register

@register("my-database", "db")
def handle_db(tool, args):
    if tool == "query":
        return {"rows": my_db.execute(args["sql"])}
    return None  # falls through to MCP
```

`mcptoon call db query '{"sql":"SELECT * FROM users"}'` goes straight to your handler. No MCP server needed.

## Config

```bash
# stdio (any npx MCP server)
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

Config lives at `~/.mcptoon/config.json`. Project-level override at `./.mcptoon.json`. Env var `MCPTOON_SERVERS` (JSON string) takes highest priority.

```json
{
  "servers": {
    "fetch": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-fetch"]
    },
    "github": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
    }
  }
}
```

## Safety

mcptoon blocks operations that match dangerous patterns (`delete`, `drop`, `purge`, `wipe`, `kill`, `force=true`, `confirm=true`, etc.) unless you pass `--destructive`.

```bash
$ mcptoon call db delete_table '{"name":"users"}'
Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

$ mcptoon call db delete_table '{"name":"users"}' --destructive
# runs
```

No surprises. No accidental data loss from an AI agent that got too creative.

## Usage tracking

```bash
$ mcptoon usage
Total calls: 142
Success rate: 138/142
Tokens (est): 84,200

By server:
  fetch       89
  github      53

Top tools:
  fetch:fetch             45
  github:search_repos     38
```

Stored locally at `~/.cache/mcptoon/usage.json`. Never transmitted.

## Architecture

```
src/mcptoon/
├── cli.py        # CLI entry + arg parsing
├── client.py     # MCPClient — stdio + HTTP transport, MCPClientPool
├── router.py     # Tool call routing, custom handlers, safety checks
├── config.py     # Server config (~/.mcptoon/config.json + overrides)
├── manifest.py   # Tool discovery with cache
├── output.py     # TOON / JSON / compact rendering
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes
```

~1,700 lines total. Zero third-party imports. The only network calls are to MCP servers you configure.

## Privacy

- **No telemetry.** No analytics, no crash reports, no phone-home. Nothing leaves your machine.
- **No credential storage.** API keys pass through from your config or env vars. Never logged, never cached.
- **No dependencies.** Pure Python stdlib. No supply chain to audit, no packages to hijack, no updates to chase.

Local files: `~/.mcptoon/config.json` (your config), `~/.cache/mcptoon/schema_cache.json` (5-min cache), `~/.cache/mcptoon/usage.json` (stats). Delete any of them, mcptoon recreates as needed.

Found a vulnerability? Email `security@activeing123.github.io` — don't open a public issue. 48h response, 7-day fix window. See [SECURITY.md](SECURITY.md).

## License

Apache 2.0. Commercial use, modification, distribution — all fine. Keep the LICENSE and NOTICE files, state your changes. The TOON format is open — implement it in your own tools, just attribute mcptoon. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 98 tests, 0.09s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*
