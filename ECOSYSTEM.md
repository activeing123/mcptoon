# mcptoon Ecosystem

> mcptoon is not just a CLI tool — it's a growing ecosystem for token-efficient MCP usage.

## Why an ecosystem?

MCP (Model Context Protocol) is growing fast: 10,000+ servers, 1M+ monthly requests. But every MCP client wastes tokens on JSON syntax — 30-55% of your context window gone before any real work happens.

mcptoon solves this with TOON (Token-Optimized Object Notation). But token optimization alone isn't enough. Developers need:

- **Ready-to-use server configs** (not everyone wants to read MCP docs)
- **Format specs** (so other tools can adopt TOON)
- **Integration guides** (every agent is different)
- **Community profiles** (the long tail of MCP servers)

That's why we're building an ecosystem, not just a tool.

---

## Ecosystem components

```
                    ┌─────────────────────────┐
                    │      mcptoon CLI        │
                    │   (token optimization)  │
                    └────────────┬────────────┘
                                 │
          ┌──────────────┬───────┴───────┬──────────────┐
          │              │               │              │
    ┌─────▼─────┐  ┌────▼─────┐  ┌──────▼──────┐  ┌───▼──────────┐
    │  Profiles │  │  TOON    │  │ Integration │  │   Badge      │
    │  Registry │  │  Spec    │  │   Guides    │  │   Program    │
    │  23 → 100 │  │  v1 → v2 │  │   0 → 10    │  │   0 → 50     │
    └───────────┘  └──────────┘  └─────────────┘  └──────────────┘
```

### 1. MCP Profiles Registry

Pre-configured, battle-tested MCP server templates. Copy, paste, done.

| Stat | Value |
|------|-------|
| Profiles now | 23 |
| Tools covered | 186+ |
| Security-audited | 23 |
| Target | 100+ profiles |
| Location | [`mcp/`](mcp/) |

**Categories:** developer · database · search · browser · communication · file · cloud · data · knowledge · utility

Browse profiles: [mcp/README.md](mcp/README.md)

### 2. TOON Format Specification

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

### 3. Integration Guides

Every major AI agent gets a step-by-step mcptoon integration guide.

| Agent | Type | Status |
|-------|------|--------|
| Claude Code | CLI | 📝 Planned |
| Cursor | IDE | 📝 Planned |
| CatPaw | IDE | 📝 Planned |
| Codex (OpenAI) | CLI | 📝 Planned |
| OpenCode | CLI | 📝 Planned |
| Continue | IDE | 📝 Planned |
| Aider | CLI | 📝 Planned |
| Cline | IDE | 📝 Planned |
| GitHub Copilot | IDE | 📝 Planned |
| Windsurf | IDE | 📝 Planned |

Each guide: 30-second quick start → full config → token savings comparison → FAQ.

### 4. "Powered by mcptoon" Badge

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

| Quarter | Milestone | Profiles | Guides | TOON SDK |
|---------|-----------|----------|--------|----------|
| 2026 Q3 | v0.3.0 — Credential leak detection + integration guides | 23 | 3 | — |
| 2026 Q4 | v0.5.0 — TOON Spec v1 | 30 | 7 | — |
| 2027 Q1 | v0.7.0 — Smart format selection | 50 | 7 | JS |
| 2027 Q2 | **v1.0.0 — Stable ecosystem** | 100 | 10 | JS + Go |
| 2027 H2 | Post-v1.0 — Multi-language + marketplace | 150+ | 15 | JS + Go + Rust |

---

## Design principles

1. **Zero dependencies** — Every ecosystem component works without npm/pip installs beyond mcptoon itself
2. **Open format** — TOON is free to implement in any language, no license restrictions
3. **Community-driven** — Profiles and guides are community-contributed, not vendor-controlled
4. **Real data** — Every profile is battle-tested with real usage numbers, not theoretical
5. **Security first** — No credentials in profiles, no telemetry in CLI, no backdoors anywhere. Every profile is security-audited with `credential_safe`, `env_vars_required`, and `permissions` fields. Tool results are scanned for credential leaks via 12 regex patterns before reaching your agent's context.

---

## Partner program

Are you an MCP server author? Let's collaborate:

- We write and verify a profile for your server
- You add a "Powered by mcptoon" badge to your README
- Both projects benefit from cross-promotion

[Open an issue](https://github.com/activeing123/mcptoon/issues) with the `partner` label to start.

---

## License

All ecosystem materials (profiles, specs, guides) are Apache 2.0, same as mcptoon itself.

TOON format is free to implement — no patent claims, no license restrictions.
