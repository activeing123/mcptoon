# Your AI agent's tools eat 40,000 tokens before it does any work. I measured with tiktoken — and found a 91% fix.

When you connect 5 MCP servers to your agent, something invisible happens before you even ask a question. Every tool schema — every `{"type":"object","properties":...}` — gets injected into your context window. Puppeteer alone has 47 tools. Playwright has 52. Together, that's ~50K tokens of JSON you're paying for before your agent does any work.

This isn't hypothetical. Anthropic says [context window is a scarce resource](https://docs.anthropic.com/en/docs/build-with-claude/context-windows). Cursor says [the difference between good and bad agents is context management](https://cursor.com/blog/context-engineering). Latent Space's MCP analysis identifies "a scaling cliff around 20-30 tools."

I built [mcptoon](https://github.com/activeing123/mcptoon) — a 128KB wheel, zero dependencies, that keeps MCP servers configured but their schemas out of your context. This post shows real tiktoken data (OpenAI's official tokenizer) on how much it actually saves.

## The 5 problems

These aren't marketing constructs. Every MCP user hits them:

**1. Context death.** Add 5 MCP servers with browser tools → 50-100K tokens of schemas → 128K context is 40-80% gone. You uninstall servers to make room. Then you need one. Reinstall, reconfigure, repeat.

**2. Config hell.** Want to add a server? Hand-edit `claude_desktop_config.json`. Miss a comma → MCP won't load. Wrong path → won't load. No error, no log, just a blank tool list.

**3. Agent can't self-serve.** Your agent says "I need GitHub search to finish this." It can't install tools — it's an AI. So you stop coding, go edit JSON, restart the agent. Momentum dies.

**4. Reconfigure per agent.** Set up 15 servers for Claude Code. Now Cursor — different config format, different file location, redo all 15. Then OpenCode. Then Codex.

**5. No visibility.** You don't know how many tokens your tools are eating. No way to audit, no way to budget.

mcptoon addresses all five: `mcptoon add server --stdio npx -y @package`, one config for all agents, `mcptoon manifest --slim` for compact schemas, `mcptoon doctor` for debugging. Your agent can run `mcptoon add` itself.

## See it: JSON vs SLIM

A single tool schema in JSON:

```json
{
  "name": "search_web",
  "description": "Search the web for current information",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "The query parameter"},
      "num_results": {"type": "number", "description": "The num_results value"}
    },
    "required": ["query"]
  }
}
```

SLIM format, one line:

```
search_web|query:s*|num_results:n
```

`*` marks required params. `s`=string `n`=number `b`=boolean `a[type]`=array `o{keys}`=object.

255 tools: JSON is a ~40,000 token wall. SLIM is a ~3,500 token screen. **91% tokens saved, tiktoken-verified.** *(Sample A — see the caliber note below; the canonical figures are 71,929 → 8,282 → 581.)*

## Real tiktoken benchmarks

I ran the actual numbers using `tiktoken` (OpenAI's official BPE tokenizer, `cl100k_base` for GPT-4 and `o200k_base` for GPT-4o). 255 MCP tool schemas:

> **Caliber note (2026-09-05).** This table is *Sample A* — a 255-tool config whose
> descriptions were shorter than the config quoted everywhere else, so its JSON baseline
> is 39,964 rather than 71,929. The repo-wide canonical caliber is *Sample B*:
> `assets/benchmark_tiktoken.json` — JSON 71,929 → SLIM 8,282 (−88.5%) → name index 581
> (−99.2%). READMEs and posts quote Sample B. Run `python scripts/bench_tokens.py` to
> measure your own setup. An earlier row here read "Compact (30 names) = 63 tokens,
> 99.8% saved": that listing was truncated at 30 entries by a bug that is now fixed, so
> the row has been removed rather than corrected — the full index is the 581 figure.

| Format | tiktoken (cl100k) | tiktoken (o200k) | Savings vs JSON |
|--------|-------------------|------------------|-----------------|
| JSON (full schemas) | 39,964 | 39,978 | — |
| **SLIM (name\|param:type)** | **3,511** | **3,525** | **91%** |
| All 255 names | 581 | 595 | 98.5% |

All numbers from actual `tiktoken.get_encoding()` calls, not `chars ÷ 4` approximations.

### What this means

A typical agent session: you have 10 MCP servers, 255 tools total.

- **Without mcptoon:** Every request carries ~40K tokens of schemas. At GPT-4o pricing ($5/M tokens), every 25 requests = $5 wasted on schemas.
- **With mcptoon:** SLIM format is 3.5K tokens. Same 25 requests = $0.44. **91% cost savings.**

100 sessions/day = $18/day saved, $540/month. And that's just 10 servers. 100 servers scales the gap further.

### Format per use case

mcptoon doesn't force non-JSON on the LLM. The key is **the right format for the consumer**:

| Format | For whom | When |
|--------|----------|------|
| `--json` | LLM | Tool calls (models trained on JSON) |
| `--slim` | LLM | Tool discovery (listing available tools) |
| `--toon` | Human | Terminal output, debugging |
| `--compact` | Human | Quick "what tools exist?" check |

Optimization happens only at the discovery layer. Actual tool calls are always JSON.

## Works with every agent

mcptoon is a CLI tool, not an MCP client library. **If your agent can run shell commands, it can use mcptoon.** No plugins, no SDK, no per-agent setup.

| Agent | Usage |
|-------|-------|
| Claude Code | `mcptoon manifest --slim` → compact schemas |
| Cursor | Same, one config works |
| OpenCode | Same |
| Codex | Same |
| Any shell-capable agent | Same |

One config file `~/.mcptoon/config.json`, shared across all agents. Switch agents without reconfiguring.

## Architecture

Two-layer decoupled design:

```
┌─────────────────────────────────────────┐
│  Layer 1: mcptoon CLI (~128KB, zero deps)│
│  Runs in agent's shell, optimizes tokens │
├─────────────────────────────────────────┤
│  Layer 2: MCP Servers (your existing)    │
│  Untouched, stdio/SSE as usual           │
└─────────────────────────────────────────┘
```

Each layer is independent. Swap agents without touching servers. Swap servers without touching agents. mcptoon is the glue — a 128KB wheel, zero dependencies, pure Python stdlib.

## Community

The community is already contributing: [Dockerfile](https://github.com/activeing123/mcptoon/pull/11) for containerized usage. Apache 2.0 license, 730 tests, fully open source.

## Try it

```bash
pip install mcptoon          # 128KB wheel, zero deps
mcptoon init                 # Sample config
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon manifest --slim      # Compact schemas for LLM discovery
mcptoon manifest --compact   # Tool names for human scanning
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

Docker works too:

```bash
docker build -t mcptoon .
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --slim
```

## Roadmap

- **Token budget monitoring** — `mcptoon usage` shows real-time token consumption per server
- **Adaptive schema trimming** — Dynamically choose --slim / --compact based on remaining context

## Conclusion

MCP is a good protocol. JSON schema injection is its Achilles' heel. mcptoon doesn't "solve" it — it makes it hurt less: schemas stay out of your context until you actually need them.

SLIM format saves 91% tokens, tiktoken-verified. CLI approach works with every agent. The 5 pain points are real. A 128KB wheel, zero dependencies — 11,400 lines of stdlib Python across 21 modules.

That's it.

---

*GitHub: [activeing123/mcptoon](https://github.com/activeing123/mcptoon) · PyPI: `pip install mcptoon` · License: Apache 2.0 · 730 tests · Zero dependencies*
