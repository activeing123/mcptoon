<div align="center">

# mcptoon

**MCP tool discovery costs 10,000+ tokens. mcptoon costs 350.**

*One MCP client for every AI agent. Cross-platform. Zero dependencies. Battle-tested with 255+ tools.*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon)

**If this saves you tokens, please star the repo — it helps others discover it.**

[English](README.md) | [中文文档](README.zh-CN.md) | [🌐 Ecosystem](ECOSYSTEM.md) | [📦 Profiles](mcp/README.md) | [Report Bug](https://github.com/activeing123/mcptoon/issues) | [Request Feature](https://github.com/activeing123/mcptoon/issues)

**What's new in v0.2.0** — stdin support, doctor command, tool poisoning guard, fuzzy match, cross-agent format export

**What's new in v0.2.2** — `--slim` mode (93% token savings for tool schemas), unit tests for slim_toon()

![mcptoon demo](assets/demo.gif)

</div>

---

## The problem

Every MCP-enabled conversation burns tokens on **syntax, not data**:

- Your agent connects to 5 MCP servers. Listing their tools: **~10,000 tokens** of JSON.
- Your agent calls 20 tools. Each returns 500-3,000 tokens wrapped in `{"content":[{"type":"text","text":"..."}]}`.
- Total MCP overhead: **40,000-70,000 tokens** before any actual thinking happens.

On a 128K context window, that's **30-55% gone**. Not on work. On syntax.

## The solution

mcptoon is a CLI client that connects to any MCP server (stdio or HTTP) and outputs **TOON** (Token-Optimized Object Notation) instead of JSON.

| Operation | JSON tokens | mcptoon tokens | Savings |
|---|---|---|---|
| Tool discovery (96 tools) | ~2,000 | ~60 | **97%** |
| Tool result (structured data) | ~800 | ~350 | **56%** |
| Tool result (raw HTML/text) | ~1,000 | ~900 | **10%** |

Zero dependencies. Pure Python. 50KB. Works with **every AI agent** — Claude Code, Codex, OpenCode, Cursor, CatPaw, anything that runs shell commands.

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

98% reduction for tool discovery, 60% for full schema, zero information lost.

## Quick start

```bash
pip install mcptoon
```

Zero dependencies. 50KB. Python 3.10+. Windows, macOS, Linux.

```bash
mcptoon init                          # Sample config: ~/.mcptoon/config.json
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon manifest --toon               # -> fetch:fetch
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
mcptoon call fetch fetch '{"url":"https://example.com"}' --json   # when you need JSON
```

## How TOON works

| JSON | TOON | Why |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | Pipes replace braces + quotes + colon |
| `[1, 2, 3]` | `1 2 3` | Spaces replace brackets + commas |
| `true` / `false` | `T` / `F` | 1 char vs 4-5 |
| `null` | `∅` | 1 symbol vs 4 chars |
| `"line1\nline2"` | `line1↲line2` | ↲ replaces escape sequence |
| `{"a":{"b":[1,2]}}` | `a:b:1_2` | Recursive compaction |

## Output formats

| Flag | What you get | Token footprint |
|---|---|---|
| `--toon` | Compact notation, full semantics | 40-60% less than JSON |
| `--slim` | Ultra-compact tool manifests (name\|param:type*) | **93% less than JSON** |
| `--compact` | Tool names only, space-separated | 97% less than JSON |
| `--json` | Standard JSON (for scripts, CI) | Baseline |
| `--raw` | Raw response, no parsing | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Hard truncate at N chars | Variable |
| `--full` | Disable the default 4000-char truncation | Full size |

Set `MCPTOON_AGENT_TYPE=claude` and every call auto-selects `--toon`.

### SLIM mode (v0.2.2+)

When you need tool schemas but want maximum token savings, use `--slim`:

```bash
$ mcptoon manifest --slim
search|q:s*|n:n
fetch|url:s*
create|meta:o{title,tags}|tags:a[s]
```

Format: `tool_name|param:type*|param:type`
- `s`=string `n`=number `b`=boolean `a[type]`=array `o{keys}`=object
- `*` marks required parameters
- Descriptions and schema wrappers stripped

**93% token savings** vs JSON for full tool schemas. Perfect for LLM agents that need to know parameter types without the overhead.

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
| Dangerous-op blocking | yes | no | no | no |
| Tool poisoning guard | **yes** | no | no | no |
| Fuzzy match suggestions | **yes** | no | no | no |
| `--stdin` large payloads | **yes** | no | no | no |
| `doctor` self-diagnosis | **yes** | no | no | no |
| Usage tracking | yes (local) | no | no | no |
| Schema cache | yes (5min) | no | no | no |
| Install size | ~50KB | ~50MB+ | ~30MB | ~10MB |
| Platform support | **Windows, macOS, Linux** | Linux/macOS | macOS | varies |

## 🌐 Ecosystem

mcptoon is more than a CLI tool — it's a **growing ecosystem** for token-efficient MCP usage:

| Component | What it is | Status |
|-----------|-----------|--------|
| 📦 **[Server Support Matrix](mcp/README.md)** | 59 MCP servers: 10 ready · 49 planned · community requests | 10 → 100+ |
| 🔧 **TOON Format** | Token-optimized notation (open spec) | v1 in mcptoon → standalone spec |
| 📚 **Integration Guides** | Agent-specific setup docs | 10 agents planned |
| 🏷️ **Powered by Badge** | For MCP servers using mcptoon | Coming soon |
| 🔌 **Multi-language SDK** | TOON for JS/Go/Rust | Post-v1.0 |

**Contribute:** Add a profile · Write an integration guide · Implement TOON in your language

→ **[Full ecosystem plan](ECOSYSTEM.md)**

---

## Works with every agent

mcptoon is a CLI tool. If your agent can run shell commands, it can use mcptoon.

| Agent | How to use |
|---|---|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files |
| **Codex (OpenAI)** | Add `mcptoon` to AGENTS.md |
| **OpenCode** | Use `mcptoon` in custom commands |
| **Cursor** | Add `mcptoon` to .cursorrules |
| **CatPaw** | Write `mcptoon` commands in skill files |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

Configure MCP servers **once** in `~/.mcptoon/config.json`. Every agent shares the same servers, the same tools, the same token savings.

### Claude Code

```bash
export MCPTOON_AGENT_TYPE=claude   # auto-select --toon
```

```markdown
# In ~/.claude/skills/mcp-tools/SKILL.md
Search the web: mcptoon call exa search '{"query":"AI news"}'
List available tools: mcptoon manifest --toon
Fetch a URL: mcptoon call fetch fetch '{"url":"https://example.com"}'
```

### Codex (OpenAI)

```markdown
# In AGENTS.md or system prompt
Use mcptoon to call MCP tools. It saves 60% tokens vs JSON.
- List tools: mcptoon manifest --toon
- Call a tool: mcptoon call <server> <tool> '{"args":"here"}' --toon
```

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

## Config

```bash
# stdio (any npx MCP server)
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

Config lives at `~/.mcptoon/config.json`. Project-level override at `./.mcptoon.json`.

## Safety

mcptoon blocks operations that match dangerous patterns (`delete`, `drop`, `purge`, `wipe`, `kill`, etc.) unless you pass `--destructive`.

```bash
$ mcptoon call db delete_table '{"name":"users"}'
Error [CONFIRMATION_REQUIRED]: Dangerous operation needs confirmation

$ mcptoon call db delete_table '{"name":"users"}' --destructive
# runs
```

## Usage tracking

```bash
$ mcptoon usage
Total calls: 142
Success rate: 138/142
Tokens (est): 84,200

By server:
  fetch       89
  github      53
```

Stored locally at `~/.cache/mcptoon/usage.json`. Never transmitted.

## Architecture

```
src/mcptoon/
├── cli.py        # CLI entry + arg parsing
├── client.py     # MCPClient — stdio + HTTP transport
├── router.py     # Tool routing, custom handlers, safety checks
├── config.py     # Server config
├── manifest.py   # Tool discovery with cache
├── output.py     # TOON / JSON / compact rendering
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes
```

~1,700 lines total. Zero third-party imports.

## Privacy

- **No telemetry.** No analytics, no crash reports, no phone-home.
- **No credential storage.** API keys pass through from your config or env vars.
- **No dependencies.** Pure Python stdlib. No supply chain to audit.

Found a vulnerability? Email `security@activeing123.github.io`. See [SECURITY.md](SECURITY.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 160 tests, 0.22s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

**Found this useful? Star the repo to help others find it.**

[Report Bug](https://github.com/activeing123/mcptoon/issues) | [Request Feature](https://github.com/activeing123/mcptoon/issues)

</div>
