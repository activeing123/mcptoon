<div align="center">

# mcptoon

**Stop editing JSON for every agent. Add MCP tools once, use them everywhere.**

Cursor wants `.mcp.json`. Claude Code wants `.claude.json`. Codex wants `AGENTS.md`. Same tool, configured three times — one missing comma breaks everything.

mcptoon fixes this. Configure MCP servers once. Every agent uses them. No JSON editing. No restarts. No context window pollution.

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/mcptoon/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![Tests](https://img.shields.io/badge/Tests-513%20passed-brightgreen)](#contributing)

**👉 `pip install mcptoon`** · [English](README.md) · [中文文档](README.zh-CN.md) · [Report Bug](https://github.com/activeing123/mcptoon/issues)

</div>

---

## The problem: MCP config hell

Every AI agent has its own MCP config format. Adding a tool means:

| Agent | Config file | Format | What breaks |
|-------|------------|--------|-------------|
| **Claude Code** | `.claude.json` | JSON | One missing comma = all tools stop working |
| **Cursor** | `.mcp.json` | JSON | One wrong field = silent failure |
| **Codex** | `AGENTS.md` | Markdown | One typo = agent ignores your tools |
| **VS Code Copilot** | `settings.json` | JSON | Wrong nesting = MCP doesn't load |

**The reality:** You have 3+ agents on your machine. Same MCP server, configured 3 times, in 3 different formats. Update one? Forget to update the others. Now they're out of sync.

> *"I just want to add a new MCP service. Why is it like going through hell?"* — A real developer

---

## The fix: one command, all agents

```bash
pip install mcptoon                          # zero deps, ~250KB

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# Call from any agent — Claude Code, Cursor, Codex, anything:
mcptoon call fetch fetch '{"url":"https://example.com"}'
```

**That's it.** No `.claude.json` editing. No `.mcp.json` editing. No `AGENTS.md` editing.

Configure once in `~/.mcptoon/config.json`. Every agent calls `mcptoon` via shell. Switch agents tomorrow — your tools are still there, zero reconfiguration.

<div align="center">

![Benchmark: 255 tools, 90,804 → 117 tokens (tiktoken cl100k_base)](assets/benchmark.svg)

![Demo: mcptoon in action](assets/demo.gif)

</div>

---

## MCP security firewall (built-in)

MCP servers can execute code on your machine. **mcptoon is the firewall.**

Current MCP security landscape:
- **MCPoison** (Check Point): Cursor RCE via MCP config tampering
- **Tool Poisoning** (Invariant Labs): Malicious instructions in tool responses — affects all major platforms
- **50 known CVEs** in MCP ecosystem, 13 critical
- **200,000+ MCP servers** exposed to RCE risk (OX Security)

mcptoon blocks these attacks with three layers — all built-in, zero config:

| Layer | What it does | Attack blocked |
|-------|-------------|----------------|
| **Prompt injection guard** | Scans tool results for injection patterns | `"ignore previous instructions"` → blocked |
| **Credential leak guard** | Scans results for exposed API keys/tokens | `sk-abc...`, `AKIA...`, `ghp_...` → blocked |
| **Dangerous-op blocker** | Blocks `delete`/`drop`/`purge` by default | `docker_remove` → blocked unless `--destructive` |

- **No telemetry.** No analytics, no crash reports, no phone-home.
- **No credential storage.** API keys pass through from your config or env vars.
- **No dependencies.** Pure Python stdlib. No supply chain to audit.

---

## 30-second quick start

```bash
pip install mcptoon                          # zero deps, ~250KB

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# See all available tools (117 tokens for 255 tools):
mcptoon manifest --compact

# Call a tool:
mcptoon call fetch fetch '{"url":"https://example.com"}'

# Or let mcptoon discover servers already on your machine:
mcptoon quickstart     # auto-discover + configure + show tools — all in one command
```

---

## Used by

<!-- Add your project here — PR welcome! -->

*Building something with mcptoon? [Open an issue](https://github.com/activeing123/mcptoon/issues) to be listed here.*

---

## Works with shell-capable AI agents

mcptoon is a **CLI tool, not an MCP Server**. It does not plug into `mcpServers` JSON config. Instead, your agent calls `mcptoon` via shell commands — schemas stay out of context.

| Agent | How to use |
|------|------------|
| **Claude Code** | Write `mcptoon` commands in SKILL.md files |
| **Codex (OpenAI)** | Add `mcptoon` to AGENTS.md |
| **Cursor** | Add `mcptoon` to .cursorrules (agent generates shell commands) |
| **OpenCode** | Use `mcptoon` in custom commands |
| **Any agent** | If it runs shell commands, it can call `mcptoon` |

Configure once in `~/.mcptoon/config.json`. Every agent shares the same servers and tools. Switch agents — config follows you.

---

## Token savings (bonus, not the point)

mcptoon keeps tool schemas **outside** your agent's context window. This is a side benefit of the CLI architecture — not the main selling point.

| Tools | JSON schemas in context | mcptoon compact | Savings |
|-------|------------------------|-----------------|---------|
| 5 | 1,897 tokens | 16 tokens | 99% |
| 50 | 17,790 tokens | 117 tokens | 99% |
| 255 | 90,804 tokens | 117 tokens | 99.9% |

- `--compact` → tool names only: **99.9% savings** (tiktoken cl100k_base)
- `--slim` → tool schemas with params: **93% savings**
- `--json` → standard JSON (default)
- `--toon` → TOON encoding (optional, 30-40% savings)

<details>
<summary><b>Output formats reference</b></summary>

| Flag | What you get | Token savings |
|------|-------------|---------------|
| `--compact` | Tool names only | 99.9% vs JSON (tiktoken) |
| `--slim` | Tool schemas (`name\|param:type*`) | 93% vs JSON |
| `--json` | Standard JSON (default) | Baseline |
| `--toon` | TOON encoding (toon-format v4.1 spec) | 30-40% vs JSON |
| `--raw` | Raw response | Full size |
| `--head N` | First N items only | Variable |
| `--max-chars N` | Truncate at N chars | Variable |
| `--full` | Disable default 4000-char truncation | Full size |
| `--stdin` | Read args from stdin (large payloads) | — |
| `--fallback-json` | Fall back to JSON if TOON encoding errors | Safety net |

</details>

<details>
<summary><b>What is TOON? (optional reading)</b></summary>

**TOON (Token-Oriented Object Notation)** is an open data format specification by [Johann Schopplich](https://github.com/johannschopplich) ([toon-format/toon](https://github.com/toon-format/toon), 25K+ stars). It's designed to reduce token consumption when feeding structured data to LLMs.

mcptoon vendors `python-toon` v0.1.1 (MIT) for spec-compliant encoding. TOON is **optional** — mcptoon defaults to JSON and works perfectly without TOON.

</details>

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
mcptoon inspect <server> <tool> # show one tool's schema
mcptoon search <query>          # search tools across all servers
mcptoon call <server> <tool> '{"args":"here"}'   # call a tool
mcptoon call --auto <tool> '{"args":"here"}'     # auto-find the server
mcptoon sync                   # sync config to all agents (Claude Desktop, Cursor, etc.)
mcptoon sync --dry             # preview what would be written
mcptoon sync --agent cursor    # sync to one agent only
mcptoon health                 # health check all servers (catches zombie servers)
mcptoon health --json           # JSON output for CI/CD (exit 1 if any dead)
mcptoon serve                  # run as stdio MCP server (1 Agent → 100 servers)
mcptoon doctor                  # self-diagnose: Python, config, connectivity
mcptoon usage                   # local-only call statistics
mcptoon completion bash         # shell completion (bash/zsh/fish/ps)
```

---

## Sync config to all agents

Configure once in mcptoon, sync to every agent automatically:

```bash
mcptoon sync                 # writes to Claude Desktop, Cursor, Cline, Windsurf, VS Code Copilot
mcptoon sync --dry           # preview without writing
mcptoon sync --agent cursor  # sync to one agent only
```

mcptoon detects which agents you have installed and writes their native config format. No more editing `.claude.json`, `.cursor/mcp.json`, or `settings.json` by hand. Update in mcptoon → sync → all agents see the same servers.

---

## Health check (catch zombie servers)

52% of MCP servers are unreachable ([source](https://www.163.com/dy/article/KSSN2L5E05561FZP.html)). Check before you use:

```bash
mcptoon health                 # check all servers: alive, dead, latency, tool count
mcptoon health --timeout 5     # 5s timeout per server
mcptoon health --json           # JSON for CI/CD (exits 1 if any dead)
```

Output:
```
── mcptoon health: 3/5 alive, 2 dead ──

  ✓ fetch     [stdio]   3 tools    120ms  ok
  ✗ brave     [stdio]   0 tools  10002ms  timeout → Timed out after 10s
  ✓ github    [http]   12 tools    340ms  ok
  ✗ broken    [stdio]   0 tools    500ms  error → Connection refused
```

Perfect for CI/CD: `mcptoon health --json || exit 1` in your pipeline.

---

## Run as MCP server (serve mode)

mcptoon can also act as a **single MCP server** in front of your agent — proxying all underlying servers with safety checks:

```json
// In your agent's mcpServers config:
"mcptoon": {
  "command": "mcptoon",
  "args": ["serve"]
}
```

- Agent connects to **1 server** (mcptoon), not 100 individual servers
- All tool calls pass through mcptoon's **security firewall** (prompt injection + credential leak detection)
- **Parallel manifest loading**: 100 servers in ~5s
- **Per-call timeout**: no single server can hang the bridge
- **Tool namespacing**: `{server}_{tool}` prevents conflicts

```bash
mcptoon serve                  # stdio mode (for Claude Code, Cursor, etc.)
mcptoon serve --listen :8080   # HTTP mode (for remote/multi-agent)
mcptoon serve --auth <token>    # HTTP mode with Bearer token auth
```

---

## How it works

mcptoon is a **CLI tool**, not an MCP client library or MCP Server. Your agent doesn't connect to MCP servers — it runs `mcptoon` commands. Schemas live on disk in `~/.mcptoon/config.json`, not in your context window.

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
    result = c.call_tool("fetch", {"url": "https://example.com"})
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
├── output.py     # TOON (vendored python-toon) + compact/slim rendering
├── toon_vendored.py  # Vendored spec-compliant TOON encoder/decoder (MIT)
├── cache.py      # Schema cache (5-min TTL)
├── sync.py       # Config sync to AI agents (Claude Desktop, Cursor, Cline, etc.)
├── health.py     # Batch health check for all MCP servers
├── usage.py      # Local usage tracking
└── errors.py     # Structured error envelopes + fix suggestions
```

~6,800 lines. 513 tests. Zero third-party imports. ~250KB source.

---

## Docker

```bash
docker build -t mcptoon .
docker run --rm mcptoon help
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --compact
```

---

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 513 tests, 0.5s
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

**Found this useful? Star the repo to help others find it.**

</div>
