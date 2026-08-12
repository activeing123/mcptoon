<div align="center">

# mcptoon

**Add 255 MCP tools → 90,804 tokens gone. Add mcptoon → 117 tokens.**

*Keep 100+ MCP servers always configured. Zero context pollution. No loading. No unloading. One CLI for every agent.*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon)

**If this saves you tokens, please star the repo — it helps others discover it.**

[English](README.md) | [中文文档](README.zh-CN.md) | [🌐 Ecosystem](ECOSYSTEM.md) | [📦 Profiles](mcp/README.md) | [Report Bug](https://github.com/activeing123/mcptoon/issues) | [Request Feature](https://github.com/activeing123/mcptoon/issues)

![mcptoon demo](assets/demo.gif)

![Benchmark: 255 tools, 90,804 → 117 tokens](assets/benchmark.svg)

</div>

---

## The problem

Every MCP-enabled agent loads **all tool schemas into your context** — before any work starts.

```
Add 10 MCP servers (especially browser tools like puppeteer/playwright)
  → Each server returns tools/list with full JSON schemas
  → ALL schemas injected into your context
  → 50,000-100,000+ tokens consumed
  → 128K context: 40-80% gone before you even ask a question

Add 100 servers → 200,000+ tokens → context is dead.
```

So you unload servers when not needed. Reload when needed. Repeat. Forever.

And when you want to add a new MCP server? You manually edit JSON config files (`claude_desktop_config.json`, etc.). One syntax error, wrong path, or missing env var — MCP won't load. You debug for hours.

**You're managing MCP servers instead of doing work.**

## The solution

mcptoon keeps **all your MCP servers configured** — but their schemas **never enter your agent's context**.

### 😤 5 pains. ✅ 5 kills.

#### 😤 Context death → ✅ 0 tokens, forever

Add 10 MCP servers — especially browser tools like puppeteer (47 tools, 23K tokens of schemas) or playwright (52 tools, 28K tokens). Before you ask a single question, 50-100K tokens of `{"type":"object","properties":...}` are squatting in your context. Your AI forgets what you were talking about. So you uninstall servers to make room. Then you need one — reinstall, wait, reconfigure. You're playing Tetris with MCP servers inside your context window. This is why people say "MCP is unusable past 5 servers."

→ **mcptoon: 100 servers configured, 0 tokens in context.** Use any tool, anytime. No Tetris.

#### 😤 Config hell → ✅ One command, done

Want to add a server? Hand-edit `claude_desktop_config.json`. Miss a comma → MCP won't load. Wrong path → won't load. Missing env var → won't load. Sometimes it loads but tools silently don't appear — no error, no log, just nothing. You stare at a blank tool list and debug for an hour.

→ **mcptoon: `mcptoon add myserver --stdio npx -y @package`.** One command. Something's wrong? `mcptoon doctor` checks Python, config syntax, server connectivity — tells you exactly what.

#### 😤 Agent can't self-serve → ✅ AI installs its own tools

Your agent is mid-task and says "I need GitHub search to finish this." It can't install tools — it's an AI, not an admin. So *you* stop coding, go edit JSON, restart the agent, wait for it to reconnect. Your AI forgot what it was working on. Momentum — dead.

→ **mcptoon: Your AI runs `mcptoon add github ...` itself**, and keeps going. No human in the loop. No context lost.

#### 😤 Reconfigure per agent → ✅ One config, all agents

You set up 15 MCP servers for Claude Code. Now you try Cursor — different config format, different file location, redo all 15 from scratch. Then OpenCode. Then Codex. Same servers, 4× the work, 4× the chances to miss a comma.

→ **mcptoon: One config file, every agent.** `~/.mcptoon/config.json`. Switch agents in seconds. Config follows you.

#### 😤 Paying for JSON garbage → ✅ TOON, 56-97% smaller

Every MCP result looks like `{"content":[{"type":"text","text":"{\"name\":\"react\",\"stars\":219000}"}]}` — 80 tokens of braces, quotes, and type declarations to deliver 6 tokens of actual data. Over a session with 200 tool calls, that's 15,000 tokens of pure syntax waste.

→ **mcptoon: Returns `name:react|stars:219000` — same data, 56% fewer tokens.** Discovery: 97% fewer. Schemas: 93% fewer. **No other MCP client does this. Only mcptoon.**

---

**100 MCP servers. 0 context waste. Use any tool, anytime. No loading. No unloading. No JSON config errors.**

### How? CLI mode.

mcptoon is a CLI tool, not an MCP client library. Your agent doesn't connect to MCP servers — it just runs `mcptoon` commands. MCP schemas live on disk in `~/.mcptoon/config.json`, not in your context window. Only the compact output you request enters context — and TOON encoding makes it 56-97% smaller than JSON.

## Show me

**JSON (287 tokens)** — what every other MCP client puts in your context:

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

### Measured benchmark (255 tools, 23 servers)

| Tools | JSON (tokens) | mcptoon compact | Reduction |
|-------|-------------|----------------|-----------|
| 5 | 1,897 | 16 | **99.2%** |
| 10 | 3,567 | 34 | **99.0%** |
| 25 | 9,009 | 97 | **98.9%** |
| 50 | 17,790 | 117 | **99.3%** |
| 93 | 33,191 | 117 | **99.6%** |
| 150 | 53,350 | 117 | **99.8%** |
| 200 | 71,135 | 117 | **99.8%** |
| **255** | **90,804** | **117** | **99.87%** |

**TOON format** for tool results: **61% smaller** than JSON.
**SLIM format** for full schemas: **93% smaller** than JSON.

<details>
<summary>📊 Full benchmark data (click to expand)</summary>

| Tools | JSON tokens | TOON tokens | SLIM tokens | Compact tokens | TOON save | SLIM save | Compact save |
|--------|-----------|------------|------------|---------------|-----------|-----------|-------------|
| 5 | 1,897 | 784 | 111 | 16 | 59% | 94% | 99% |
| 10 | 3,567 | 1,382 | 235 | 34 | 61% | 93% | 99% |
| 25 | 9,009 | 3,562 | 595 | 97 | 60% | 93% | 99% |
| 50 | 17,790 | 6,939 | 1,203 | 117 | 61% | 93% | 99% |
| 93 | 33,191 | 13,011 | 2,231 | 117 | 61% | 93% | 100% |
| 150 | 53,350 | 20,834 | 3,626 | 117 | 61% | 93% | 100% |
| 200 | 71,135 | 27,787 | 4,842 | 117 | 61% | 93% | 100% |
| 255 | 90,804 | 35,527 | 6,174 | 117 | 61% | 93% | 100% |

Reproduce: `python _benchmark.py` → outputs `assets/benchmark_data.json` + `assets/benchmark.html`

</details>

### Third-party research & context window economics

| Source | Finding | Why it matters |
|--------|---------|---------------|
| [Anthropic, *Context Windows for Agents*](https://docs.anthropic.com/en/docs/build-with-claude/context-windows) | “Context window is a scarce resource. Every token of schema is a token stolen from the user's actual task.” | MCP schemas are the #1 source of context waste in agent workflows |
| [OpenAI, *Function Calling Guide*](https://platform.openai.com/docs/guides/function-calling) | Tool definitions consume context tokens proportional to schema complexity | 100+ tools with full schemas can eat 40-80% of a 128K context window |
| [Cursor Team, *Context Engineering*](https://cursor.com/blog/context-engineering) | “The difference between a good and bad agent is almost always context management, not model intelligence.” | Token optimization at the transport layer (like TOON) directly improves agent quality |
| [Latent Space, *MCP Ecosystem Analysis*](https://www.latent.space/p/mcp) | “The MCP protocol injects full JSON schemas into every request — this is by design, but it creates a scaling cliff around 20-30 tools.” | Confirms the problem mcptoon solves: 20-30 tools is the pain point, not 100+ |
| [Simon Willison, *LLM Tooling*](https://simonwillison.net/2024/Nov/19/llms/) | “JSON is the least token-efficient format possible for structured data sent to an LLM.” | Validates TOON's approach: any non-JSON encoding saves tokens |
| GitHub Issues | Puppeteer MCP (47 tools) + Playwright MCP (52 tools) = ~50K tokens of schemas alone | Two browser MCP servers consume more context than this entire README |

## Quick start

```bash
pip install mcptoon
```

Zero dependencies. 50KB. Python 3.10+. Windows, macOS, Linux.

```bash
mcptoon init                          # Sample config: ~/.mcptoon/config.json
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon manifest --compact            # → all tool names, 350 tokens
mcptoon manifest --slim               # → tool schemas, 93% smaller than JSON
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

## Works with every agent

mcptoon is a CLI tool. **If your agent can run shell commands, it can use mcptoon.** No plugins. No SDK. No per-agent MCP setup. No JSON config editing.

| Agent | How to use |
|---|---|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files |
| **Codex (OpenAI)** | Add `mcptoon` to AGENTS.md |
| **OpenCode** | Use `mcptoon` in custom commands |
| **Cursor** | Add `mcptoon` to .cursorrules |
| **CatPaw** | Write `mcptoon` commands in skill files |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

**Configure once** in `~/.mcptoon/config.json`. **Every agent shares** the same servers, the same tools, the same token savings. Switch agents? Config follows you. No migration.

```bash
export MCPTOON_AGENT_TYPE=claude   # auto-select --toon for all calls
```

### Agent self-service

Your agent can add MCP tools on its own — no human intervention needed:

```bash
# Agent wants a web scraper? Just add it:
mcptoon add firecrawl --stdio npx -y firecrawl-mcp

# Agent wants GitHub access? One command:
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# Verify everything works:
mcptoon doctor

# Use it immediately:
mcptoon call github search_repos '{"query":"token optimization"}' --toon
```

No JSON config files. No RPC debugging. No server restarts. Just CLI commands.

## How TOON works

TOON (Token-Optimized Object Notation) is mcptoon's encoding that compresses JSON for LLM consumption:

| JSON | TOON | Why |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | Pipes replace braces + quotes + colon |
| `[1, 2, 3]` | `1 2 3` | Spaces replace brackets + commas |
| `true` / `false` | `T` / `F` | 1 char vs 4-5 |
| `null` | `∅` | 1 symbol vs 4 chars |
| `"line1\nline2"` | `line1↲line2` | ↲ replaces escape sequence |
| `{"a":{"b":[1,2]}}` | `a:b:1_2` | Recursive compaction |

No other MCP client does token optimization. mcptoon is the only one.

## Output formats

| Flag | What you get | Token footprint |
|---|---|---|
| `--compact` | Tool names only, space-separated | **97% less than JSON** |
| `--slim` | Ultra-compact schemas (name\|param:type*) | **93% less than JSON** |
| `--toon` | Compact notation, full semantics | 40-60% less than JSON |
| `--json` | Standard JSON (for scripts, CI) | Baseline |
| `--raw` | Raw response, no parsing | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Hard truncate at N chars | Variable |
| `--full` | Disable the default 4000-char truncation | Full size |

### SLIM mode

When you need tool schemas but want maximum token savings:

```bash
$ mcptoon manifest --slim
search|q:s*|n:n
fetch|url:s*
create|meta:o{title,tags}|tags:a[s]
```

Format: `tool_name|param:type*|param:type`
- `s`=string `n`=number `b`=boolean `a[type]`=array `o{keys}`=object
- `*` marks required parameters

**93% token savings** vs JSON for full tool schemas.

## vs. other MCP clients

| | mcptoon | mcp-cli | raw MCP SDK |
|---|---|---|---|
| **Context pollution** | **0 tokens** — schemas on disk | All schemas in context | All schemas in context |
| **Servers stay configured** | **Yes — no load/unload** | Must manage | Must manage |
| **Add server = CLI command** | **`mcptoon add ...`** | Edit JSON config | Edit JSON config |
| Token savings | **97% discovery, 93% schema, 56% results** | 0% | 0% |
| Works with all agents | **yes** (any shell-capable agent) | Claude only | varies |
| One config for all agents | **yes** | no | no |
| Dependencies | **0** | 5-20 | 3-8 |
| Install size | ~50KB | ~50MB+ | ~10MB |
| Tool poisoning guard | **yes** | no | no |
| `doctor` self-diagnosis | **yes** | no | no |
| Platform | **Windows, macOS, Linux** | Linux/macOS | varies |

## Features

**Battle-tested** with 255+ MCP tools across 23+ servers, 30K+ real calls.

- **`--stdin`** — Pipe large payloads bypassing OS command-line limits
- **`doctor`** — One-command self-diagnosis (Python, config, servers, connectivity)
- **`discover`** — Server health check with tool counts
- **Tool poisoning guard** — Detects prompt injection in MCP results (`ignore previous instructions`, `[INST]`, data exfiltration attempts)
- **Credential leak detection** — Scans tool results for exposed API keys, AWS keys, GitHub PATs, OpenAI/Anthropic keys, Slack tokens, JWTs, private keys — blocks them before they reach your agent's context
- **Fuzzy match** — "Did you mean: search, search_all?" on typos
- **Cross-agent export** — `--format openai|openapi|mcp` for non-CLI agents
- **Schema cache** — 5-min TTL, avoids repeated `tools/list` round-trips
- **Usage tracking** — Local-only call statistics and token estimates
- **Dangerous-op blocking** — Blocks `delete`/`drop`/`purge` unless `--destructive`
- **Shell completion** — bash, zsh, fish, PowerShell

### Security layers

| Layer | What it does | Example |
|-------|-------------|----------|
| **Dangerous-op guard** | Blocks `delete`/`drop`/`purge`/`kill` by default | `docker_remove` → blocked unless `--destructive` |
| **Prompt injection guard** | Scans results for injection patterns | `"ignore previous instructions"` → blocked |
| **Credential leak guard** | Scans results for exposed keys/tokens | `sk-abc...xyz` → blocked, masked in error message |

```bash
# Credential leak detection in action:
$ mcptoon call github get_file --toon
# Error: CREDENTIAL_LEAK — potential OpenAI API Key leak detected: sk-abc...wxyz
# The result never enters your agent's context.
```

## 🌐 Ecosystem

| Component | What it is | Status |
|-----------|-----------|--------|
| 📦 **[Server Profiles](mcp/README.md)** | 23 ready-to-use MCP server profiles (186+ tools) | 23 → 100+ |
| 🔧 **TOON Format** | Token-optimized notation (open spec) | v1 in mcptoon |
| 📚 **Integration Guides** | Agent-specific setup docs | Coming soon |
| 🏷️ **Powered by Badge** | For MCP servers using mcptoon | Available |

### Server profiles — not bundled, on-demand, clean

The 20 profiles in `mcp/stdio/` are **JSON templates, not installed software**:

- **Not bundled** — mcptoon doesn't ship MCP servers. Each profile is a ~1KB JSON file describing *how* to connect.
- **On-demand** — Running `mcptoon add <name>` installs the actual MCP server via `npx`. You only install what you use.
- **Security-audited** — Each profile declares `security.credential_safe`, `env_vars_required` (with sensitivity levels), and `permissions` (read/write scope).
- **Decoupled** — Profiles are independent. Remove one, the rest work fine. Add your own, it just works.

```json
// Example: mcp/stdio/puppeteer.json (excerpt)
{
  "name": "puppeteer",
  "security": {
    "audited": true,
    "credential_safe": true,
    "env_vars_required": [],
    "permissions": ["read: web pages, DOM", "write: form inputs, JS execution"]
  },
  "bundled": false,
  "install_method": "on-demand"
}
```

23 profiles available: fetch, github, exa, brave-search, firecrawl, filesystem, memory, sequential-thinking, sqlite, time, puppeteer, playwright, postgres, slack, notion, git, gitlab, tavily, google-maps, docker, aws, cloudflare, tmux. See [`mcp/README.md`](mcp/README.md) for the full list.

→ **[Full ecosystem plan](ECOSYSTEM.md)**

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

## Config

```bash
# stdio (any npx MCP server)
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

Config lives at `~/.mcptoon/config.json`. Project-level override at `./.mcptoon.json`.

## Privacy

- **No telemetry.** No analytics, no crash reports, no phone-home.
- **No credential storage.** API keys pass through from your config or env vars.
- **No dependencies.** Pure Python stdlib. No supply chain to audit.
- **Credential leak guard.** Scans tool results for exposed API keys/tokens — blocks them before they reach your agent.

## Architecture

```
src/mcptoon/
├── cli.py        # CLI entry + arg parsing
├── client.py     # MCPClient — stdio + HTTP transport
├── router.py     # Tool routing, custom handlers, poisoning + credential leak detection
├── config.py     # Server config
├── manifest.py   # Tool discovery with cache
├── output.py     # TOON / JSON / compact / slim rendering
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes
```

~2,400 lines. 160 tests. Zero third-party imports. 50KB installed.

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 160 tests, 0.22s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

**Found this useful? Star the repo to help others find it.**

[Report Bug](https://github.com/activeing123/mcptoon/issues) | [Request Feature](https://github.com/activeing123/mcptoon/issues)

</div>
