<div align="center">

# mcptoon

**Add 1,000 MCP tools to your local environment. Worry zero about token context.**

mcptoon is a CLI tool that sits between your AI agent and MCP servers. Add unlimited servers — your agent's context window stays clean. Schemas never enter it. Only the compact result you request does, and it's 30-97% smaller than JSON.

**You own your tools.** mcptoon ships zero bundled servers — just a 200KB CLI. You add the servers you want, one command each, from npm/pip/HTTP. Delete mcptoon? Your MCP servers keep working independently.

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/mcptoon/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![Tests](https://img.shields.io/badge/Tests-429%20passed-brightgreen)](#contributing)

**👉 `pip install mcptoon`** · [English](README.md) · [中文文档](README.zh-CN.md) · [Server Profiles](mcp/README.md) · [Report Bug](https://github.com/activeing123/mcptoon/issues)

![Benchmark: 255 tools, 90,804 → 117 tokens](assets/benchmark.svg)

</div>

---

## 30-second quick start

```bash
pip install mcptoon                          # zero deps, 200KB

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# See all available tools (117 tokens for 255 tools):
mcptoon manifest --compact

# Call a tool — output is 30-97% smaller than JSON:
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**Or let mcptoon discover servers already on your machine:**

```bash
mcptoon quickstart     # auto-discover + configure + show tools — all in one command
```

That's it. No JSON config editing. No MCP protocol debugging. No context window pollution.

---

## What problem does this solve?

Every MCP-enabled agent (Claude Code, Cursor, Codex, etc.) loads **all tool schemas into your context window** before any work starts:

```
10 MCP servers → 50,000-100,000+ tokens of JSON schemas → 128K context: 40-80% gone
100 servers → 200,000+ tokens → context window is dead
```

So you unload servers when not needed. Reload when needed. Repeat. Forever. And adding a new server means hand-editing JSON config files — one syntax error and nothing works.

**mcptoon fixes this.** All your MCP servers stay configured, but their schemas **never enter your agent's context**. Your agent just runs `mcptoon` commands. Only the compact result you request enters context — and TOON encoding makes it 30-97% smaller than JSON.

```
Without mcptoon:  255 tools → 90,804 tokens of schemas in your context
With mcptoon:      255 tools → 117 tokens. That's 99.87% savings.
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

# List what you have:
mcptoon install --list

# Remove:
mcptoon install --remove brave-search
```

mcptoon auto-connects, discovers tools, generates a handler, and registers it. No restart needed.

**23 connection templates** are included for popular servers (fetch, github, puppeteer, sqlite, slack, etc.) — each is a ~1KB JSON file, *not* a bundled server. They just describe how to connect. You still install servers yourself. Think of them as recipe cards, not ingredients. Don't want them? Ignore them. They take 23KB total. See [mcp/README.md](mcp/README.md).

**Works with any MCP server**, template or not:

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest --toon    # works immediately
```

---

## Works with every AI agent

mcptoon is a CLI tool. **If your agent can run shell commands, it can use mcptoon.** No plugins, no SDK, no per-agent setup.

| Agent | How to use |
|---|---|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files |
| **Codex (OpenAI)** | Add `mcptoon` to AGENTS.md |
| **Cursor** | Add `mcptoon` to .cursorrules |
| **OpenCode** | Use `mcptoon` in custom commands |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

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

### Token savings (255 tools, 5 formats)

| Tools | JSON | TOON | SLIM | Compact |
|-------|------|------|------|---------|
| 5 | 1,897 | 981 (-48%) | 111 (-94%) | 16 (-99%) |
| 50 | 17,790 | 8,776 (-51%) | 1,203 (-93%) | 117 (-99%) |
| 255 | **90,804** | **44,863 (-51%)** | **6,174 (-93%)** | **117 (-100%)** |

- `--compact` → tool names only: **97-100% savings**
- `--slim` → tool schemas with params: **93% savings**
- `--toon` → structured results (round-trip safe): **30-60% savings**

Reproduce: `python _benchmark.py` → outputs `assets/benchmark_data.json`

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
| `--compact` | Tool names only | **97-100%** vs JSON |
| `--slim` | Tool schemas (`name\|param:type*`) | **93%** vs JSON |
| `--toon` | Standard TOON (toon-format/toon spec) | **30-60%**, round-trip safe |
| `--json` | Standard JSON | Baseline |
| `--raw` | Raw response | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Truncate at N chars | Variable |
| `--full` | Disable default 4000-char truncation | Full size |
| `--stdin` | Read args from stdin (large payloads) | — |

---

## How it works

mcptoon is a **CLI tool**, not an MCP client library. Your agent doesn't connect to MCP servers — it runs `mcptoon` commands. Schemas live on disk in `~/.mcptoon/config.json`, not in your context window.

**Three layers, fully decoupled:**

```
Layer 1: mcptoon CLI (~200KB, zero deps)
         Runs in your agent's shell. No schemas in context. Ever.
                    │
Layer 2: Server Profiles (~1KB each, 23 included)
         JSON templates describing how to connect. Not installed software.
         Add your own — it just works.
                    │
Layer 3: Actual MCP Servers (npm packages)
         Launched on-demand only when you call a tool. Zero overhead until use.
```

- 100 servers configured → 0 running until you use one
- mcptoon never bundles MCP servers — you install what you use
- Each profile is security-audited: declares `credential_safe`, `env_vars_required`, `permissions`

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
├── discover.py   # Zero-config auto-discovery (5-layer)
├── output.py     # Standard TOON + legacy mcptoon + compact/slim rendering
├── cache.py      # Schema cache (5-min TTL)
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes + fix suggestions
```

~4,500 lines. 429 tests. Zero third-party imports. ~200KB source.

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
python -m pytest tests/ -v   # 429 tests, 0.5s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

**Found this useful? Star the repo to help others find it.**

</div>
