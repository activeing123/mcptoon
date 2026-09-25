<!-- mcp-name: io.github.activeing123/mcptoon -->
<div align="center" markdown="1">

# mcptoon

**Install 1,000 skills and 1,000 MCP tools locally — and don't worry about the token context. mcptoon manages it all.**

**Its own compact format saves 99.2% of tokens; no line of config to write for any desktop or command-line agent.**

**Connects to a 17,000+ MCP tool registry and searches skills on demand — nothing pre-installed, you pick what goes in.**

**It's just a 227KB native CLI — delete it anytime; keep it, and you never have to configure tools or skills for any agent again.**

[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon/stargazers)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-1445%20passed-brightgreen)](#contributing)
[![Manages](https://img.shields.io/badge/manages-MCP%20tools%20%2B%20agent%20skills-8250df)](#what-it-does)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)
[![AllMCPs](https://allmcps.com/api/badge/mcptoon?style=directory)](https://allmcps.com/mcp/mcptoon?verify=7eb0d0d6-5d4e-41a3-a048-2fe3c91a36ed)
[![MCPVault: verified](https://mcpvault.io/badge/mcptoon.svg)](https://mcpvault.io/servers/mcptoon/health)
[![mcptoon on AI Agents Listing](https://aiagentslisting.com/mcptoon/badge.svg)](https://aiagentslisting.com/mcp/mcptoon)
[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/activeing123/mcptoon)

**👉 See it first: [landing page](https://activeing123.github.io/mcptoon/) · [30-second token calculator](https://activeing123.github.io/mcptoon/tools/token-tax/) · [中文](https://github.com/activeing123/mcptoon/blob/main/README.zh-CN.md)**

**👉 Or run it: `pip install mcptoon && mcptoon bench`** — it measures what your own tools and skills cost, on your machine.

**👉 [Developer docs](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) · [Contributing](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md) · [Issues](https://github.com/activeing123/mcptoon/issues)**

![Benchmark: 255 tools, 71,929 → 581 tokens](https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/benchmark.svg)

</div>

## Why mcptoon

Every MCP agent (Claude Code, Cursor, Codex, …) loads **the full description of every tool and every skill into its context window before it does any work** — and re-sends it every turn. On 255 tools that is **71,929 tokens**: more than half of a 128K window spent on descriptions, before the first question.

## How the token saving works

mcptoon keeps those descriptions **on disk, not in context**, and hands the agent a compact view instead:

- **A name index, not full schemas.** Picking a tool only needs its name — 255 tools become **581 tokens (−99.2%)**. The full schema is fetched on demand with `mcptoon inspect`, only when a tool is actually called.
- **Skills the same way.** One resident pointer (**39 tokens**) plus one lookup (**501 tokens**) replaces loading every `SKILL.md` in full — **926,232 → 39 + 501 (−99.9%)**.
- **Results too.** `--toon` encodes a tool's *result* **~34%** smaller than JSON.

Nothing is lost: the full schema and the full skill text stay one command away. Only the context window is spared.

mcptoon is a **227KB, zero-dependency native CLI** that manages every MCP tool and agent skill on your computer — and shares them across all your agents with no config written by you.

## This isn't just us talking

Those numbers are ours — but "loading every tool schema into context is expensive" is not
a claim only we make:

- **[Anthropic's engineering write-up](https://www.anthropic.com/engineering/code-execution-with-mcp)** — tool schemas flooding the context window is a real cost; one example drops from 150,000 tokens to 2,000
- **[Firecrawl's benchmark](https://firecrawl.dev/blog/mcp-vs-cli)** — the same task cost 1,365 tokens via CLI vs 44,026 via MCP (32×)
- **[Scalekit's benchmark](https://scalekit.com/blog/mcp-vs-cli-use)** — CLI 10–32× cheaper, 100% reliable vs MCP's 72%
- **[MCP-Zero (arXiv:2506.01056)](https://arxiv.org/abs/2506.01056)** — on-demand tool retrieval, near-constant cost regardless of tool count

mcptoon is the one you can use today, covering every agent at once.

---

## Two ways in

<table>
<tr>
<td width="50%" valign="top">

<h3>🧑‍💻 I just use AI tools</h3>

Install once, and every desktop AI you have — **Claude Desktop, Claude Code, Codex, Cursor, Windsurf, Cline, VS Code Copilot and any other agent** — shares all the tools and skills you already have. You write nothing in any agent's config.

**[→ Install and go](#30-seconds-up-and-running)**

</td>
<td width="50%" valign="top">

<h3>🔧 I build with MCP / agents</h3>

Script it. `mcptoon` is a plain CLI with stable JSON output and an `mcptoon serve` MCP endpoint — wire it into your own agent, CI, or app.

**[→ Commands and formats](#all-commands)**

</td>
</tr>
</table>

Reproduce the numbers yourself: `pip install mcptoon && mcptoon bench`

| | Without mcptoon | With mcptoon |
|---|---|---|
| **Descriptions in context** | full description of every tool + skill, re-sent every turn | a compact view — **581 tokens** for 255 tools (−99.2%, lossless) |
| **Adding a tool or skill** | hand-write JSON in every agent | one command — no agent config touched |
| **Which agents get it** | only the ones you configured | every agent on the machine — they just run `mcptoon` |
| **Finding tools & skills** | hunt GitHub by hand | `install --search` (**17,000+ MCP servers**) + `skills search` |
| **Starting from scratch** | wire tools one by one | 4 built-in starter packs — one command to a working set |

Skills work the same way: **926,232 tokens** of `SKILL.md` text → **39** resident + **501** per lookup (−99.9%). Call results shrink another **~34%** with `--toon`.

---

## Path 1 · I just use AI tools

You have a desktop AI — Claude, Codex, Cursor, Windsurf, Cline, VS Code Copilot. Today, adding a tool or a skill means hand-editing that agent's JSON. mcptoon removes that step:

1. **Install once.**
   ```bash
   pip install mcptoon && mcptoon quickstart
   ```
   `quickstart` finds your MCP servers, writes your config, and registers mcptoon in every agent it detects.
   (Skip `quickstart` and the first command you run still self-heals: it installs
   mcptoon's own skill into each agent and builds the skill index, once per machine.)

2. **Add tools and skills in one place** — here, not in each agent.
   ```bash
   mcptoon install --search github     # find and install any MCP server
   mcptoon skills search "make a PDF"  # find a skill by what it does
   ```

3. **Use them from any agent.** Your agent runs `mcptoon` like any other command — no config, no restart. See [Works with every AI agent](#works-with-every-ai-agent).

**Want a head start?** Four built-in starter packs — `essentials`, `web-research`, `code-review`, `docs` — stand up a working toolset in one command:

```bash
mcptoon install --pack essentials
```

---

## Path 2 · I build with MCP / agents

mcptoon is a plain CLI with scriptable output, plus an MCP endpoint when you want one.

```bash
mcptoon manifest --format json      # machine-readable tool index
mcptoon call <server> <tool> '{}'   # call any tool, JSON or --toon output
mcptoon serve                       # expose every configured server behind one MCP endpoint
```

- **Stable output** — JSON by default, `--toon` for ~34% smaller results, `--format mcp` to export standard MCP JSON.
- **`mcptoon serve`** — stdio or HTTP, connection pooling, per-agent keys, for clients that insist on a proxy.
- **Zero dependencies** — pure Python standard library, so it drops into any environment (CI, containers, air-gapped).

Full reference: [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) and [All commands](#all-commands).

---

## Contents

- [Why mcptoon](#why-mcptoon)
- [How the token saving works](#how-the-token-saving-works)
- [This isn't just us talking](#this-isnt-just-us-talking)
- [Two ways in](#two-ways-in)
- [30 seconds up and running](#30-seconds-up-and-running)
- [What it does](#what-it-does)
- [Where the tools come from](#where-the-tools-come-from--search-17000-install-with-one-command)
- [The three bills](#the-three-bills-and-why-you-must-not-mix-them)
- [Install](#install)
- [Works with every AI agent](#works-with-every-ai-agent)
- [Why a CLI, not a proxy](#why-a-cli-not-a-proxy)
- [All commands](#all-commands)
- [Trust and safety](#trust-and-safety)
- [Credits and references](#credits-and-references)
- [Contributing](#contributing)
- [License](#license)

---

## 30 seconds up and running

```bash
pip install mcptoon                          # pure stdlib, 227KB, zero dependencies

# One command: find your MCP servers, write your config, register the gateway
# in every agent you have, and show you what it found:
mcptoon quickstart

# See every tool available (names-only by default; 255 tools cost 581 tokens):
mcptoon manifest

# Call a tool (JSON output by default; add --toon to save more):
mcptoon call everything echo '{"message":"hi"}'
```

`quickstart` is also what makes mcptoon *visible*: it writes `mcptoon serve` into each
agent's config as the reserved server `mcptoon`, so your agent can see mcptoon itself.
Already synced? Re-register with `mcptoon sync --self` (plain `mcptoon sync` only writes
your servers); check the state any time with `mcptoon status`.

**And it is fully reversible.** `mcptoon sync --self` adds a single entry to an agent's
config — nothing else is touched. Take it back any time with `mcptoon off` (your own
servers stay as they are, and every changed file keeps a `.bak`); preview the complete
removal plan with `mcptoon uninstall --dry`. Your server definitions stay put, and
`uninstall` prints exactly what it will remove before it removes it.

Don't want to install yet? Watch it work instead (needs Node):

```bash
uvx mcptoon demo --quick
```

It boots the official "everything" reference server, calls one tool, and prints the token
math on your screen — no API key, none of your servers, nothing written to disk.

---

## What it does

### Tools: schema on demand

The full schema is compressed to a name index. When you need one, `mcptoon inspect`
fetches its real parameters, then `call` runs it. You pay for a listing, not for every
turn.

### Skills: one resident pointer

No more loading the whole catalog. A single pointer line stays resident (39 tokens) and
one lookup returns the most relevant skills (501 tokens). Views are **links** (a junction
on Windows, no admin needed), so one edit at the source is live everywhere and there is no
second copy to drift.

### Install once, share everywhere

Install mcptoon once and every AI on the machine gets all your tools and skills. Add more
later and it is live immediately — no agent restart, no per-agent JSON.

### Add tools your way

```bash
mcptoon install brave-search --npm @modelcontextprotocol/server-brave-search
mcptoon install my-tool --pip mcp-my-tool
mcptoon install remote-api --url https://example.com/mcp
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon install --list                       # see what's installed
mcptoon install --remove brave-search        # uninstall one
```

One command per server, from npm / pip / HTTP. Or let mcptoon scan what you already have:
`mcptoon discover`.

---

## Where the tools come from — search 17,000+, install with one command

On a new machine the first question isn't "how do I save tokens", it's "which tools do I
even want". The old answer is to hunt GitHub for `mcpServers` snippets and hand-copy them
into JSON.

mcptoon **ships no tools and bundles no catalog**. It queries the upstream registries, so
you search for exactly what you need:

```bash
mcptoon install --search github     # search, list only — nothing installed
mcptoon install --search postgres
mcptoon install github              # search and install
```

Results carry a `✓` (registry-verified), a type tag (`npm` / `pypi` / `hosted` / `remote`)
and a call count. Data comes from two upstreams, queried live and never stored:

| Source | What it is | Scale |
|---|---|---|
| [Smithery](https://smithery.ai) | the largest MCP registry | **17,000+** entries |
| [Official MCP Registry](https://registry.modelcontextprotocol.io) | the official meta-registry | installable npm / pypi packages |

**Why nothing is bundled:** a built-in list would need a release to update and would pull
someone else's source into your supply chain. mcptoon stores only a **pointer** — the
search writes one line into your own `~/.mcptoon/config.json`; third-party source never
lands inside mcptoon.

Then distribute to every agent:

```bash
mcptoon sync          # push the new tools to every detected agent
mcptoon manifest      # see every tool (name index, the cheapest view)
```

**How to read a result:** the index mixes official `@modelcontextprotocol/*` servers with packages individuals publish. A `✓` means the registry verified the entry — your cue to read the source before you hand it credentials.

**The skills half:** `skills search <query>` queries the open skills index (skills.sh) — find a skill by what it does, then install it with `skills add <git-url>`. mcptoon installs the repos **you point it at** — the catalog is the open ecosystem itself.

**Starter packs:** if you'd rather not pick tool-by-tool, four built-in packs — `essentials`, `web-research`, `code-review`, `docs` — each bundle a few tools plus a ready-made prompt. `mcptoon install --packs` lists them; `mcptoon install --pack essentials` installs one. The two research packs need no API key.

---

## The three bills, and why you must not mix them

mcptoon saves tokens in three separate places. Comparing the numbers across them is
meaningless.

### Bill 1 · Tool discovery (`manifest`): 99.2% smaller by default

`mcptoon manifest` with no flags is this tier. Want more? `--slim` (names plus param
types, 8,282 tokens, −88.5%) or `--full` (the complete schema).

### Bill 2 · Call results (`call`): optional, `--toon` saves ~34%

This bill comes due *after* a tool returns. `mcptoon call` prints JSON by default and
**saves nothing by default**. Add `--toon` to shrink the result.

### Bill 3 · Skill catalog (`skills`): 926,232 → 39 resident + 501 per lookup

```bash
mcptoon skills manifest                      # 39 tokens, resident
mcptoon skills resolve "make a PDF" --k 5    # 501 tokens, the 5 most relevant
```

**One table, all three, on the machine this README was written on:**

| Path | What the agent loads | Tokens | vs native |
|---|---|---:|---:|
| Tool schemas (1109) | every full schema | 139,863 | — |
| | `manifest` (name index) | 5,406 | 96.1% |
| | `manifest --slim` | 16,396 | 88.3% |
| Skill files (371) | every `SKILL.md`, full text | 926,232 | — |
| | `skills manifest` (pointer) | 39 | 100.0% |
| | `skills resolve --k 5` | 501 | 99.9% |

The fixed headline benchmark — 255 tools across 50 servers, `tiktoken cl100k_base`:

| Format | Tokens | Savings |
|---|---:|---:|
| JSON | 71,929 | — |
| TOON | 47,438 | 34% |
| SLIM | 8,282 | 88.5% |
| Compact | 581 | 99.2% |

Reproduce it yourself: `mcptoon bench` (ships in the wheel). Method and caliber:
[docs/tiktoken-benchmarks.md](https://github.com/activeing123/mcptoon/blob/main/docs/tiktoken-benchmarks.md).

---

## Install

```bash
pip install mcptoon
```

<details>
<summary>Other ways to install</summary>

```bash
# Run without installing (needs Node)
uvx mcptoon demo --quick

# From source (for development)
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation

# Claude Code plugin
/plugin marketplace add activeing123/mcptoon
```

</details>

---

## Works with every AI agent

mcptoon is a **CLI tool** — a manager, not a proxy — not a client library. Your agent doesn't
connect to MCP servers; it runs `mcptoon` commands. So the config is written once and shared:

| Agent | How it hooks up |
|---|---|
| Claude Desktop | `mcptoon sync --self` adds one `mcptoon` entry to `claude_desktop_config.json` |
| Claude Code | put the `mcptoon` command in a `SKILL.md` (skills live in `~/.claude/skills`) |
| Codex | put it in `AGENTS.md` |
| Cursor | `mcptoon sync --self` adds it to Cursor's MCP config; or put it in `AGENTS.md` |
| Windsurf | `mcptoon sync --self` writes `mcp_config.json` |
| Cline | `mcptoon sync --self` writes Cline's MCP config |
| VS Code Copilot | `mcptoon sync --self` writes VS Code's MCP config |
| Any agent that can run a shell | call `mcptoon` directly — zero config |

```bash
# Agent needs GitHub access mid-task? It just runs:
mcptoon add github --url https://api.githubcopilot.com/mcp/
# Done. No JSON editing. No restart. No lost context.
```

`mcptoon serve` is the other direction: run all your configured servers behind one MCP
endpoint, with connection pooling and per-agent keys, for clients that insist on a proxy.

---

## Why a CLI, not a proxy

MCP's premise is that every capability is a *server* your agent must be configured to
reach — which is why one new tool means editing per-agent JSON in a different format for
each, restarting everything, and re-paying the full schema cost in every agent.

A command line is the one interface every agent already has. And the form factor is
measurably cheaper on its own, before mcptoon does anything:

- [Firecrawl](https://firecrawl.dev/blog/mcp-vs-cli): the same task cost **1,365 tokens via CLI vs 44,026 via MCP — 32×**
- [Scalekit](https://scalekit.com/blog/mcp-vs-cli-use): CLI **10–32× cheaper, 100% reliable vs MCP's 72%**

If you genuinely need the proxy form, `mcptoon serve` is exactly that — all configured
servers behind one MCP endpoint.

---

## All commands

```bash
mcptoon quickstart              # one-shot start (discover + configure + register the gateway)
mcptoon discover                # scan this machine for MCP servers (--write to keep, --health to probe)
mcptoon init                    # create a sample config (--auto to discover and fill it)
mcptoon list                    # show configured servers
mcptoon manifest                # all tool names (compact by default; 255 tools = 581 tokens)
mcptoon manifest --slim         # names + param types (8,282 vs 71,929 = −88.5%)
mcptoon inspect <server> <tool> # inspect one tool's schema
mcptoon search <query>          # search tools across servers
mcptoon call <server> <tool> '{"args":"here"}'   # call a tool
mcptoon add <name> --stdio|--http <cmd|url>     # add any MCP server
mcptoon remove <name>           # remove a server
mcptoon install <name> --npm|--pip|--url <pkg>  # install + auto-generate handler
mcptoon install --search <kw>   # search the live registries (nothing installed)
mcptoon plugin install <dir>    # install an Agent Plugins 1.0.0 plugin
mcptoon sync                    # sync native config to every detected agent
mcptoon health                  # health-check every MCP server
mcptoon serve                   # run as an MCP server (stdio/HTTP)
mcptoon skills list             # list the skill catalog (--usage adds hit counts)
mcptoon skills sync <src>       # distribute a skill catalog to every agent's folder
mcptoon skills resolve "<task>" # BM25 shortlist of skills (offline, no LLM)
mcptoon bench                   # prove the savings on this machine (tools + skills, one table)
mcptoon demo                    # one command, live demo on your machine
mcptoon demo-server             # the same proof with zero downloads (11 stdlib tools)
mcptoon doctor                  # self-check: Python, config, connectivity
mcptoon status                  # one screen: what's configured, gateway wired, tokens saved
mcptoon stats                   # token-savings dashboard (vs raw JSON)
mcptoon usage                   # local call statistics
mcptoon footer-facts            # one line of savings for a chat footer (never blocks)
mcptoon config                  # show gateway settings (footer, welcome, lang)
mcptoon toggle <server> <tool>  # enable/disable a single tool (--list to show all)
mcptoon policy                  # per-tool compression policy (raw / toon / slim)
mcptoon completion ps           # shell completion (bash/zsh/fish/powershell)
mcptoon off                     # remove the gateway entry from your agents (reversible)
mcptoon uninstall               # full cleanup — prints the plan first (--dry to preview)
```

Full reference in [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md).

### Format family: four tiers, compact by default

All optional; the default is already the leanest tier.

| Tier | Output | vs native schema | Origin |
|---|---|---|---|
| **compact (default)** | names only `search_web` | **99.2% smaller** | common design |
| **slim** | name + param types `search_web\|query:s*` | 88.5% smaller | **mcptoon original** |
| **full** | full schema with params | baseline | native MCP |
| **toon** (results) | reversible structured encoding | ~34% smaller than JSON | open TOON standard |

**Why compact by default?** Choosing *which* tool to use only needs names (581 tokens for
255 tools); parameter detail matters at call time and is fetched on demand. Defaulting to
full schemas would hand the 99.2% right back.

**The rule for agents: use `manifest` to choose, `inspect` before you call.** Measured on
41 live tools: an agent guessing arguments from names alone lands ~10% valid calls, while
one that runs `inspect` once for the 2–3 tools a turn actually uses hits 100% — identical
to injecting every schema, at a fraction of the cost.

---

## Trust and safety

**It's just a 227KB native CLI — delete it anytime; keep it, and you never have to configure tools or skills for any agent again.** mcptoon touches your agent configs, so it is built to be transparent — and easy to walk away from.

Three guards run on every tool result before your agent sees it:

| Guard (on by default) | What it does |
|---|---|
| **Destructive-action block** | a dangerous call is refused unless you pass `--destructive` |
| **Prompt-injection guard** | results are scanned for injection patterns like "ignore previous instructions" and blocked |
| **Credential-leak detection** | a result carrying an API key or token is blocked before it enters context |

- **Reversible.** `mcptoon off` removes the one entry it added; `mcptoon uninstall
  --dry` prints the full removal plan first. Your servers are never deleted unless you ask.
- **No telemetry.** No analytics, no crash reports, nothing phoned home.
- **Local-first.** Your tools, skills and files stay on your machine. The only thing that leaves is `install --search`, which asks the registries for a catalog listing — it never sends your data.
- **No stored credentials.** API keys pass straight from your config or environment.
- **No dependencies.** Pure Python standard library — nothing in the supply chain to audit.
  CI enforces it with `scripts/check_zero_deps.py`.
- **No daemon.** Pure CLI — no resident process, no listening port.
- **Formats don't break compatibility.** The wire protocol is always standard JSON-RPC;
  compact/slim/toon only affect mcptoon's output to the agent. If `--toon` decoding ever
  fails it falls back to JSON, and one `--full` restores the native schema. No lock-in.

**Scope, in one line:** mcptoon is an index and a config manager — it points you to each tool's own source, which you can review on its own terms.

---

## Credits and references

- **[TOON standard](https://github.com/toon-format/toon)** — v4.1 (MIT), vendored from
  python-toon and credited in NOTICE
- **[ToonDeck](https://github.com/activeing123/toondeck)** — a GUI console for mcptoon
  (pre-alpha): same engine, point and click instead of typing commands

**Who builds this:** mcptoon is an independent third-party project maintained by
[@activeing123](https://github.com/activeing123). It is not affiliated with Anthropic.

---

## Contributing

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 1445 passed, 1 skipped
```

Three hard rules: zero dependencies (CI-enforced), new behavior ships with tests, Windows
is a first-class target. New here? Start with
[CONTRIBUTING.md](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md) and
[DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md).

The codebase: **19,944 lines of Python across 28 modules**, zero third-party dependencies.

---

## License

Apache 2.0. See [LICENSE](https://github.com/activeing123/mcptoon/blob/main/LICENSE) and
[NOTICE](https://github.com/activeing123/mcptoon/blob/main/NOTICE).

---

<div align="center" markdown="1">

*mcptoon is an independent third-party MCP client, not affiliated with Anthropic.*

**If mcptoon cut your context bill, star it — that's how other builders find small tools.**

[![Star History Chart](https://api.star-history.com/svg?repos=activeing123/mcptoon&type=Date)](https://star-history.com/#activeing123/mcptoon&Date)

</div>
