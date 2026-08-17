# mcptoon Ecosystem

> mcptoon is not just a CLI tool — it's a growing ecosystem for token-efficient MCP usage.

## Why an ecosystem?

MCP (Model Context Protocol) is growing fast: 10,000+ servers, 1M+ monthly requests. But every MCP client wastes tokens on JSON syntax — 30-55% of your context window gone before any real work happens.

mcptoon solves this with TOON (Token-Optimized Object Notation). But token optimization alone isn't enough. Developers need:

- **Integration guides** (every agent is different)
- **Format specs** (so other tools can adopt TOON)
- **Community configs** (the long tail of MCP servers)

That's why we're building an ecosystem, not just a tool.

---

## Ecosystem components

```
                    ┌─────────────────────────┐
                    │      mcptoon CLI        │
                    │   (token optimization)  │
                    └────────────┬────────────┘
                                 │
          ┌──────────────┬───────┴───────┐
          │              │               │
    ┌─────▼─────┐  ┌────▼─────┐  ┌──────▼──────┐
    │  TOON     │  │ Integration │  │   Badge     │
    │  Spec     │  │   Guides    │  │   Program   │
    │  v1 → v2  │  │   0 → 10    │  │   0 → 50    │
    └───────────┘  └─────────────┘  └─────────────┘
```

### 1. TOON Format Specification

TOON (Token-Optimized Object Notation) is the encoding that saves 40-97% tokens vs JSON.

| Format | Token savings | Use case |
|--------|--------------|----------|
| TOON | 40-60% | Tool results, structured data |
| SLIM | 93% | Tool schemas (name\|param:type*) |
| Compact | 97% | Tool discovery (names only) |

**Roadmap:**
- TOON Spec v1 — standalone document (Q4 2026)
- `toon-js` — JavaScript/TypeScript SDK (< 5KB)
- `toon-go` — Go SDK
- `toon-rust` — Rust SDK
- Cross-language consistency test suite

### 2. Integration Guides

Every major AI agent gets a step-by-step mcptoon integration guide.

| Agent | Type | Status |
|-------|------|--------|
| Claude Code | CLI | ✅ Ready |
| Cursor | IDE | ✅ Ready |
| Codex (OpenAI) | CLI | ✅ Ready |
| OpenCode | CLI | ✅ Ready |
| Continue | IDE | 📝 Planned |
| Aider | CLI | 📝 Planned |
| Cline | IDE | 📝 Planned |
| GitHub Copilot | IDE | 📝 Planned |
| Windsurf | IDE | 📝 Planned |

Each guide: 30-second quick start → full config → token savings comparison → FAQ.

### 3. "Powered by mcptoon" Badge

MCP servers that recommend mcptoon for token-efficient access can display a badge:

```markdown
[![Powered by mcptoon](https://img.shields.io/badge/Powered%20by-mcptoon-blue)](https://github.com/activeing123/mcptoon)
```

**Coming soon.** If you're an MCP server author and want early access, [open an issue](https://github.com/activeing123/mcptoon/issues).

---

## How to participate

### Add a Server Integration

1. Pick an MCP server (from [npm](https://www.npmjs.com/search?q=mcp) or [pip](https://pypi.org/search?q=mcp))
2. Test it: `mcptoon add my-server --stdio npx -y <package>` then `mcptoon manifest --toon`
3. Write a short integration note (server name, install command, example tool call)
4. Open a PR to `docs/integrations/`

### Write an Integration Guide

1. Pick an agent from the list above
2. Follow the [guide template](#) (coming soon)
3. Test the integration end-to-end
4. Open a PR to `docs/integrations/`

### Implement TOON in another language

1. Read the TOON encoding rules in [`src/mcptoon/output.py`](src/mcptoon/output.py)
2. Implement `toon()` and `slim_toon()` in your language
3. Zero dependencies, < 500 lines
4. Open a PR with your implementation + test cases

### Report Token Savings

Using mcptoon? Share your before/after numbers:

```bash
mcptoon usage  # shows your token savings
```

[Open a discussion](https://github.com/activeing123/mcptoon/discussions) with your numbers — we feature the best ones.

---

## Roadmap

| Quarter | Milestone | Guides | TOON SDK |
|---------|-----------|--------|----------|
| 2026 Q3 | v0.5.0 — Install command + zero bundled content | 4 | — |
| 2026 Q4 | v0.6.0 — TOON Spec v1 draft | 7 | — |
| 2027 Q1 | v0.8.0 — Smart format selection | 7 | JS |
| 2027 Q2 | **v1.0.0 — Stable ecosystem** | 10 | JS + Go |
| 2027 H2 | Post-v1.0 — Multi-language + marketplace | 15 | JS + Go + Rust |

---

## Design principles

1. **Zero dependencies** — Every component works without npm/pip installs beyond mcptoon itself
2. **Open format** — TOON is free to implement in any language, no license restrictions
3. **Community-driven** — Guides and configs are community-contributed, not vendor-controlled
4. **Real data** — Every claim is backed by benchmark numbers, not theoretical
5. **Security first** — No credentials in configs, no telemetry in CLI, no backdoors anywhere. Tool results are scanned for credential leaks via 12 regex patterns before reaching your agent's context.

---

## Partner program

Are you an MCP server author? Let's collaborate:

- We test your server with mcptoon and verify token savings
- You add a "Powered by mcptoon" badge to your README
- Both projects benefit from cross-promotion

[Open an issue](https://github.com/activeing123/mcptoon/issues) with the `partner` label to start.

---

## License

All ecosystem materials (specs, guides) are Apache 2.0, same as mcptoon itself.

TOON format is free to implement — no patent claims, no license restrictions.
