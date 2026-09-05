<!-- mcp-name: io.github.activeing123/mcptoon -->
<div align="center" markdown="1">

# mcptoon — MCP tool discovery that costs 114 tokens, not 14,113

**You added a few MCP servers and your agent got worse: slower, more forgetful, more
likely to answer the wrong question. That is not the model. Every MCP tool ships a
full JSON Schema, and your agent must read all of them before it is allowed to pick
one.**

**Fifty tools is 14,113 tokens — 11% of a 128K context window, gone before you type a
word. mcptoon sends the names instead: 114 tokens, same tools, −99.2%. At 255 tools it
is 71,929 → 581, over half your window, and on agentic usage that is $25 to $128 a
month spent reading manuals.**

*Both rows are measured configs, not extrapolations (tiktoken `cl100k_base`,
`assets/benchmark_tiktoken.json`). Your mix will differ —
[work out your own number in the browser](https://activeing123.github.io/mcptoon/tools/token-tax/),
30 seconds and nothing is uploaded; or measure it exactly with
`python scripts/bench_tokens.py` from a clone (it lives in the repo, not in the wheel).*

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/hero-powerstrip-en.svg" width="820" alt="mcptoon power strip: plug your MCP tools in once, and Claude, Cursor, Codex or any agent can use them — no hand-written config, no restarts">
</p>

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-738%20passed-brightgreen)](#for-developers)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](#mcp-spec-compatibility-2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)

[中文文档](https://github.com/activeing123/mcptoon/blob/main/README.zh-CN.md) ·
[DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) ·
[Changelog](https://github.com/activeing123/mcptoon/blob/main/CHANGELOG.md) ·
[Issues](https://github.com/activeing123/mcptoon/issues)

</div>

---

## Install once, every agent works

```bash
pip install mcptoon          # pure stdlib, 128KB wheel, zero dependencies

mcptoon quickstart           # finds the MCP servers you already configured
mcptoon demo                 # live before/after on your own machine
```

No Python wrangling? One line, script handles the rest:

```bash
curl -fsSL https://raw.githubusercontent.com/activeing123/mcptoon/main/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/activeing123/mcptoon/main/install.ps1 | iex
```

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/demo-en.gif" width="700" alt="mcptoon demo: pip install, run the one-command demo, watch the tool list collapse from a schema dump to a name index">
</p>

Windows · macOS · Linux · Python 3.10+ · Apache-2.0

---

## What it does

Every MCP tool ships with an instruction sheet: its name, what it does, every
parameter it accepts and what each of those allows. Before your agent can pick a
tool, it has to read all of them — every session, in every agent, before any work
starts. That reading is what fills up its context window and makes an agent slow and
forgetful.

| | Without mcptoon | With mcptoon |
|---|---|---|
| Finding a tool | reads every instruction sheet | reads a list of names |
| Adding a server | edit each agent's JSON, restart | `mcptoon sync`, no restart |
| Multiple agents | one config file per format | one source of truth, synced |
| Dead servers | discovered at call time | `mcptoon health`, CI exit codes |

In protocol terms: "instruction sheet" is a JSON Schema, and "list of names" is a name
index. mcptoon is a zero-dependency CLI that connects any agent to every Model Context
Protocol server — including agents that don't support MCP.

---

## It's a dial, not a switch

How much of that reading your agent does is a choice you make per call. Both columns
are measured configs, not one number scaled up and down:

| Rung | What your agent reads | 50 tools | 255 tools | What you give up |
|---|---|---:|---:|---|
| default | every tool's full JSON Schema | 14,113 | 71,929 | nothing — this is the bill you pay today |
| `--slim` | names + parameter types | 1,624 | 8,282 | descriptions and constraints |
| `--compact` | just the names | **114** | **581** | everything but the names |

The saving does not evaporate as you grow: `--slim` is −88.5% and `--compact` −99.2%, at
both sizes, measured. What
grows is the stake: 11% of a 128K window at fifty tools, 56% at two hundred and
fifty. And the listing is re-sent by every fresh agent, so at 20 listings a day and
$3 per million input tokens, the reading alone costs **$25 a month** on the small
setup and **$128** on the big one.

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/token-savings-en.svg" width="700" alt="Bar chart on one 255-tool config: raw JSON schemas 71,929 tokens, slim 8,282, compact 581">
</p>

The instruction sheets stay on disk in `~/.mcptoon/config.json`; your agent never
reads one unless it asks for it. That is the whole trick, and it is why this is not
compression: a compressor ships the full payload into the window and unpacks it
later, so the cost still lands there. mcptoon never sends it. `--json` is always
there when you want the complete schemas back.

**Need the real instruction sheets and still want them cheap?** `mcptoon serve`
returns *simplified but valid* JSON Schemas — `type`, `properties`, `required` and a
one-line description survive, so any MCP client can still call the tool correctly;
`examples`, `$ref`, `format`, `pattern` and the 500-word descriptions are stripped,
and argument validation against the **full** schema happens in mcptoon before the
call is routed. How much that saves depends on how verbose your servers' descriptions
are — measure it on your own config rather than trusting a number.

> **On the numbers.** Earlier releases of this README advertised 97%, then 99.8% at
> 123 tokens. Both were wrong: the 123 was a 30-entry truncation artifact in our own
> benchmark harness, not a full name index. The figures above are the corrected,
> reproducible ones, and they came from our own audit (commit `9760bbc`), not from a
> reader — which is why the fix ships with tests that go red if a retired figure
> reappears. If you find one we missed,
> [open an issue](https://github.com/activeing123/mcptoon/issues).

---

## Where the tokens actually go

"14,113 → 114" is one number carrying an argument. Here is what a tool listing is
physically made of, measured field by field with the same tokenizer, on a live 12-tool
cache from this machine:

| Part of a tool entry | Tokens | Share of the bill |
|---|---:|---:|
| the tool's **name** | 26 | **2.2%** |
| its human-readable description | 232 | 19.9% |
| its parameter schema (`type`, `properties`, `required`) | 635 | **54.5%** |
| JSON keys, braces, the per-tool envelope | 273 | 23.4% |
| **total** | **1,166** | 100% |

Two things fall out, and neither is what people expect.

**The name is 2.2% of the bill.** Everything an agent needs in order to *decide* which
tool to use costs it two percent. The other 97.8% is what it needs in order to *call*
one correctly — and it needs that for the one tool it picked, not for all twelve, let
alone all 255. mcptoon's whole move is to make that second part a lookup instead of a
preamble.

**The expensive part is not the prose.** Descriptions are 19.9% of the bill; the
parameter schema is 54.5%. Most of what you pay for is machine-shaped JSON —
`{"type":"string","description":…}` repeated for every argument of every tool. That is
why `--slim` still saves 88.5%: it drops the prose and keeps the skeleton, and the
skeleton was already the larger half.

This sample is small and it is ours: 12 tools, dominated by one browser server. Read the
percentages as the *shape* of the cost, not as your number. Your shape depends on how
verbosely your servers are written.

### The saving is a rate, never a flat number

Measured tokens per tool, from the same artifact as the tables above:

| Config | raw, per tool | `--compact`, per tool |
|---|---:|---:|
| 5 tools | 303.8 | 2.20 |
| 50 tools | 282.3 | 2.28 |
| 255 tools | 282.1 | 2.28 |
| live 12-tool cache | 97.2 | 3.50–4.58 |

The raw rate is remarkably stable (282 tokens per tool across both benchmark configs),
which is why the calculator defaults to it. The name-index rate is **not** constant:
2.20 on the benchmark configs, up to 4.58 on the live cache, because names vary in
length — `opencli_profile_list` costs more in an index than `echo` does. Any claim of
the form "N tokens flat" is therefore wrong; the honest form is a rate times your tool
count.

### What each rung keeps

| Rung | Kept | Dropped | 50 tools | 255 tools |
|---|---|---|---:|---:|
| default | everything | — | 14,113 | 71,929 |
| `--slim` | name, parameter names and types | descriptions, enums, constraints | 1,624 | 8,282 |
| `--compact` | names only | everything else | **114** | **581** |
| `serve` | valid JSON Schema, thinned | `examples`, `$ref`, `format`, `pattern`, long prose | depends | depends |

`serve` is last and deliberately has no number beside it. How much it saves depends
entirely on how verbose your servers' descriptions are, and we would rather print
nothing than print a figure you cannot reproduce.

### The same bill in money

Written out long, so every step is checkable:

```text
50 tools    raw 14,113 − compact 114  = 13,999 tokens saved per listing
13,999      × 20 listings/day × 30    = 8,399,400 tokens/month
8,399,400   × $3 per 1M input tokens  = $25.20 / month
255 tools   raw 71,929 − compact 581  = 71,348  →  $128.43 / month
```

Two of those inputs are yours to set: listings per day (an agent that re-spawns per task
lists its tools twenty times a day; a chat you leave open lists once) and your model's
input price. The first line is the only one that is ours, and it is measured.

> **The error bar, measured.** On a live 12-tool cache the real saving came out at
> **96.1%**, where the calculator's model estimates **97.5%** for the same config — 1.4
> points of optimism. Small setups save a little less than the model says. Large ones
> are measured directly, not modelled.

---

## The three moves

**1 · `sync` — configure once**

```bash
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon sync                 # writes native config to every detected agent
mcptoon sync --watch         # keeps them aligned as you edit
mcptoon sync --dry           # preview the writes
```

Merges rather than overwrites: servers you configured by hand stay put. Drift
detection catches edits made outside mcptoon.

**2 · `manifest` — a list of names, not a stack of manuals**

```bash
$ mcptoon manifest --compact
bsk-tools: resolve, map_list, map_get · echo: echo, add, delete_item
```

Real output, real config. Your agent gets the list of what exists; the definitions
stay on disk until it asks for one.

**3 · `serve` — one door in front of every server**

```bash
mcptoon serve                  # stdio, one agent
mcptoon serve --listen :8080   # HTTP, many agents or remote
```

Every configured server appears as one MCP endpoint, with connection pooling and
per-agent API-key isolation.

**And the part nobody else has: you never hand-edit a config file.** Native MCP
means editing a JSON file per agent, in a different shape each time —
`claude_desktop_config.json`, `.claude.json`, `.cursor/mcp.json`, and so on. mcptoon is
a program your agent already knows how to run:

```text
You:    "What tools do we have? Then fetch https://example.com and summarize."
Agent:  $ mcptoon manifest --compact
Agent:  $ mcptoon call fetch fetch '{"url":"https://example.com"}'
```

For an agent that can run a shell command that is the entire setup: no `mcpServers`
entry, no plugin API, nothing to restart. For one that cannot — Claude Desktop, any GUI
client — `mcptoon sync` writes its native JSON for you. Either way the number of config
files *you* type into is zero. mcptoon keeps its own list at `~/.mcptoon/config.json`,
and `mcptoon quickstart` fills it by scanning what is already on the machine.

That is also why mcptoon reaches where MCP cannot: shell scripts, CI pipelines, cron
jobs, aider, and terminal-only environments — anything that can execute a command.

---

## Why a CLI, not a library or a proxy

MCP assumes every capability is a *server* your agent must be configured to reach.
That single assumption is why adding one tool means editing one JSON file per agent,
in a different shape each time, and restarting all of them — and why every agent
re-pays the full schema cost before it does anything.

A command line is the one interface every agent already has. Models are trained on
billions of CLI examples; they don't need to be taught how to run `mcptoon`. And the
form factor is measurably cheaper, independent of anything mcptoon does:

- Firecrawl's benchmark: the same task cost **1,365 tokens via CLI vs 44,026 via MCP — 32×** ([source](https://www.firecrawl.dev/blog/mcp-vs-cli))
- Scalekit's benchmark: CLI **10–32× cheaper, 100% reliable vs MCP's 72%** ([source](https://www.scalekit.com/blog/mcp-vs-cli-use))

**Why not a library?** A library needs a host process that imports it, in a language
that host speaks. A CLI needs a shell — which is the one thing every agent, CI runner
and cron job already has.

**Why not a proxy?** A proxy is another service to run and point agents at. mcptoon is
zero-install-to-try and stays out of the way; when you *do* want the proxy shape,
`mcptoon serve` is that mode.

---

## Why this is a real problem (not our own claim)

Independent sources, each verified against the page it comes from:

| Source | What it actually says |
|---|---|
| [Anthropic — Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | "reduces the token usage from 150,000 tokens to 2,000 tokens — a time and cost saving of 98.7%" |
| [Firecrawl — MCP vs CLI](https://www.firecrawl.dev/blog/mcp-vs-cli) | "~200 tokens per command" via CLI vs "~44K tokens (full schema loaded upfront)" via MCP |
| [Scalekit](https://www.scalekit.com/blog/mcp-vs-cli-use) | "CLI won on every efficiency metric — 10 to 32× cheaper, 100% reliable versus MCP's 72%" |
| [MCP-Zero (arXiv:2506.01056)](https://arxiv.org/abs/2506.01056) | On-demand tool retrieval achieves near-constant cost regardless of tool count |
| [ProMCP — ACL 2026 Findings](https://doi.org/10.18653/v1/2026.findings-acl.1967) | Peer-reviewed profiling of token flows and latency costs in MCP-based agents |
| [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576) | An open MCP proposal to reduce schema redundancy — the problem is acknowledged upstream |

We are not the only ones who measured this, and the protocol's own working group is
now proposing fixes for it. mcptoon is available today, in every agent at once,
without waiting for that proposal to land.

---

## MCP spec compatibility (2026-07-28)

| Spec feature | Status |
|---|---|
| Stateless auto-negotiation | ✅ |
| Structured tool output | ✅ parsed natively |
| MRTR multi round-trip results | ✅ |
| `server/discover` probing | ✅ |
| Long-polling SSE responses | ✅ |
| Backward compatibility (2024-10-07 → 2025-11-25) | ✅ |

Spec releases are treated as a compatibility matrix, not a changelog: each one lands
with wire-level tests against a real server. See
[DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md).

## Agent Plugins 1.0.0

Scan, install and sync the cross-vendor plugin standard (Amazon / Cursor / Microsoft /
OpenAI / Vercel) into every agent with `mcptoon plugin install <dir>` — including
agents with no native plugin loader.

## Security, applied to every call

MCP servers run code on your machine and return arbitrary text into your agent's
context. mcptoon inspects every result before it gets there:

| Check | Blocks |
|---|---|
| Prompt injection | `"ignore previous instructions"` buried in tool output |
| Credential leak | `sk-…`, `AKIA…`, `ghp_…` patterns in tool output |
| Dangerous operations | `delete` / `drop` / `purge` tools unless you pass `--destructive` |

Zero dependencies is part of the security story: no npm subtree, no postinstall
scripts, nothing to audit but 11,400 lines of readable Python. No telemetry, no
analytics, no phone-home. API keys pass through from your config or environment and
are never stored by mcptoon.

## Works with

**Claude Desktop · Claude Code · Cursor · Cline · Windsurf · VS Code Copilot · Codex ·
Gemini CLI · OpenCode** — plus aider, shell scripts, CI jobs and anything else that
executes commands, including environments with no MCP support at all.

That last clause is the point: being a CLI first is what lets mcptoon work where an
MCP client cannot.

<details markdown="1">
<summary><strong>How is this different from per-agent configs or a tool-search proxy?</strong></summary>

| | Per-agent configs | Tool-search proxies | mcptoon |
|---|---|---|---|
| Agent-side setup | edit JSON per agent + restart | run a service, point agents at it | **none — it is just a command** |
| Files to maintain | one per agent | one per agent | **one, synced everywhere** |
| Discovery cost | full schemas | search first, load on demand | **name index; schemas never leave disk** |
| Dead-server detection | — | varies | built-in, CI-friendly exit codes |
| Output inspection | — | varies | injection + leak checks on every call |
| To adopt | native support | run a service | `pip install mcptoon` |

They also compose: `serve` mode gives you the proxy shape when you want it.

</details>

## Questions worth asking

### Isn't this just compression?
No. Compression ships the full payload into the context and unpacks it later, so the
cost still lands in the window. mcptoon never sends the schemas: they stay on disk, and
`--json` returns any one of them on demand.

### Doesn't Claude Code already defer tool loading?
Yes, and the two stack. Deferred loading decides *when* a definition loads, in one
agent. mcptoon decides how much a listing *costs*, in every agent at once, and adds
sync, health checks and output inspection on top.

### Is the 99.2% a formatting trick?
No `null` → `∅` substitutions. That misconception came from earlier TOON-style
experiments, and those substitutions were removed in v0.3.0 after tiktoken proved two
of them cost more than they saved. Optional `--toon` encoding of tool *results* saves a
further ~34% and is off by default.

### Why not just use fewer MCP servers?
That is the trade MCP users make today: uninstall one to buy back room, reinstall it
the week you need it. It works, and it is why the 50-tool column above matters more
than the 255 one. mcptoon is what lets you keep all of them and still have a window
left to work in.

### Do I have to give it my API keys?
No account, no telemetry, no phone-home. Keys pass through from your own config or
environment and mcptoon never stores them. There is also very little to hide in: 11,400
lines of stdlib Python, and zero third-party imports enforced at review.

### What do I actually give up?
At `--compact`, everything except tool names — your agent asks for a schema before it
builds an argument. At `--slim`, descriptions and constraints. Both are per-call flags
on one command, so this is a dial you set per agent, not a migration.

### How is this different from McpHub or another MCP gateway?
A gateway is a service you run and then point your agents at. [mcphub](https://github.com/samanhappy/mcphub),
for example, keeps its own server list, serves it at `http://localhost:3000/mcp` (with
`/mcp/{group}` and `/mcp/{server}` routes), and each agent gets a config entry pointing
there. That is the right shape when a team wants one audited door. mcptoon has no door
to point at: an agent that can run a shell command calls `mcptoon call <server.tool>`
directly, so there is no service to keep up and no per-agent entry to add. The token
bill differs for the same reason — a gateway aggregates servers behind one endpoint, and
the agent still receives the combined `tools/list` from it. Aggregating does not shrink
a listing; only refusing to send it does.

### So do you have a config file, or not?
You do: `~/.mcptoon/config.json`. It is written by scanning what the machine already has
— `mcptoon quickstart` reads Claude Desktop, Cursor, Cline and Windsurf configs, plus
environment variables and local tools — not by you. And for agents that cannot run a
shell command, `mcptoon sync` writes their native JSON. The claim this README makes is
"you never hand-edit a config file", which survives `ls ~/.mcptoon`. "No config file"
would not, so it is not claimed.

<details markdown="1">
<summary><strong>Honest limitations</strong></summary>

- `--compact` lists tool **names only** — no descriptions or parameter details. Use
  `--slim` for signatures, `--json` for everything.
- Token counts were measured with tiktoken `cl100k_base`. Other tokenizers differ
  (±10–25%); the main saving — schemas not entering context — is tokenizer-independent.
- Percentages depend on your toolset — small configs amortise worse. On a 12-tool
  config we measure −96.1%, not −99.2%.
- Each stdio call spawns a process (~300 ms cold). Hot paths should use `serve` mode.
- Terminal-first. There is no GUI.

</details>

---

## For developers

```python
from mcptoon.client import MCPClient

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    result = c.call_tool("fetch", {"url": "https://example.com"})
```

```bash
git clone https://github.com/activeing123/mcptoon.git && cd mcptoon
pip install -e . --no-build-isolation && pip install pytest
python -m pytest tests/ -v          # 738 passed, 1 skipped
```

Zero third-party imports is a hard rule enforced in review; new behavior ships with
tests. 11,400 lines of Python across 21 modules — see
[CONTRIBUTING.md](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md).

## License

Apache 2.0 — see [LICENSE](https://github.com/activeing123/mcptoon/blob/main/LICENSE)
and [NOTICE](https://github.com/activeing123/mcptoon/blob/main/NOTICE).

<div align="center" markdown="1">

*Independent third-party client for the Model Context Protocol. Not affiliated with Anthropic, Cursor, or Microsoft.*

**Skeptical? Good. `pip install mcptoon && mcptoon demo` takes 30 seconds and runs on your machine.**

<sub>A ⭐ is how the next person finds this README.</sub>

</div>
