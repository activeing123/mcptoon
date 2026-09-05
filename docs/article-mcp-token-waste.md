---
title: How MCP Wastes 4-32× More Tokens Than CLI (and How to Fix It)
published: false
description: 255 MCP tools cost 71,929 tokens before your agent does any work. A names-only CLI manifest does the same job in 581. Here's the evidence, the math, and a fix you can run today.
tags: mcp, ai, llm, python
cover_image: https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/demo-cover.png
---

Here are two numbers that should ruin your morning coffee:

**71,929 tokens** versus **581 tokens**. Same 255 tools. Same machine. Same day.

The first number is what your agent pays — every single session — when 255 tools from 50 MCP servers load as raw JSON schemas into its context window. The second is what the same tool listing costs when discovery happens through a CLI instead.

That's a **300-page book vs. a sticky note**, every single session, before your agent has answered a single question. If you're running multiple MCP servers in Claude Code, Cursor, or anything similar, you're paying the book price right now and probably don't know it.

I didn't believe it either, so I measured it with tiktoken (OpenAI's tokenizer) and built a tool around the result. Let me show you the receipts.

## The Problem: Every Tool Ships Its Entire Resume

When an agent connects to an MCP server, the server hands over a tool catalog. Each entry looks like this:

```json
{
  "name": "search_repos",
  "description": "Search GitHub repositories by query",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query"
      },
      "per_page": {
        "type": "number",
        "description": "Results per page (default 30)"
      }
    },
    "required": ["query"]
  }
}
```

That's one tool. Multiply by every parameter, every description, every nested `properties` block, and then by 255 tools. The protocol's answer to "what can you do?" is a full API reference document — types, defaults, prose descriptions and all — injected wholesale into the context window.

And here's the thing: **the schema only matters twice per session** — once when the model picks a tool, and once when it fills in arguments. The other 99% of the time, that 71K-token wall just sits there, occupying prime real estate while your actual code, conversation, and diffs fight for scraps.

