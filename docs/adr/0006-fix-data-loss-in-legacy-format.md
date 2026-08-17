# ADR-0002: Fix data loss in legacy mcptoon format

Date: 2026-08-12

## Status

Proposed

## Context

The current `_toon_scalar` function replaces colons in string values with underscores:

```python
s = str(val)[:200]
return s.replace(":", "_")  # DATA LOSS
```

This means:
- URLs become invalid: `https://example.com` → `https___example.com`
- Time values become ambiguous: `12:30:00` → `12_30_00`
- File paths on Windows: `C:\Users` → `C_\Users` (colon already missing, but `C:` → `C_`)

The root cause is that `:` is used as the key-value separator in the format, so having `:` in values creates ambiguity.

Standard TOON avoids this by using YAML-style indentation (no inline key-value separator needed) and CSV-style commas for arrays.

## Decision

For the legacy `--mcptoon` format, adopt **escape sequences** instead of character replacement:

| Original char | Escape sequence | Rationale |
|--------------|----------------|-----------|
| `:` | `\c` | "colon" — 2 tokens, same as `_` but reversible |
| `\|` | `\p` | "pipe" — avoids separator collision |
| `\n` | `\n` | standard escape, recognizable |

Add a `decode_mcptoon()` function that reverses these escapes, achieving round-trip.

For the new standard `--toon` format, no escaping needed — the spec handles this via structure.

## Consequences

- **Breaking change**: output format changes slightly (`:` → `\c` in values)
- **Round-trip achieved**: `decode(encode(x)) == x` now holds
- **No more data loss**: URLs and times preserved
- **~30 lines of code** for escape/unescape logic
