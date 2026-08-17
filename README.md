<div align="center">

# mcptoon

**Add 255 MCP tools → 90,804 tokens gone. Add mcptoon → 117 tokens.**

*Keep 100+ MCP servers always configured. Zero context pollution. No loading. No unloading. One CLI for every agent.*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white)](https://pypi.org/project/mcptoon/)

**If this saves you tokens, please star the repo — it helps others discover it.**

[English](README.md) | [中文文档](README.zh-CN.md) | [📦 Server Profiles](mcp/README.md) | [🌐 Ecosystem](ECOSYSTEM.md) | [Report Bug](https://github.com/activeing123/mcptoon/issues) | [Request Feature](https://github.com/activeing123/mcptoon/issues)

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

#### 😤 Paying for JSON garbage → ✅ TOON, 30-97% smaller

Every MCP result looks like `{"content":[{"type":"text","text":"{\"name\":\"react\",\"stars\":219000}"}]}` — 80 tokens of braces, quotes, and type declarations to deliver 6 tokens of actual data. Over a session with 200 tool calls, that's 15,000 tokens of pure syntax waste.

→ **mcptoon: Returns `name: react\nstars: 219000` — same data, 30-60% fewer tokens on results (standard TOON), 97% fewer on discovery, 93% fewer on schemas.** [tiktoken-verified](#how-toon-works).

---

**100 MCP servers. 0 context waste. Use any tool, anytime. No loading. No unloading. No JSON config errors.**

### How? CLI mode.

mcptoon is a CLI tool, not an MCP client library. Your agent doesn't connect to MCP servers — it just runs `mcptoon` commands. MCP schemas live on disk in `~/.mcptoon/config.json`, not in your context window. Only the compact output you request enters context — and TOON encoding makes it 30-97% smaller than JSON.

### Industry validation: CLI > MCP

Independent research confirms mcptoon's CLI approach is superior to MCP protocol injection:

| Source | Finding |
|--------|---------|
| [CLI vs MCP benchmark (75 tasks)](https://www.cn486.com/news/4135995/) | CLI agents outperform MCP agents on all metrics: **10-32x lower token cost**, ~100% reliability vs MCP's 72% |
| Perplexity | Removed MCP support from their agent architecture entirely — token overhead too high |
| Anthropic internal research | Shell scripts consume **98.7% fewer tokens** than equivalent MCP tool calls |
| Latent Space | "MCP protocol creates a scaling cliff around 20-30 tools" — mcptoon has no such limit |

**The industry is moving from MCP injection → CLI execution. mcptoon was CLI-first from day one.**

---

## What GitHub users see vs what you have locally

mcptoon has a **dual-track architecture** — the public GitHub repo is clean and self-contained, while your local installation can have private extensions:

```
GitHub repo (public)                     Your machine (local)
┌────────────────────────────┐           ┌────────────────────────────┐
│  src/mcptoon/              │           │  src/mcptoon/              │
│  ├─ cli.py                 │           │  ├─ cli.py                 │  ← same code
│  ├─ client.py              │           │  ├─ client.py              │
│  ├─ installer.py           │           │  ├─ installer.py           │
│  ├─ router.py              │           │  ├─ router.py              │
│  └─ output.py (TOON)       │           │  └─ output.py (TOON)       │
│                            │           │                            │
│  mcp/ (23 profiles)        │           │  mcp/ (23 profiles)        │  ← same profiles
│  tests/ (429 tests)        │           │  ~/.mcptoon/config.json    │  ← your servers
│  docs/, README, etc.       │           │  local/ (private layer)   │  ← your extensions
│                            │           │  ├─ handlers/ (30+)        │
│  NO private handlers       │           │  ├─ router.py (bridge)    │
│  NO local credentials      │           │  └─ cli_pro.py            │
└────────────────────────────┘           └────────────────────────────┘
```

**What goes to GitHub:** the clean, zero-dependency CLI core — 13 Python files, ~4,500 lines, 429 tests, 23 server profiles. No private handlers, no credentials, no local config.

**What stays local:** your personal `~/.mcptoon/config.json`, your installed MCP servers, and optionally a `local/` directory with private handlers for custom tools. The `.gitignore` excludes all of it.

### Can GitHub users install their own tools?

**Yes — that's the whole point.** mcptoon is a *tool manager*, not a bundle of tools. Here's how a GitHub user gets started:

```bash
# 1. Install mcptoon (the CLI core, zero deps)
pip install mcptoon

# 2. Add ANY MCP server you want — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# 3. Or auto-discover servers already on your machine:
mcptoon init --auto

# 4. Or install from npm/pip/HTTP with auto-handler generation:
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search
mcptoon install my-tool --pip mcp-my-tool
mcptoon install remote-api --url https://example.com/mcp

# 5. See your tools (117 tokens for 255 tools):
mcptoon manifest --compact

# 6. Call any tool:
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**mcptoon never bundles MCP servers.** Users install only what they need, from npm, pip, or HTTP endpoints. The 23 pre-configured profiles in `mcp/stdio/*.json` are just ~1KB JSON templates describing *how to connect* — not the servers themselves. Servers are launched on-demand via `npx` only when a tool is actually called.

| What mcptoon ships | What it doesn't ship |
|---|---|
| CLI core (13 files, ~200KB) | MCP server binaries |
| 23 server profile templates (~1KB each) | API keys or credentials |
| 429 tests + benchmark suite | User's private config |
| Integration guides + ecosystem docs | Third-party dependencies |

---

## Quick start

```bash
pip install mcptoon
```

Zero dependencies. Python 3.10+. ~200KB source. Windows, macOS, Linux.

```bash
# ─── 30-second onboarding ───
mcptoon quickstart                      # discover + configure + show tools
mcptoon init --auto                     # auto-discover MCP servers on your machine
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# ─── See your tools ───
mcptoon manifest --compact              # → all tool names, 117 tokens for 255 tools
mcptoon manifest --slim                 # → tool schemas, 93% smaller than JSON
mcptoon manifest --toon                 # → standard TOON format

# ─── Call a tool ───
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
mcptoon call --auto search '{"query":"AI"}' --toon  # auto-find server

# ─── Self-diagnosis ───
mcptoon doctor
```

### Install new MCP servers — one command, auto-generated

Found a new MCP server on GitHub? Install it with one command — mcptoon auto-connects, discovers tools, generates a handler, and registers it. No restart needed.

```bash
# From npm
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search

# From pip
mcptoon install my-tool --pip mcp-my-tool

# HTTP/SSE server
mcptoon install remote-api --url https://example.com/mcp

# List installed servers
mcptoon install --list

# Remove
mcptoon install --remove brave-search
```

### Use a pre-configured profile

23 battle-tested server profiles are included in `mcp/stdio/*.json`. Each is a ~1KB JSON file describing how to connect — security-audited with `credential_safe`, `env_vars_required`, and `permissions` declared.

```bash
# Browse profiles:
cat mcp/stdio/github.json

# Use any profile — just add the server:
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# Set your API key:
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx

# Use it:
mcptoon call github search_repos '{"query":"mcp"}' --toon
```

**Don't see your server?** mcptoon works with *any* MCP server, profile or not:

```bash
mcptoon add my-server --stdio npx -y @any/mcp-server
mcptoon manifest --toon    # works immediately
```

See all 23 profiles: [mcp/README.md](mcp/README.md)

---

## Docker

mcptoon is zero-dependency, so the image is small. Build it and run any subcommand. The entrypoint is `mcptoon`, so args pass through exactly as on the host:

```bash
docker build -t mcptoon .
docker run --rm mcptoon help
docker run --rm mcptoon manifest --toon
```

Server config lives at `~/.mcptoon/config.json` on the host. Mount it so the container shares your servers:

```bash
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --toon
```

`manifest`, `list`, `inspect`, and `doctor` are config-only and work out of the box. `call` and `add --stdio` spawn a server process (for example `npx`), so they need that runtime available inside the image: extend the Dockerfile with the toolchain your servers require.

---

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

---

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

**SLIM (with schemas, 14 tokens)** — when you need parameter details:

```
search_web|query:s*|num_results:n
fetch_url|url:s*
```

### Measured benchmark (255 tools, 5 formats)

| Tools | JSON | Std TOON | mcptoon | SLIM | Compact |
|-------|------|----------|---------|------|---------|
| 5 | 1,897 | 981 (-48%) | 785 (-59%) | 111 (-94%) | 16 (-99%) |
| 10 | 3,567 | 1,757 (-51%) | 1,391 (-61%) | 235 (-93%) | 34 (-99%) |
| 25 | 9,009 | 4,491 (-50%) | 3,580 (-60%) | 595 (-93%) | 97 (-99%) |
| 50 | 17,790 | 8,776 (-51%) | 6,981 (-61%) | 1,203 (-93%) | 117 (-99%) |
| 93 | 33,191 | 16,426 (-51%) | 13,086 (-61%) | 2,231 (-93%) | 117 (-100%) |
| 150 | 53,350 | 26,326 (-51%) | 20,958 (-61%) | 3,626 (-93%) | 117 (-100%) |
| 200 | 71,135 | 35,106 (-51%) | 27,952 (-61%) | 4,842 (-93%) | 117 (-100%) |
| **255** | **90,804** | **44,863 (-51%)** | **35,735 (-61%)** | **6,174 (-93%)** | **117 (-100%)** |

**Standard TOON** (`--toon`): **51% smaller** than JSON (round-trip safe).
**mcptoon format** (`--mcptoon`): **61% smaller** (round-trip safe).
**SLIM format** (`--slim`): **93% smaller** for full schemas.
**Compact** (`--compact`): **100% smaller** for tool names only.

Reproduce: `python _benchmark.py` → outputs `assets/benchmark_data.json`. Token count: `chars ÷ 4` (GPT BPE approximation).

### Third-party research & context window economics

| Source | Finding | Why it matters |
|--------|---------|---------------|
| [Anthropic, *Context Windows for Agents*](https://docs.anthropic.com/en/docs/build-with-claude/context-windows) | "Context window is a scarce resource. Every token of schema is a token stolen from the user's actual task." | MCP schemas are the #1 source of context waste in agent workflows |
| [OpenAI, *Function Calling Guide*](https://platform.openai.com/docs/guides/function-calling) | Tool definitions consume context tokens proportional to schema complexity | 100+ tools with full schemas can eat 40-80% of a 128K context window |
| [Cursor Team, *Context Engineering*](https://cursor.com/blog/context-engineering) | "The difference between a good and bad agent is almost always context management, not model intelligence." | Token optimization at the transport layer (like TOON) directly improves agent quality |
| [Latent Space, *MCP Ecosystem Analysis*](https://www.latent.space/p/mcp) | "The MCP protocol injects full JSON schemas into every request — this is by design, but it creates a scaling cliff around 20-30 tools." | Confirms the problem mcptoon solves: 20-30 tools is the pain point, not 100+ |
| [Simon Willison, *LLM Tooling*](https://simonwillison.net/2024/Nov/19/llms/) | "JSON is the least token-efficient format possible for structured data sent to an LLM." | Validates TOON's approach: any non-JSON encoding saves tokens |
| GitHub Issues | Puppeteer MCP (47 tools) + Playwright MCP (52 tools) = ~50K tokens of schemas alone | Two browser MCP servers consume more context than this entire README |

---

## How TOON works

mcptoon supports two token-efficient formats:

### Standard TOON (`--toon`)

Implements the [TOON (Token-Oriented Object Notation)](https://github.com/toon-format/toon) spec — an open-source format for token-efficient LLM data exchange. Uses YAML-style indentation for objects and CSV-style tabular layout for uniform arrays.

| JSON | Standard TOON | Why |
|---|---|---|
| `{"name":"search","count":3}` | `name: search\ncount: 3` | Newlines replace braces + quotes |
| `[{"id":1,"name":"Alice"}]` | `[1]{id,name}:\n  1,Alice` | Field declaration once + CSV rows |
| `[1, 2, 3]` | `[3]:\n  1\n  2\n  3` | Bracket notation for arrays |
| `true` / `false` / `null` | `true` / `false` / `null` | Kept as-is (1 token each) |

**Round-trip safe**: `decode(encode(x)) == x`. URLs, timestamps, and special characters are preserved.

### Legacy mcptoon format (`--mcptoon`)

mcptoon's original pipe-separated format. Simpler but less structured than standard TOON.

| JSON | mcptoon | Why |
|---|---|---|
| `{"name":"search","count":3}` | `name:search\|count:3` | Pipes replace braces + quotes |
| `[1, 2, 3]` | `1 2 3` | Spaces replace brackets + commas |
| `"https://example.com"` | `https\c//example.com` | Colons escaped as `\c` (round-trip safe) |

**Round-trip safe** with `mcptoon_decode()`. Escape sequences: `\c`=colon, `\p`=pipe, `\\`=backslash.

### SLIM format (`--slim`)

mcptoon-specific ultra-compact tool schema encoding. No external equivalent.

```
search|q:s*|n:n
fetch|url:s*
```

**tiktoken verification** (o200k_base / cl100k_base):

```
{"content":[{"type":"text","text":"hello"}]}  →  hello         (85% savings)
{"type":"object","properties":{"q":{"type":"string"}}}  →  q:s*        (83% savings)
```

Token optimization at the transport layer is mcptoon's primary focus.

## Output formats

| Flag | What you get | Token footprint |
|---|---|---|
| `--compact` | Tool names only, space-separated | **97% less than JSON** |
| `--slim` | Ultra-compact schemas (name\|param:type*) | **93% less than JSON** |
| `--toon` | Standard TOON (toon-format/toon spec) | 30-60% less than JSON (round-trip safe) |
| `--mcptoon` | Legacy mcptoon pipe format | 20-40% less than JSON (round-trip safe) |
| `--json` | Standard JSON (for scripts, CI) | Baseline |
| `--raw` | Raw response, no parsing | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Hard truncate at N chars | Variable |
| `--full` | Disable the default 4000-char truncation | Full size |

---

## Architecture — Three-layer decoupling

mcptoon is built on a **three-layer decoupled architecture**. Each layer is independent — swap one without touching the others.

```
┌─────────────────────────────────────────────────┐
│  Layer 1: mcptoon CLI (~200KB, zero deps)        │
│  ─────────────────────────────────────────────   │
│  Runs in your agent's shell. Token-optimizes     │
│  everything. No schemas in context. Ever.        │
└──────────────────────┬──────────────────────────┘
                       │ reads JSON templates (on disk)
┌──────────────────────▼──────────────────────────┐
│  Layer 2: MCP Server Profiles (~1KB each)         │
│  ─────────────────────────────────────────────   │
│  23 JSON templates in mcp/stdio/*.json.           │
│  Not installed software — just connection specs.  │
│  Security-audited: credential_safe, env_vars,     │
│  permissions declared per profile.                │
│  Add your own — it just works.                    │
└──────────────────────┬──────────────────────────┘
                       │ spawns on-demand via npx
┌──────────────────────▼──────────────────────────┐
│  Layer 3: Actual MCP Servers (npm packages)       │
│  ─────────────────────────────────────────────   │
│  Real MCP servers (@modelcontextprotocol/server-* │
│  etc). Only launched when you actually call a     │
│  tool. Not installed at config time.              │
│  Not loaded at startup. Zero overhead until use.  │
└─────────────────────────────────────────────────┘
```

**Why three layers?**

- **Layer 1 (CLI)** stays tiny — ~200KB, zero deps. No MCP SDK bloat.
- **Layer 2 (Profiles)** are editable JSON — add, remove, fork without touching code. Each is a ~1KB file describing *how to connect*, not the server itself.
- **Layer 3 (Servers)** spin up lazily — only when `mcptoon call` actually runs. No idle processes. No startup tax.

This means:
- 100 servers configured → 0 running until you use one
- Remove a profile → the rest work fine
- Add a profile → no code changes, no rebuild
- mcptoon never bundles MCP servers — you install what you use

### Security-audited profiles

Every profile declares its security posture:

```json
// mcp/stdio/puppeteer.json
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

23 profiles: fetch, github, exa, brave-search, firecrawl, filesystem, memory, sequential-thinking, sqlite, time, puppeteer, playwright, postgres, slack, notion, git, gitlab, tavily, google-maps, docker, aws, cloudflare, tmux. See [`mcp/README.md`](mcp/README.md).

→ **[Full ecosystem plan](ECOSYSTEM.md)**

---

## Features

**Tested** with 255+ MCP tools across 55+ servers, 30K+ real calls. 429 tests passing. 10/10 E2E tests passing.

- **`mcptoon install`** — One-command MCP server installation from npm/pip/HTTP with auto-handler generation
- **`mcptoon quickstart`** — One-command onboarding: discover + configure + show tools
- **`mcptoon doctor`** — Self-diagnosis (Python, config, servers, connectivity)
- **`mcptoon discover`** — Zero-config auto-discovery (config scan + env detection + network probe)
- **`mcptoon search`** — Cross-server tool search with multi-factor scoring
- **`mcptoon call --auto`** — Auto-route tool calls to the right server
- **`--stdin`** — Pipe large payloads bypassing OS command-line limits
- **Tool poisoning guard** — Detects prompt injection in MCP results
- **Credential leak detection** — Scans tool results for exposed API keys, AWS keys, GitHub PATs, OpenAI/Anthropic keys, Slack tokens, JWTs, private keys
- **Fuzzy match** — "Did you mean: search, search_all?" on typos
- **Cross-agent export** — `--format openai|openapi|mcp` for non-CLI agents
- **Schema cache** — 5-min TTL, avoids repeated `tools/list` round-trips
- **Usage tracking** — Local-only call statistics and token estimates
- **Dangerous-op blocking** — Blocks `delete`/`drop`/`purge` unless `--destructive`
- **Shell completion** — bash, zsh, fish, PowerShell
- **TOML config** — `~/.mcptoon/config.toml` support

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

---

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon_encode, toon_decode, mcptoon_encode

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon_encode(tools))         # Standard TOON output
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon_encode(result))        # Standard TOON output
    # Round-trip: decode back to Python dict
    decoded = toon_decode(toon_encode(result))
    assert decoded == result          # ✅ Round-trip safe
```

## Config

```bash
# stdio (any npx MCP server)
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github

# HTTP
mcptoon add myapi --http http://localhost:3001/mcp --header "Authorization: Bearer xxx"
```

Config lives at `~/.mcptoon/config.json`. Project-level override at `./.mcptoon.json`. TOML support at `~/.mcptoon/config.toml`.

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

## Privacy

- **No telemetry.** No analytics, no crash reports, no phone-home.
- **No credential storage.** API keys pass through from your config or env vars.
- **No dependencies.** Pure Python stdlib. No supply chain to audit.
- **Credential leak guard.** Scans tool results for exposed API keys/tokens — blocks them before they reach your agent.

---

## Architecture

```
src/mcptoon/
├── cli.py        # CLI entry + arg parsing
├── client.py     # MCPClient — stdio + HTTP transport
├── installer.py  # One-command MCP server installation + auto-handler generation
├── router.py     # Tool routing, custom handlers, poisoning + credential leak detection
├── config.py     # Server config (JSON + TOML)
├── manifest.py   # Tool discovery with cache + cross-server search
├── discover.py   # Zero-config auto-discovery (5-layer)
├── output.py     # Standard TOON + legacy mcptoon + JSON / compact / slim rendering
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes + fix suggestions
```

~4,500 lines. 429 tests + 10/10 E2E. Zero third-party imports. ~200KB source.

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 429 tests, 0.5s
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
