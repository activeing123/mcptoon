<div align="center">

# mcptoon

**Install 1,000 MCP tools locally. Schemas consume 0 tokens. Any agent, zero MCP config.**

Download a brand-new agent today — it can immediately call all 1,000 MCP tools. No `mcpServers` JSON to edit. No MCP protocol to configure. Tools are lazy-loaded (0 servers running until you call one). Schemas never enter your context window. Switch to any other agent tomorrow — same 1,000 tools, zero reconfiguration.

**You own your tools.** mcptoon ships zero bundled servers — just a ~250KB CLI. You add the servers you want, one command each, from npm/pip/HTTP. Switch agents? Your tools follow. Delete mcptoon? Servers keep running.

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/mcptoon/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![Tests](https://img.shields.io/badge/Tests-486%20passed-brightgreen)](#contributing)

**👉 `pip install mcptoon`** · [English](README.md) · [中文文档](README.zh-CN.md) · [Report Bug](https://github.com/activeing123/mcptoon/issues)

</div>

## mcptoon vs your current MCP manager

| | Your current MCP manager | mcptoon |
|---|---|---|
| **Agent setup** | Edit `mcpServers` JSON in agent config. One typo breaks everything. | Run `mcptoon` shell commands. No agent config to touch. |
| **Schema tokens** | All schemas loaded into context on launch. 10 servers = 50K-100K tokens gone. | Zero. Schemas never enter context. Only the compact result you request. |
| **New agent** | Download agent. Find its config file. Edit JSON. Add servers. Restart. Repeat per agent. | Download agent. Run `mcptoon call`. 1,000 tools ready. That's it. |
| **Switch agents** | Each agent has its own MCP config format. Migration is manual and painful. | Zero config. Any new agent calls 1,000 tools out of the box. |
| **Server lifecycle** | All configured servers start on agent launch. Running even when unused. Eating RAM. | Lazy-load. Servers start only when you call a tool. 0 running until needed. |
| **Add a server** | Find package. Edit JSON. Check syntax. Restart agent. | `mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch` |
| **Result size** | Full JSON response enters your context window. | TOON/SLIM encoding. 30-93% smaller than JSON. |
| **100 servers** | 350K+ tokens of schemas. Context window dead before you start. | 0 token schemas. Context window clean. Tools wait on disk. |
| **Security** | Depends on the agent. Most have no built-in guards. | Prompt injection guard + credential leak detection + dangerous-op blocker. |

| | |
|---|---|
| **90,804** tokens | 255 tool schemas in context (current MCP manager) |
| **117** tokens | 255 tools via mcptoon `--compact` (99.9% less) |
| **0** tokens | schemas in context with mcptoon (always) |

**Bottom line:** Your current MCP manager taxes your context window with schemas you might never use. mcptoon keeps tools outside the agent, calls them on demand, and compresses results. Your context window stays yours.

<div align="center">

![Benchmark: 255 tools, 90,804 → 117 tokens (tiktoken cl100k_base)](assets/benchmark.svg)

![Demo: mcptoon in action](assets/demo.gif)

</div>

---

## 30-second quick start

```bash
pip install mcptoon                          # zero deps, ~250KB

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# See all available tools (117 tokens for 255 tools):
mcptoon manifest --compact

# Call a tool — output is 30-93% smaller than JSON:
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**Or let mcptoon discover servers already on your machine:**

```bash
mcptoon quickstart     # auto-discover + configure + show tools — all in one command
```

That's it. No JSON config editing. No MCP protocol debugging. No context window pollution.

---

## Used by

<!-- Add your project here — PR welcome! -->

*Building something with mcptoon? [Open an issue](https://github.com/activeing123/mcptoon/issues) to be listed here.*

---

## What problem does this solve?

Every MCP-enabled agent (Claude Code, Cursor, Codex, etc.) loads **all tool schemas into your context window** before any work starts:

```
10 MCP servers → 50,000-100,000+ tokens of JSON schemas → 128K context: 40-80% gone
100 servers → 350,000+ tokens → context window is dead
```

So you unload servers when not needed. Reload when needed. Repeat. Forever. And adding a new server means hand-editing JSON config files — one syntax error and nothing works.

**mcptoon fixes this.** All your MCP servers stay configured, but their schemas **never enter your agent's context**. Your agent just runs `mcptoon` commands. Only the compact result you request enters context — and TOON encoding makes it 30-93% smaller than JSON.

```
Without mcptoon:  255 tools → 90,804 tokens of schemas in your context (tiktoken cl100k_base)
With mcptoon:      255 tools → 6,174 tokens (SLIM format). 93% savings.
                   255 tools → 117 tokens (compact, names only). 99.9% savings.
```

---

## Install MCP servers — one command each

```bash
# From npm (most MCP servers live here):
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search

# From pip:
mcptoon install my-tool --pip mcp-my-tool

# HTTP/SSE server:
mcptoon install remote-api --url https://example.com/mcp

# Parallel Search (optional; no account or API key required):
mcptoon install parallel-search --url https://search.parallel.ai/mcp

# List what you have:
mcptoon install --list

# Remove:
mcptoon install --remove brave-search
```

When you explicitly use Parallel Search, user-provided search objectives, search queries, and
requested URLs are sent to Parallel.

mcptoon auto-connects, discovers tools, generates a handler, and registers it. No restart needed.

**Works with any MCP server:**

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest --toon    # works immediately
```

---

## Works with shell-capable AI agents

mcptoon is a **CLI tool, not an MCP Server**. It does not plug into `mcpServers` JSON config. Instead, your agent calls `mcptoon` via shell commands — schemas stay out of context.

**Works with (shell-capable agents):**

| Agent | How to use |
|---|---|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files |
| **Codex (OpenAI)** | Add `mcptoon` to AGENTS.md |
| **Cursor** | Add `mcptoon` to .cursorrules (agent generates shell commands) |
| **OpenCode** | Use `mcptoon` in custom commands |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

**Does NOT replace native MCP config:**
- Cursor's `mcpServers` setting → unaffected (mcptoon is separate, not a server entry)
- Claude Desktop's `claude_desktop_config.json` → unaffected
- mcptoon does not output MCP JSON-RPC protocol stream — it is a client, not a server

Configure once in `~/.mcptoon/config.json`. Every agent shares the same servers and tools. Switch agents — config follows you.

```bash
export MCPTOON_AGENT_TYPE=claude   # auto-select --toon for all calls
```

Your agent can even add tools on its own — no human intervention:

```bash
# Agent needs GitHub access mid-task? It runs:
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon call github search_repos '{"query":"mcp"}' --toon
# Done. No JSON editing. No restart. No context lost.
```

---

## The numbers

### Token savings (255 tools, tiktoken cl100k_base)

All numbers from `tiktoken.get_encoding("cl100k_base")` — OpenAI's official BPE tokenizer.

| Tools | JSON | TOON | SLIM | Compact |
|-------|------|------|------|---------|
| 5 | 1,897 | 1,167 (-39%) | 111 (-94%) | 16 (-99%) |
| 50 | 17,790 | 10,688 (-40%) | 1,203 (-93%) | 117 (-99%) |
| 255 | **90,804** | **54,649 (-40%)** | **6,174 (-93%)** | **117 (-99.9%)** |

- `--compact` → tool names only: **99.9% savings** (tiktoken cl100k_base)
- `--slim` → tool schemas with params: **93% savings** (tiktoken cl100k_base)
- `--toon` → structured results (round-trip safe): **30-40% savings**

<details>
<summary><b>What is TOON? Why does mcptoon use it?</b></summary>

**TOON (Token-Oriented Object Notation)** is an open data format specification by [Johann Schopplich](https://github.com/johannschopplich) ([toon-format/toon](https://github.com/toon-format/toon), 25K+ stars). It's designed specifically to reduce token consumption when feeding structured data to LLMs.

**Why TOON instead of JSON/YAML/CSV?**

| Format | Problem for LLMs |
|--------|-----------------|
| JSON | Braces `{}`, brackets `[]`, quotes `""`, commas — each is a separate BPE token. 255 tool schemas = ~91K tokens. |
| YAML | Indentation-sensitive, hard for LLMs to generate correctly, no array length hints. |
| CSV | No nesting, no key-value pairs, no type information. |
| TOON | YAML-style keys + CSV-style arrays + length hints `[N]` + type literals. 30-40% fewer tokens than JSON. |

**What mcptoon uses from TOON spec v4.1:**

| Feature | Used? | Example |
|---------|-------|---------|
| YAML-style objects (`key: value`) | ✅ | `name: search` |
| Tabular arrays (`[N,]{fields}: rows`) | ✅ | `[2,]{id,name}:\n  1,Alice\n  2,Bob` |
| Inline scalar arrays (`key[N]: v1,v2,v3`) | ✅ | `tags[3]: ai,ml,nlp` |
| Nested objects (indentation) | ✅ | `config:\n  host: localhost` |
| Type literals (`true`/`false`/`null`) | ✅ | `active: true` |
| String quoting (only when needed) | ✅ | `desc: "hello, world"` |
| Backslash escaping in quoted strings | ✅ | `desc: "say \"hi\""` |
| Length markers (`#` prefix) | ❌ Not needed | — |
| Pipe/tab delimiters | ❌ Not needed | Comma delimiter only |
| Root scalar values | ❌ Not needed | MCP data is always objects/arrays |

**Compatibility:**

- Encoder/decoder: **vendored from [python-toon](https://github.com/xaviviro/python-toon) v0.1.1** (MIT License, by Xavi Vinaixa) — spec-compliant implementation
- Official TypeScript reference: [toon-format/toon](https://github.com/toon-format/toon) (25K+ stars)
- Round-trip safe: `decode(encode(x)) == x` for all JSON-serializable data
- Non-strict decode mode (lenient parsing for real-world MCP outputs)
- **Known minor differences:** empty containers output `{}`/`[]` (instead of spec's empty string); 3 edge-case decode patterns (keyed tabular form, nested field groups) — all non-blocking for MCP use cases
- 47/52 compatibility tests pass against official spec

**Why not use the official `toon-format` PyPI package directly?**

The official Python implementation ([toon-format/toon-python](https://github.com/toon-format/toon-python)) is currently in beta — its encoder raises `NotImplementedError`. We vendor the community implementation (`python-toon` by Xavi Vinaixa) instead, which is functional and spec-compliant. When the official Python encoder is stable, we'll switch.

**TOON vs SLIM vs Compact — what's the difference?**

| Format | Origin | Use case | Savings |
|--------|--------|----------|---------|
| `--toon` | Open spec (toon-format/toon v4.1) | General structured output, round-trip safe | 30-40% vs JSON |
| `--slim` | mcptoon-specific | Tool schemas only (`name\|param:type*`) | 93% vs JSON |
| `--compact` | mcptoon-specific | Tool names only | 99.9% vs JSON |

SLIM and Compact are **not** part of the TOON spec. They are mcptoon-specific optimizations for tool discovery. TOON is the general-purpose format for tool call results.

</details>

Reproduce: `pip install tiktoken && python -c "import mcptoon; mcptoon._benchmark()"` → outputs `assets/benchmark_data.json`

### Before vs after — concrete example

**Without mcptoon** (what every MCP client puts in your context — 287 tokens):

```json
[{"name":"search_web","description":"Search the web for information",
"inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"Search query"}}}}]
```

**With mcptoon** (5 tokens):

```
search_web
```

**With mcptoon --slim** (14 tokens, includes parameter info):

```
search_web|query:s*
```

---

## Security

Three layers of protection, all built-in:

| Layer | What it does | Example |
|-------|-------------|---------|
| **Dangerous-op guard** | Blocks `delete`/`drop`/`purge` by default | `docker_remove` → blocked unless `--destructive` |
| **Prompt injection guard** | Scans results for injection patterns | `"ignore previous instructions"` → blocked |
| **Credential leak guard** | Scans results for exposed keys/tokens | `sk-abc...xyz` → blocked before reaching your agent |

- **No telemetry.** No analytics, no crash reports, no phone-home.
- **No credential storage.** API keys pass through from your config or env vars.
- **No dependencies.** Pure Python stdlib. No supply chain to audit.

---

## All commands

```bash
mcptoon quickstart              # one-command onboarding (discover + configure + show tools)
mcptoon init --auto             # auto-discover MCP servers on your machine
mcptoon add <name> --stdio npx -y <package>   # add any MCP server
mcptoon install <name> --npm <package>        # install + auto-generate handler
mcptoon list                    # show configured servers
mcptoon manifest --compact      # all tool names (117 tokens for 255 tools)
mcptoon manifest --slim         # tool schemas (93% smaller than JSON)
mcptoon manifest --toon         # standard TOON format
mcptoon inspect <server> <tool> # show one tool's schema
mcptoon search <query>          # search tools across all servers
mcptoon call <server> <tool> '{"args":"here"}' --toon   # call a tool
mcptoon call --auto <tool> '{"args":"here"}' --toon     # auto-find the server
mcptoon doctor                  # self-diagnose: Python, config, connectivity
mcptoon usage                   # local-only call statistics
mcptoon completion bash         # shell completion (bash/zsh/fish/ps)
```

### Output formats

| Flag | What you get | Token savings |
|---|---|---|
| `--compact` | Tool names only | **99.9%** vs JSON (tiktoken) |
| `--slim` | Tool schemas (`name\|param:type*`) | **93%** vs JSON (tiktoken) |
| `--toon` | Spec-compliant TOON (vendored python-toon v0.1.1, toon-format v4.1) | **30-40%**, round-trip safe |
| `--json` | Standard JSON | Baseline |
| `--raw` | Raw response | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Truncate at N chars | Variable |
| `--full` | Disable default 4000-char truncation | Full size |
| `--stdin` | Read args from stdin (large payloads) | — |
| `--fallback-json` | Fall back to JSON if TOON encoding errors | Safety net |

> **Note on `--fallback-json`:** Only catches encoding-level errors (e.g., unsupported data types). It does not detect whether the LLM successfully parsed the output — that's the caller's responsibility.

---

## How it works

mcptoon is a **CLI tool**, not an MCP client library or MCP Server. Your agent doesn't connect to MCP servers — it runs `mcptoon` commands. Schemas live on disk in `~/.mcptoon/config.json`, not in your context window.

**Architecture boundary:**
- mcptoon is an **MCP Client** — it connects to MCP servers internally via stdio/HTTP
- mcptoon does **not** expose an MCP JSON-RPC endpoint for native MCP hosts
- `--json` output is a tool list fragment, not a full MCP protocol message (no `initialize`, `id`, `method` fields)
- To use with Cursor/Claude Desktop native MCP: configure their `mcpServers` separately. mcptoon is for shell-capable agents only.

**Two layers, fully decoupled:**

```
Layer 1: mcptoon CLI (~200KB, zero deps)
         Runs in your agent's shell. No schemas in context. Ever.
                    │
Layer 2: Actual MCP Servers (npm/pip packages)
         Launched on-demand only when you call a tool. Zero overhead until use.
```

- 1,000 servers configured → 0 running until you use one
- mcptoon ships zero bundled servers — you add what you want, one command each
- Delete mcptoon? Your MCP servers keep working independently

---

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon_encode, toon_decode

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon_encode(tools))         # compact TOON output
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon_encode(result))        # compact TOON output
    decoded = toon_decode(toon_encode(result))
    assert decoded == result          # round-trip safe
```

---

## Architecture

```
src/mcptoon/
├── cli.py        # CLI entry + arg parsing
├── client.py     # MCPClient — stdio + HTTP transport
├── installer.py  # One-command MCP server installation + auto-handler
├── router.py     # Tool routing + poisoning/credential leak detection
├── config.py     # Server config (JSON + TOML)
├── manifest.py   # Tool discovery with cache + cross-server search
├── discover.py   # Zero-config auto-discovery (4-layer)
├── output.py     # TOON (vendored python-toon) + legacy mcptoon + compact/slim rendering
├── toon_vendored.py  # Vendored spec-compliant TOON encoder/decoder (MIT, python-toon v0.1.1)
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes + fix suggestions
```

~6,400 lines. 486 tests. Zero third-party imports. ~250KB source.

## Docker

```bash
docker build -t mcptoon .
docker run --rm mcptoon help
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --toon
```

`manifest`, `list`, `inspect`, `doctor` work out of the box. `call` and `add --stdio` need the server runtime (e.g. `npx`) available in the image.

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 486 tests, 0.5s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

**Found this useful? Star the repo to help others find it.**

</div>
