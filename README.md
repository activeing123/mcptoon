<!-- mcp-name: io.github.activeing123/mcptoon -->
<div align="center" markdown="1">

# mcptoon

**Add 1,000 MCP tools locally — your token context never feels it.**

mcptoon is a 128KB CLI that keeps MCP tool schemas out of your agent's context.
Tool discovery drops **71,929 → 581 tokens at 255 tools (−99.2%, measured)**; call
results shrink another ~34% with `--toon`. One command per server, zero config,
and every agent on your machine shares the same toolkit.

[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon/stargazers)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-790%20passed-brightgreen)](#contributing)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)

**👉 [中文](https://github.com/activeing123/mcptoon/blob/main/README.zh-CN.md) · [Developer docs](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) · [Issues](https://github.com/activeing123/mcptoon/issues)**

![Benchmark: 255 tools, 71,929 → 581 tokens](https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/benchmark.svg)

![Token savings at a glance](https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/token-savings-en.svg)

</div>

```bash
pip install mcptoon

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# What your agent actually reads (names only — 581 tokens, not 71,929):
mcptoon manifest
```

**Your tools stay yours.** mcptoon bundles nothing — it's a remote control, not a
runtime. The MCP servers you want, you install yourself, one command each
(npm/pip/a URL). Delete mcptoon someday? Your MCP servers keep running on their own —
not one goes missing.

**Mcptoon is the native decoupling layer for MCP tools.** It fixes the twin pain of
MCP tool listings eating tokens and every AI agent re-configuring tools on its own.
Zero config, out of the box: it auto-scans and unifies the MCP tools of every agent
on this machine — Claude Code, Cursor, Codex, scripts, CI — shares tool instances
globally, and slashes token overhead.

</div>

---

## This isn't just us talking

Those numbers are ours, but "loading every tool schema into context is expensive" is
not a claim only we make:

- [Anthropic](https://www.anthropic.com/engineering/code-execution-with-mcp): tool
  schemas flooding the context window is a real pain — one example drops from 150,000
  tokens to 2,000 (a 98.7% saving)
- [Firecrawl benchmark](https://www.firecrawl.dev/blog/mcp-vs-cli): the same task cost
  1,365 tokens via CLI vs 44,026 via MCP — 32× (full schema loaded upfront)
- [Scalekit benchmark](https://www.scalekit.com/blog/mcp-vs-cli-use): CLI is 10–32×
  cheaper and 100% reliable; MCP scores 72%
- [MCP-Zero (arXiv:2506.01056)](https://arxiv.org/abs/2506.01056): on-demand tool
  retrieval achieves near-constant cost regardless of tool count
- [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576):
  an open MCP proposal to cut schema redundancy — the problem is acknowledged upstream

We're not the only ones who measured this. mcptoon is the one you can use today,
covering every agent at once.

---

## Up and running in 30 seconds

```bash
pip install mcptoon                          # pure stdlib, 128KB, zero dependencies

# Add any MCP server — one command:
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# See every tool available (names-only by default; 255 tools cost 581 tokens):
mcptoon manifest

# Call a tool (JSON output by default; add --toon to save more):
mcptoon call fetch fetch '{"url":"https://example.com"}'
```

Claude Code user? Skip the terminal entirely:

```bash
/plugin marketplace add activeing123/mcptoon
```

The plugin auto-installs the CLI (SessionStart hook), wires the `mcptoon
serve` bridge via `.mcp.json`, and ships a skill that teaches the agent when
to compress. `/mcptoon-setup` is the manual fallback.

**Or let mcptoon auto-discover servers already on your machine:**

```bash
mcptoon quickstart     # discover + configure + list tools — one command
```

That's it. No hand-written JSON config. No MCP protocol debugging. No polluted context
window. The wheel is 128KB with zero dependencies, and mcptoon itself needs no API
key and phones nothing home — $0 in service fees, everything runs on your machine.

---

## The problem

Every MCP agent (Claude Code, Cursor, Codex, …) stuffs **every tool's full schema into
your context window** before doing any work:

```
50 tools  → 14,113 tokens of schema → a 128K context: 11% gone
255 tools → 71,929 tokens of schema → a 128K context: 56% gone
```

So you unload servers you aren't using and reload them when you are. Back and forth.
Adding one new server still means hand-writing a JSON config — one missing comma and
everything breaks.

**mcptoon fixes this.** Your MCP servers stay configured, but their schemas **never
enter the agent's context by default**. The agent just runs `mcptoon` commands, and
only the compact result you asked for enters context — the name index weighs 581
tokens (114 for 50 tools, −99.2%).

```
Without mcptoon: 255 tools → 71,929 tokens, over half the window
With mcptoon:    255 tools → 581 tokens. 99.2% saved.
```

*Both rows are measured configurations, not one number scaled up and down (tiktoken
`cl100k_base`, `assets/benchmark_tiktoken.json`). Your mix will differ —
[compute your own numbers in the browser](https://activeing123.github.io/mcptoon/tools/token-tax/),
30 seconds, nothing uploaded.*

---

## The industry validated the problem — then gated the fix

Token-heavy tool context is no longer a niche complaint — it is now an official
engineering problem, and the same answer keeps appearing on every roadmap:

- **Anthropic**: [Tool Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
  defers tool definitions until needed; [Programmatic Tool Calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
  moves orchestration into code. Both are Claude-platform betas.
- **MuleSoft**: [MCP Payload Optimization](https://docs.mulesoft.com/gateway/latest/policies-included-mcp-payload-optimization)
  productizes clean → distill → compress (its compression stage is TOON).
  Enterprise gateway only, MCP up to 2025-06-18.

| The fix | Where it runs | The catch |
|---|---|---|
| Tool Search Tool / PTC | Claude-platform betas | tool *results* still enter context token by token on every other agent |
| MuleSoft gateway | enterprise gateway | behind MuleSoft; MCP spec one generation behind |
| **mcptoon** | **any agent that can run a shell command** | none — 128KB, no key, no proxy, MCP 2026-07-28 GA |

The direction is settled. mcptoon is the version of this answer you can run
**today, on every agent at once** — the results-side discipline without the
platform or gateway toll.

---

## Installing MCP servers — one command each

```bash
# Install from npm (most MCP servers live here):
mcptoon install brave-search --npm @modelcontextprotocol/server-brave-search

# Install from pip:
mcptoon install my-tool --pip mcp-my-tool

# HTTP/SSE servers:
mcptoon install remote-api --url https://example.com/mcp

# List installed:
mcptoon install --list

# Uninstall:
mcptoon install --remove brave-search
```

mcptoon connects, discovers tools, generates the handler, registers it. No restart
needed. Each install adds **0 KB to mcptoon itself** — the CLI stays 128KB with zero
dependencies, because servers are external processes your machine runs directly, not
code bundled into mcptoon. Four steps, one command, no agent restart.

**Any MCP server works:**

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest    # usable immediately
```

---

## Prefer a GUI? ToonDeck

Don't want to hand-edit configs? **[ToonDeck](https://github.com/activeing123/toondeck)**
is a local console for mcptoon: every MCP server and tool in one place with a
real health check, one skill folder synced to all your agents, agent launching
with live logs, and API keys stored in your OS keychain — never in a plaintext
file.

```bash
pip install toondeck    # ships the web UI inside the wheel — no node, no build
```

Pre-alpha; free (Apache-2.0). ToonDeck drives the engine — mcptoon stays the
single source of truth underneath.

---

## Works with every AI agent

mcptoon is a CLI. **If your agent can run a shell command, it can use mcptoon.** No
plugins, no SDK, no per-agent setup.

| Agent | How |
|---|---|
| **Claude Code** | put `mcptoon` commands in SKILL.md |
| **Codex (OpenAI)** | add `mcptoon` to AGENTS.md |
| **Cursor** | add `mcptoon` to .cursorrules |
| **OpenCode** | use `mcptoon` in custom commands |
| **Any agent** | can run shell commands → can call `mcptoon` |

Configure once in `~/.mcptoon/config.json`; every agent that can run shell commands
shares the same servers and tools. GUI agents that can't? `mcptoon sync` writes native
JSON into each one's own location.

```bash
export MCPTOON_AGENT_TYPE=claude   # call results auto-select --toon
# export MCPTOON_AGENT_TYPE=openai   # or keep the default JSON
```

Your AI can even add tools by itself — no human in the loop:

```bash
# Agent needs GitHub access mid-task? It just runs:
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon call github search_repos '{"query":"mcp"}'
# Done. No JSON editing. No restart. No lost context.
```

---

## The numbers

mcptoon's token savings are two separate bills — know which one you're reading before
comparing numbers. The short version: at 255 tools, native discovery costs 71,929
tokens — over half of a 128K context — while the same toolset reads back at 581
tokens through the name index, a 99.2% cut. On the results side, `--toon` saves
34.0–34.2% versus JSON across the measured set. Both rows are measured
configurations (tiktoken `cl100k_base`, `assets/benchmark_tiktoken.json`), not
scaled estimates.

### Bill 1 · Tool discovery (`manifest`): 99.2% saved by default

This bill comes due **before your agent decides "which tool do I use"**. Native MCP
shoves every tool's full schema into context (50 tools: 14,113 tokens; 255 tools:
71,929 tokens). mcptoon sends only the name index — that's where "114, not 14,113"
comes from.

| Tools | Native schema (JSON) | mcptoon name index (default) | Saved |
|-------|-------------------|------------------------|-------:|
| 5 | 1,519 | 11 | −99.3% |
| 50 | 14,113 | **114** | **−99.2%** |
| 255 | 71,929 | **581** | **−99.2%** |

Zero action, on by default: `mcptoon manifest` with no flags is this tier.
Want to give the agent more? `--full` (names + parameter types) saves 88.5%;
`--json` (full schema) is the baseline.

*We measured both rows ourselves — not one number scaled up and down (tiktoken
`cl100k_base`, `assets/benchmark_tiktoken.json`). Your mix will differ —
[compute your own numbers in the browser](https://activeing123.github.io/mcptoon/tools/token-tax/),
30 seconds, nothing uploaded.*

### Bill 2 · Call results (`call`): optional, --toon saves ~34%

This bill comes due **after a tool returns its result to your agent**. `mcptoon call`
outputs JSON by default — yes, the default saves nothing. To shrink results too, add
`--toon` (structured encoding, reversible):

```
Default:  mcptoon call fetch fetch '{"url":"https://example.com"}'   → JSON (baseline)
Leaner:   mcptoon call fetch fetch '{"url":"https://example.com"}' --toon   → ~34% saved
```

34% is the measured `toon_save` value in `assets/benchmark_tiktoken.json`
(34.0–34.2%), not a marketing number.

**One line to remember: 99.2% is what you save seeing which tools exist; 34% is what
you can further save on results.**

### Side-by-side (Bill 1, made visible)

One tool's schema costs **37 tokens** as native JSON but only **2 tokens** as an
mcptoon name-index entry — a 95% cut on a single tool. We measured it with tiktoken
(`cl100k_base`).

**Without mcptoon** (what every MCP client stuffs into context — 37 tokens, measured
with tiktoken):

```json
[{"name":"search_web","description":"Search the web for information",
"inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"Search query"}}}}]
```

**With mcptoon** (2 tokens):

```
search_web
```

**With mcptoon --full** (6 tokens, parameter info included):

```
search_web|query:s*
```

---

## Security

Three layers, all built in:

| Layer | What it does | Example |
|-------|-------------|---------|
| **Destructive-action block** | dangerous actions blocked unless you pass `--destructive` | `db query '{"sql":"DROP TABLE users"}'` → blocked |
| **Prompt-injection guard** | scans results for injection patterns | `"ignore previous instructions"` → blocked |
| **Credential-leak detection** | scans results for exposed keys/tokens | `sk-abc...xyz` → blocked, never enters agent context |

- **No telemetry.** No analytics, no crash reports, no call-home.
- **No stored credentials.** API keys pass straight from your config or environment.
- **No dependencies.** Pure Python standard library. Nothing in the supply chain to audit.
- **No daemon.** Pure CLI — no resident process, no listening port, no attack surface.

---

## All commands

```bash
mcptoon quickstart              # one-shot start (discover + configure + list tools)
mcptoon list                    # show configured servers
mcptoon manifest                # all tool names (compact by default; 255 tools = 581 tokens)
mcptoon manifest --full         # tool schemas with params (88.5% smaller than native)
mcptoon inspect <server> <tool> # inspect one tool's schema
mcptoon search <query>          # search tools across servers
mcptoon call <server> <tool> '{"args":"here"}'   # call a tool
mcptoon call --auto <tool> '{"args":"here"}'     # auto-find the server
mcptoon call <server> <tool> --stdin             # read large args from stdin
mcptoon add <name> --stdio|--http <cmd|url>     # add any MCP server
mcptoon remove <name>           # remove a server
mcptoon install <name> --npm|--pip|--url <pkg>  # install + auto-generate handler
mcptoon install --list          # list installed
mcptoon install --remove <name> # uninstall
mcptoon sync                    # sync native config to every detected agent
mcptoon plugin install <dir>    # install an Agent Plugins 1.0.0 plugin
mcptoon serve                   # run as an MCP server (stdio/HTTP) — MCP 2026-07-28: stateless-first, server/discover, cacheable list results
mcptoon demo                    # one command, live demo on your machine
mcptoon doctor                  # self-check: Python, config, connectivity
mcptoon usage                   # local call statistics
mcptoon completion ps           # shell completion (bash/zsh/fish/powershell)
```

### Format family: four tiers, compact by default

Discovery and call results each have a set of formats — all optional, and the default
is already the leanest tier:

**manifest (discovery): compact by default, upgrade only if you want more**

| Tier | Output | vs native schema | Origin |
|---|---|---|---|
| **compact (default)** | names only `search_web` | **99.2% smaller** | common design |
| **slim** | name + param types `search_web\|query:s*` | 88.5% smaller | **mcptoon original** |
| **full** | full schema with params | baseline | native MCP |

**Why compact by default, not full?** Deciding "which tool do I use" only needs names
(581 tokens for 255 tools); parameter details matter at call time, fetched on demand
via `inspect` or `manifest --full`. Defaulting to full schemas hands the 99.2% right
back.

**call (results): JSON by default, --toon to save**

| Tier | Output | vs JSON | Origin |
|---|---|---|---|
| **(default)** | JSON | baseline | common |
| **--toon** | structured encoding (reversible) | ~34% smaller | open TOON standard |
| **--mcptoon** | legacy pipe format | — | mcptoon original (legacy) |

**Where these formats come from**

- **compact**: a name list — any tool manager can do it; nothing proprietary.
- **slim** (`name|param:type*` signatures): **an mcptoon original**, implemented in
  `output.py` (`slim_toon`, Apache 2.0); noted in NOTICE.
- **full**: full JSON Schema — what MCP speaks natively.
- **toon** (result encoding): integration of the open **TOON standard**
  ([toon-format/toon](https://github.com/toon-format/toon) v4.1, MIT), vendored from
  python-toon and credited in NOTICE — not our invention, and we don't claim it.

---

## Do custom formats break MCP compatibility? — No, for three reasons

"Proprietary format = compatibility bomb" is a fair worry. It doesn't apply here:

**1 · The protocol layer is always standard JSON-RPC; formats live only in the
presentation layer.**
mcptoon speaks standard MCP to servers (initialize / tools/list / tools/call —
and since the 2026-07-28 GA bridge, `server/discover` and stateless requests
too; the initialize handshake remains for legacy clients).
compact/slim/toon only affect the "mcptoon → agent" output rendering — not a single
byte toward the server. Servers always see standard JSON; they don't even know these
formats exist.

**2 · --toon isn't proprietary; it's an open standard.**
TOON (Token-Oriented Object Notation) is an external open standard
([toon-format/toon](https://github.com/toon-format/toon) v4.1, MIT, official
TypeScript reference implementation). We integrate python-toon (MIT);
`tests/test_toon_cross_validate.py` verifies `decode(encode(x)) == x` case by case.

**3 · There's a fallback; worst case you fall back to JSON.**
If `--toon` decoding fails it falls back to JSON automatically (`--fallback-json`);
and call results are JSON by default anyway — `--toon` is optional. Want the full
schema back? One `--full` is native MCP. No lock-in.

**In one line: zero protocol changes, formats live in the output layer, worst case
falls back to JSON.** The feared "server can't understand the custom format" can't
happen — servers always hear standard JSON-RPC.

---

## How it works

mcptoon is a **CLI tool**, not an MCP client library. Your agent doesn't connect to
MCP servers — it runs `mcptoon` commands. Schemas live on disk in
`~/.mcptoon/config.json`, out of the context window by default.

**Two-layer decoupling:**

```
Layer 1: mcptoon CLI (128KB, zero deps)
         runs in the agent's shell. schemas stay out of context by default.
                    │
Layer 2: the actual MCP servers (npm/pip packages)
         start only when a tool is called. Zero cost when idle.
```

- 1,000 servers configured → 0 running, until you call one
- mcptoon bundles nothing — you add what you want, one command each
- Delete mcptoon? Your MCP servers keep running independently

---

## Why a CLI, not a proxy

MCP's premise: every capability is a *server*, and your agent must be configured to
reach it. That premise is why one new tool means editing per-agent JSON in a different
format for each, restarting everything — and why every agent re-pays the full schema
cost before doing anything.

A command line is the one interface every agent already has. And the form factor is
measurably cheaper, independent of anything mcptoon does:

- Firecrawl's benchmark: the same task cost **1,365 tokens via CLI vs 44,026 via MCP — 32×**
- Scalekit's benchmark: CLI **10–32× cheaper, 100% reliable vs MCP's 72%**

If you truly need the proxy form, `mcptoon serve` is that mode — all configured
servers behind one MCP endpoint, with connection pooling and per-agent API keys.

---

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 790 passed, 1 skipped
```

Zero dependencies is a hard rule — our test suite gates every change (790 tests
green before merge). See
[CONTRIBUTING.md](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md) and [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md).

The codebase: 11,750 lines of Python across 21 modules, zero third-party dependencies.

---

<div align="center">

*mcptoon is an independent third-party MCP client, not affiliated with Anthropic.*

**If mcptoon cut your context bill, star it — that's how other builders find small tools.**

</div>
