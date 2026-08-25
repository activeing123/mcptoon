# Managing MCP across agents: compare your options by the numbers

> Four ways to give multiple AI agents the same MCP tools — what each one
> actually costs you in setup, tokens, and safety. Numbers first, opinions second.
> Companion pages: [workflow before/after](config-hell-comparison.md) ·
> [benchmark methodology](tiktoken-benchmarks.md)

## The four approaches

| | Manual per-agent configs | Config-sync CLIs | GUI managers | **mcptoon** |
|---|---|---|---|---|
| Add one server, N agents | edit N files × N formats | 1 command, syncs | 1 form, syncs | **1 command** (`mcptoon add` + auto-detect) |
| Agent-side setup required | yes (per agent) | yes (per agent) | yes (per agent) | **no — any shell-capable agent works day one** |
| Platforms | — | usually macOS/Linux-first | often macOS-only (e.g. commercial managers) | **Windows / macOS / Linux equal** (pure Python stdlib) |
| Dependencies to install | n/a | Node/npm trees common | bundled runtimes | **zero (~250KB)** |
| Token cost of tool discovery | full JSON schemas | full JSON schemas | full JSON schemas | **−88.5% (slim) or −99.8% (name-only manifest)** |
| Result payload size | raw JSON | raw JSON | raw JSON | **−34% (TOON encoding)** |
| Security inspection of results | none | none | none | **injection / credential-leak / destructive-op guards on every call** |
| Health checks across agents | manual | some | some | built-in (`mcptoon health`, CI exit codes) |

The capability table is deliberately category-level: it compares *approaches*,
not individual products. Products change; trade-offs don't.

## What discovery actually costs (measured)

Every turn, an agent that supports MCP loads tool definitions into context.
Same 255 tools, four encodings, token counts via tiktoken `cl100k_base`:

| Tools loaded | Raw JSON | TOON results | Name-only manifest (compact) | Savings vs JSON |
|---:|---:|---:|---:|---:|
| 5 | 1,519 | 1,003 | 11 | −99.3% |
| 50 | 14,113 | 9,287 | 123 | −99.1% |
| **255** | **71,929** | 47,438 (−34%) | **123** | **−99.8%** |

Reading it plainly: at 255 tools, raw discovery costs about a 300-page book per
session; mcptoon's compact manifest costs a sticky note.

## Honest limitations

- Discovery savings apply to *tool listing*. Per-call arguments and outputs are
  unchanged — except results encoded as TOON, which measure ~34% smaller.
- Exact numbers vary with your toolset's names/descriptions. Measure your own:
  `mcptoon demo` prints before/after for a live sample server on your machine.
- Config-sync CLIs and mcptoon overlap only partially: they move bytes between
  config files; mcptoon also changes *what gets loaded into context* and adds
  a CLI path that works without native MCP support.

## Try it

```bash
pip install mcptoon      # zero deps, ~250KB
mcptoon quickstart       # import existing configs, see your numbers
```

Back to the [README](../README.md) · methodology details in
[tiktoken-benchmarks.md](tiktoken-benchmarks.md)
