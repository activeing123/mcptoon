# ADR-0005: Adopt standard TOON as primary format, rename legacy to MCPTOON-SLIM

Date: 2026-08-12

## Status

Proposed

## Context

mcptoon was created with a custom pipe-separated encoding called "TOON" (Token-Optimized Object Notation). After investigation, we discovered that an external open-source project `toon-format/toon` already defines "TOON" (Token-Oriented Object Notation) with a different syntax and an official spec. This project has been covered by InfoQ, CSDN, Juejin, and has implementations in .NET, Java, and JavaScript.

**Our TOON syntax:** `name:search|count:3|cached:true`
**Standard TOON syntax:** `users[2]{id,name,role}:\n1,Alice,admin\n2,Bob,user`

The naming collision creates three problems:
1. GitHub users who know standard TOON will expect compatibility and find a completely different format
2. We cannot claim TOON compliance or list mcptoon in TOON ecosystem directories
3. The name "TOON" in our `--toon` flag is misleading

Additionally, our legacy format has critical defects:
- No decoder (one-way only, no round-trip)
- Data loss: colons in values are replaced with `_` (URLs become `https___example.com`)
- Separator collision: `|` and space in values conflict with structural delimiters
- No formal spec document

## Decision

1. **Rename our `--toon` flag to `--mcptoon`** for the legacy pipe-separated format
2. **Add `--toon` as standard TOON compliant** output (implements `toon-format/toon` spec)
3. **Keep `--slim` as-is** — it's a unique mcptoon innovation, no collision
4. **Keep `--compact` as-is** — it's a name list, not a data format
5. **Fix data loss in legacy format**: use proper escaping instead of colon replacement
6. **Add a TOON decoder** for standard TOON format
7. **Document the distinction** in README and CLI help

### Flag mapping after change

| Flag | What it does | Format |
|------|-------------|--------|
| `--toon` | Standard TOON (toon-format/toon spec) | YAML+CSV style |
| `--mcptoon` | Legacy mcptoon pipe format (improved) | Pipe-separated |
| `--slim` | Ultra-compact tool schemas | mcptoon-specific |
| `--compact` | Names only | Not a format |
| `--json` | Standard JSON | Baseline |

## Consequences

- **Breaking change**: existing users of `--toon` will get different output
- **Migration path**: `--mcptoon` preserves old behavior for existing scripts
- **Ecosystem benefit**: `--toon` now interoperates with the growing TOON ecosystem
- **Reduced criticism**: GitHub visitors who know standard TOON won't be confused
- **Additional work**: need to implement standard TOON encoder + decoder (~200 lines)
