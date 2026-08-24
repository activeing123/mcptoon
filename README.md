<div align="center">

# mcptoon

**One config for every MCP server. Every AI agent. Zero JSON editing.**

`pip install mcptoon`

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/mcptoon/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-ZERO-orange)](#privacy)
[![Tests](https://img.shields.io/badge/Tests-513%20passed-brightgreen)](#contributing)

[English](README.md) · [中文文档](README.zh-CN.md) · [Report Bug](https://github.com/activeing123/mcptoon/issues)

</div>

---

## What problem does this solve?

You use Claude Code, Cursor, and maybe Codex. Each one wants MCP servers configured in a different file, in a different format:

| Agent | Config file | Format |
|-------|-------------|--------|
| Claude Desktop | `claude_desktop_config.json` | JSON |
| Cursor | `.cursor/mcp.json` | JSON |
| Claude Code | `.claude.json` | JSON |
| VS Code Copilot | `settings.json` | JSON (nested) |

You add a server to Cursor. Forget to add it to Claude. Now Claude does not have it. You fix a path in Claude. Forget to fix it in Cursor. Now Cursor is broken.

mcptoon sits in between. You configure servers once. Run `mcptoon sync` and it writes the correct format to every agent. Run `mcptoon health` and it tells you which servers are actually alive.

## Install

```bash
pip install mcptoon
```

No dependencies. Works on Windows, macOS, Linux. Python 3.10+.

## Quick start

```bash
# Add a server (any MCP server from npm):
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# See what tools you have:
mcptoon manifest --compact

# Call a tool:
mcptoon call fetch fetch '{"url":"https://example.com"}'

# Sync to every agent on your machine:
mcptoon sync

# Check which servers are alive:
mcptoon health
```

## Commands

| Command | What it does |
|---------|-------------|
| `mcptoon add <name> --stdio <cmd>` | Add an MCP server |
| `mcptoon list` | Show configured servers |
| `mcptoon manifest --compact` | List all tool names (very small) |
| `mcptoon manifest --slim` | List tools with params (still small) |
| `mcptoon call <server> <tool> '{...}'` | Call a tool |
| `mcptoon call --auto <tool> '{...}'` | Call a tool, auto-find the server |
| `mcptoon sync` | Write config to every agent (Claude Desktop, Cursor, Cline, Windsurf, VS Code Copilot) |
| `mcptoon sync --dry` | Preview what sync would write |
| `mcptoon sync --agent cursor` | Sync to one agent only |
| `mcptoon health` | Check if each server is alive, dead, how fast |
| `mcptoon health --json` | JSON output for CI/CD (exits 1 if any dead) |
| `mcptoon serve` | Run as a single MCP server in front of your agent |
| `mcptoon install <name> --npm <pkg>` | Install from npm, auto-discover tools |
| `mcptoon search <query>` | Search tools across all servers |
| `mcptoon doctor` | Self-diagnose: Python, config, connectivity |
| `mcptoon quickstart` | Discover + configure + show tools, one command |

## sync: one config, every agent

```bash
mcptoon sync
```

That is it. mcptoon detects which agents you have installed (Claude Desktop, Cursor, Cline, Windsurf, VS Code Copilot) and writes their native config format. If you already have servers configured in an agent, mcptoon merges instead of overwriting.

```bash
mcptoon sync --dry           # see what it would write, no changes
mcptoon sync --agent cursor  # only sync to Cursor
```

## health: catch dead servers

52% of MCP servers are unreachable ([source](https://www.163.com/dy/article/KSSN2L5E05561FZP.html)). A server in your config does not mean it is alive.

```bash
mcptoon health
```

Output:
```
── mcptoon health: 3/5 alive, 2 dead ──

  ✓ fetch     [stdio]   3 tools    120ms  ok
  ✗ brave     [stdio]   0 tools  10002ms  timeout
    → Timed out after 10s
  ✓ github    [http]   12 tools    340ms  ok
  ✗ broken    [stdio]   0 tools    500ms  error
    → Connection refused
```

For CI/CD, use `--json` and it exits 1 if any server is dead:

```bash
mcptoon health --json || exit 1
```

## serve: one server, all tools

If your agent supports `mcpServers` in its config, you can point it at mcptoon instead of listing every server individually:

```json
"mcptoon": {
  "command": "mcptoon",
  "args": ["serve"]
}
```

Your agent connects to one server. mcptoon proxies all your configured servers behind it, with the same security checks (prompt injection, credential leak detection) applied to every call.

```bash
mcptoon serve                  # stdio mode
mcptoon serve --listen :8080   # HTTP mode (remote, multi-agent)
```

## Security

MCP servers run code on your machine. mcptoon inspects every tool result before it reaches your agent:

| Check | What it blocks |
|-------|----------------|
| Prompt injection | `"ignore previous instructions"` in tool output |
| Credential leak | `sk-...`, `AKIA...`, `ghp_...` in tool output |
| Dangerous operations | `delete`, `drop`, `purge` in tool names (unless you pass `--destructive`) |

No telemetry. No analytics. No phone-home. API keys pass through from your config or environment variables, never stored by mcptoon.

## Token savings

When your agent asks "what tools are available?", mcptoon returns tool names, not full JSON schemas:

| 255 tools | Full JSON | mcptoon `--compact` |
|-----------|-----------|---------------------|
| Token cost | 90,804 | 117 |

This is a side effect of the CLI architecture, not the main pitch. The main pitch is: configure once, use everywhere.

<details>
<summary>Output format reference</summary>

| Flag | What you get | When to use |
|------|-------------|------------|
| `--compact` | Tool names only | "What tools do I have?" |
| `--slim` | Names + param types | "What params does this tool take?" |
| `--json` | Standard JSON | Default, safe for everything |
| `--toon` | TOON encoding (30-40% smaller) | Optional, needs no extra deps |
| `--full` | No truncation | When you need everything |
| `--head N` | First N items | Quick preview |
| `--stdin` | Read args from stdin | Large payloads |

</details>

## How it works

```
Your agent (Claude, Cursor, Codex, anything)
        │
        │ runs `mcptoon call fetch fetch '{"url":"..."}'`
        ▼
mcptoon CLI (~250KB, zero deps)
        │
        │ spawns the server, calls the tool, returns the result
        ▼
MCP server (npx @modelcontextprotocol/server-fetch)
```

Your agent never talks to MCP servers directly. It talks to mcptoon. mcptoon handles the protocol, applies security checks, and returns plain text. Schemas stay on disk in `~/.mcptoon/config.json`, not in your agent's context window.

You can configure 1,000 servers. Zero will be running until you call one.

## Python API

```python
from mcptoon.client import MCPClient

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    result = c.call_tool("fetch", {"url": "https://example.com"})
```

## Docker

```bash
docker build -t mcptoon .
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --compact
```

## Project structure

```
src/mcptoon/
├── cli.py            # CLI entry + arg parsing
├── client.py         # MCPClient (stdio + HTTP transport)
├── sync.py           # Config sync to AI agents
├── health.py         # Batch health check
├── serve.py          # stdio/HTTP MCP server bridge
├── installer.py      # One-command server install from npm/pip
├── router.py         # Tool routing + security checks
├── config.py         # Server config (JSON + TOML)
├── manifest.py       # Tool discovery + cache + search
├── discover.py       # Zero-config auto-discovery
├── output.py         # TOON + compact/slim rendering
├── cache.py          # Schema cache (5-min TTL)
├── usage.py          # Local usage tracking
└── errors.py         # Error envelopes + fix suggestions
```

~6,800 lines. 513 tests. Zero third-party imports. ~250KB.

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 513 tests
```

Zero dependencies is a hard rule. New features need tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

---

<div align="center">

*mcptoon is an independent third-party MCP client. Not affiliated with Anthropic.*

</div>