This isn't a niche problem. The [Firecrawl team benchmarked MCP against plain CLI usage](https://firecrawl.dev/blog/mcp-vs-cli) in 2026 and found the *same tasks* cost roughly **~200 tokens through a CLI vs. ~44K tokens through MCP** — a spread of **4× to 32× more expensive** depending on the task shape. [Scalekit's independent analysis](https://scalekit.com/blog/mcp-vs-cli-use) landed on the same headline figure: up to 32× more tokens for identical work.

## Why This Actually Matters (Not Just Aesthetics)

"Tokens cost money" is the obvious objection, but the math is worse than it looks, because schema overhead isn't a one-time fee — it rides along with **every request**.

On a **128K context window** (Claude Sonnet, GPT-4o class models), 71,929 tokens of tool definitions consume **~56% of the window** on syntax alone. More than half your context is gone before the first user message is processed. Your agent now has half the room for your codebase, your conversation history, and your reasoning chains — so it degrades, forgets earlier instructions, or truncates file context sooner.

On a **64K window** — common for cheaper and faster models — it's not "worse," it's **mathematically impossible**. The tools don't fit. Period. You either uninstall servers you paid good time configuring, or you pay for the big-context premium model purely to absorb boilerplate. That second option is the quiet budget killer: you're effectively subscribing to a larger model *to carry JSON*.

And because schemas re-enter every request, the waste compounds. At typical frontier pricing, tens of thousands of redundant tokens × dozens of requests per session × daily sessions adds up to real money spent on punctuation and curly braces. Nobody budgets for that line item because nobody sees it on an invoice. It's just... your context quietly dying.

## Don't Take My Word For It: The Evidence

The best part of this story is that it's not my thesis. Independent groups keep arriving at the same conclusion from completely different directions:

| Source | What they found | Direction |
|--------|----------------|-----------|
| [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576) (official MCP proposal) | Proposes schema redundancy reduction and smarter tool selection — the protocol itself acknowledges the bloat | Spec |
| [Anthropic Engineering — code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | Loading tools on demand cuts context overhead by **up to 98.7%** (~150K → ~2K tokens) | Lab |
| [Firecrawl](https://firecrawl.dev/blog/mcp-vs-cli) | Same tasks: CLI ≈ 200 tokens vs MCP ≈ 44K — **4–32× overhead** | Practitioner |
| [Scalekit](https://scalekit.com/blog/mcp-vs-cli-use) | Independently confirms the **32×** worst case | Practitioner |
| [MCP-Zero](https://arxiv.org/abs/2508.12553) (Xiamen Univ. + USTC) | On-demand tool retrieval keeps retrieval cost **constant regardless of tool count** | Academic |
| Microsoft — dynamic tool discovery | Agent-side guidance: discover tools at runtime instead of front-loading every definition | Vendor |
| ProMCP (ACL ARR 2026) | Profiles token flows and latency of MCP agents — quantifies exactly where the budget goes | Academic |

Read that table again. The standards body, the company that created MCP, two practitioner benchmarks, and two academic groups all converged on the same diagnosis: **eager, whole-catalog schema injection doesn't scale**. When Anthropic's own engineering blog writes about cutting 150K tokens down to 2K, the debate about *whether* there's a problem is over. Only the *how do we fix it* remains.

## The Fix: Pay for Names, Not Schemas

All of the above approaches share one insight: **the model needs an index, not an encyclopedia.**

That's the idea behind [mcptoon](https://github.com/activeing123/mcptoon), a zero-dependency CLI I work on. Instead of injecting every schema into context, tool discovery becomes a **names-only manifest**:

```bash
$ mcptoon manifest --compact
fetch: fetch · github: search_repos, get_file, create_issue · sqlite: query, execute
```

That's the whole listing. 581 tokens for 255 tools. The full schemas stay on disk in `~/.mcptoon/config.json` and **never enter the context at all**. This is the crucial part — it's not compression. Compression ships the whole payload and unpacks it later; the bytes still land in your window eventually. Here the schemas simply aren't sent. The model reads the index, decides which tool fits, and asks for details only if it needs them.

It's a dial, not a switch:

| Tool listing (tiktoken cl100k_base) | Tokens | vs. raw JSON |
|-------------------------------------|-------:|-------------:|
| Raw JSON schemas, 255 tools         | 71,929 | —            |
| `--slim` (names + parameter types)  |  8,282 | −88.5%       |
| `--compact` (names only)            |    581 | **−99.2%**   |

*(Measured over a real-world 255-tool config spanning 50 MCP servers. Reproduce with `mcptoon manifest --compact --tokens`.)*

Same principle applies to outputs. Tool *results* get encoded with [TOON](https://github.com/toon-format/toon) (a tabular token-oriented notation), which trims another **~34%** off typical responses — and it's opt-in, off by default, so nothing surprises you.

## How It Works Under the Hood

The architecture is almost boring, which is the compliment: a small CLI sits **between the agent and the MCP servers**.

```text
Agent ──runs──▶ mcptoon CLI ──spawns (only when called)──▶ MCP server ──▶ result back
                     │
                     └─ ~/.mcptoon/config.json  (schemas live here, on disk)
```

The flow inside an agent session looks like this:

```bash
# 1. Discovery: a name index, not a schema dump
$ mcptoon manifest --compact

# 2. Execution: call exactly one tool
$ mcptoon call fetch fetch '{"url":"https://example.com"}'
# CLI spawns the fetch server, performs the call,
# returns the result, server exits. Nothing lingers.
```

Three properties fall out of this:

1. **Zero servers running until you call one.** No daemon, no proxy process, no port. `mcptoon call` spawns the server, gets the answer, tears it down. Cold-start is a few hundred milliseconds; hot paths can use `mcptoon serve` mode if you want a long-lived connection instead.
2. **Every error is structured and actionable.** Call a tool that doesn't exist and you get `"server 'fetchh' not found — did you mean 'fetch'?"` — which means the *agent* self-corrects instead of stalling until a human rescues it.
3. **Security checks ride along free.** Every result passes inspection for prompt-injection strings and credential patterns (`sk-…`, `AKIA…`, `ghp_…`) before entering context, and destructive tool names require an explicit `--destructive` flag.

And because it's a CLI, it works with **anything that can execute a command** — including agents with no MCP support at all, shell scripts, CI jobs, cron. The shell is the one interface every agent already speaks.

## Try It Yourself in 60 Seconds

Don't trust my benchmarks — measure on your own machine:

```bash
pip install mcptoon     # pure stdlib, ~250KB, zero dependencies

mcptoon demo            # live side-by-side: JSON vs mcptoon, real token counts
```

`demo` spins up a sample fetch server, prints the same listing both ways, and shows the actual token counts computed on your box. No telemetry, no account, nothing leaves your machine — it's ~6,800 lines of readable Python you can audit in an afternoon.

If you already have MCP configs scattered around, start here instead:

```bash
mcptoon quickstart      # detects existing configs, imports them, lists your tools
```

## The Bigger Picture: One Config for Every Agent

Token waste is only half of MCP's tax. The other half is configuration drift: Claude Code wants `.claude.json`, Cursor wants `.cursor/mcp.json`, Claude Desktop wants `claude_desktop_config.json`, Codex and friends each have their own shape. Add a server in Cursor, forget Claude. Fix a path in Claude, break Cursor. Repeat weekly.

mcptoon treats that as the same problem: one source of truth, synced everywhere.

```bash
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon sync            # writes native config into every detected agent

mcptoon sync --watch    # polls config files and re-syncs automatically on change
```

`sync` merges rather than overwrites, so servers you configured by hand stay put. With `--watch`, editing any config propagates to every agent on the machine — cross-agent MCP management that finally stops requiring you to remember which file belongs to which tool.

## Star It, Break It, Tell Me About It

To be fair to MCP: the protocol is good. Standardized tool access was genuinely needed, and the ecosystem explosion proves it. But eager schema injection was the wrong default, and everyone measuring it now agrees. The fix pattern — index in context, schemas on disk, retrieval on demand — is where the whole ecosystem is heading, whether via official proposals like SEP-1576, Anthropic's code execution approach, or plain CLIs.

If you run multiple agents and multiple servers, give it a spin:

- ⭐ Star [mcptoon on GitHub](https://github.com/activeing123/mcptoon) if the numbers made you wince — it genuinely helps others find the project
- Run `mcptoon demo` and paste your own before/after counts in the comments — I'd love to see what your tool mix costs
- Open issues ruthlessly. Weird server? Broken config shape? Bad edge case? That's exactly what the issue tracker is for

Your context window is the most expensive real estate in AI right now. Stop renting it out to curly braces for free.

---

*Further reading: [SEP-1576 — schema redundancy reduction](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576) · [Anthropic: effective context engineering & code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) · [MCP-Zero: proactive tool acquisition](https://arxiv.org/abs/2508.12553)*
