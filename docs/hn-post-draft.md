# HN Post Draft — Text Post (no link in title)

---

## Title

I claimed 99.87% token savings on MCP. HN commenters proved me wrong. Here's what I fixed.

## Body

Six days ago I posted a Show HN for a CLI tool that sits between AI agents and MCP servers. The pitch: keep tool schemas out of your context window, save tokens.

It got 73 points and ~30 comments. Roughly half were technical corrections. They were right about almost everything.

Here's what happened, what I got wrong, and what the real numbers are.

---

### What HN caught

**1. My token counts were wrong.**

My original benchmark claimed 255 MCP tools = 90,804 tokens in JSON. Commenters asked me to verify with an actual tokenizer. I did — using `tiktoken` (OpenAI's official BPE tokenizer, `cl100k_base`).

The real number: 39,964 tokens. Not 90,804.

My original figure was a character-based estimate (`chars ÷ 4`), not a real token count. I conflated bytes with tokens. The difference matters — 90K sounds catastrophic, 40K is still bad but honest.

**2. My encoding used Unicode symbols that cost MORE tokens.**

I had replaced `true`→`T`, `false`→`F`, `null`→`∅`, `\n`→`↲`. The idea: fewer characters = fewer tokens.

Wrong. `true` is 1 token in cl100k_base. `∅` (U+2205) is 2 tokens. `↲` is 2 tokens. My "optimization" was actively making things worse.

I removed every Unicode substitution. Now the output uses standard `true`/`false`/`null` — matching the official TOON spec (v4.1, github.com/toon-format/spec) which explicitly requires lowercase literals.

**3. "Zero information lost" was false for compact mode.**

`--compact` returns tool names only: `search_web fetch git_search ...`

I claimed "zero information lost." That's not true — you lose descriptions, parameter schemas, and types. What I should have said: `--compact` is for "what tools exist?" scanning, `--slim` preserves full schema info in a compressed format.

I fixed the README to describe each format by what it preserves, not by a misleading absolute.

---

### The real numbers (tiktoken-verified)

255 MCP tool schemas from 5 real servers (filesystem, memory, sequential-thinking, sqlite, time):

| Format | tiktoken (cl100k_base) | Savings vs JSON |
|--------|----------------------|-----------------|
| JSON (full schemas) | 39,964 | — |
| SLIM (`name\|param:type*`) | 3,511 | **91%** |
| Compact (tool names only) | 581 | 98.5% |
| TOON (standard, round-trip safe) | ~20,000 | ~50% |

These are actual `tiktoken.get_encoding("cl100k_base").encode()` calls, not approximations. I published the benchmark script so anyone can reproduce: `python _benchmark.py` outputs `assets/benchmark_data.json`.

**91% savings is still significant.** 40K → 3.5K tokens for tool discovery is real. But 99.87% was a number I cannot defend, and I've stopped using it.

---

### What the tool actually does

The core idea didn't change — it's still valid. MCP servers inject tool schemas into your context window before any work starts. A CLI proxy keeps schemas out of context:

```
Without proxy:  255 tools → 39,964 tokens of JSON schemas in your context
With proxy:     255 tools → 3,511 tokens (SLIM format). 91% savings.
                 Or → 581 tokens (compact, names only). 98.5% savings.
```

The agent runs shell commands to discover and call tools. Tool schemas live on disk, not in context. Only the compact result the agent requests enters context.

It's a 200KB Python CLI, zero dependencies, works with any agent that runs shell commands (Claude Code, Cursor, Codex, etc.).

---

### What I learned

1. **Always verify token claims with a real tokenizer.** `chars ÷ 4` is a rough heuristic, not a measurement. Different tokenizers (cl100k_base, o200k_base, Claude's tokenizer) produce different counts. Pick one, be explicit, be honest.

2. **Read the spec before implementing.** The official TOON spec (v4.1) is clear: `true`, `false`, `null` as lowercase literals. No Unicode symbol substitution. I was implementing a format I hadn't fully read.

3. **Don't conflate "smaller" with "lossless."** Compact mode is smaller because it drops information. That's a trade-off, not a free lunch. Naming it honestly helps users pick the right format for their use case.

4. **HN commenters made the project better.** `debazel` caught the Unicode token issue. `saretup` caught the "zero information lost" claim. `philipp-gayret` asked for real tokenizer data. `stephantul` pointed out I hadn't investigated how tokenization works. `vunderba` nailed it: "confuse token counts with byte counts." They were all right. The current version is better because of them.

---

### Current state

- 177 stars, 486 tests, v0.5.1 on PyPI
- TOON encoding now matches official spec v4.1 (no Unicode hacks)
- Benchmark data is tiktoken-verified, reproducible
- README no longer claims 99.87% — uses the real 91% (SLIM) and 98.5% (compact) figures
- Apache 2.0, zero dependencies, pure Python stdlib, 250KB

If you want to try it: `pip install mcptoon`

GitHub: https://github.com/activeing123/mcptoon

---

*Thanks to everyone who commented on the original post. The criticism was sharper than the code, and the code is better for it.*
