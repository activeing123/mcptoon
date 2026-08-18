# TOON Format Specification

**Version:** 1.0 (aligned with [toon-format/toon](https://github.com/toon-format/toon) community spec v4.1)

**Full name:** Token-Oriented Object Notation

**Purpose:** A token-efficient serialization format for LLM contexts. 30-60% fewer tokens than JSON (tiktoken-verified, cl100k_base).

---

## 1. Design Principles

1. **No braces, no quotes, no commas in the common case** — these are expensive in BPE tokenizers
2. **YAML-style `key: value`** — one per line, indentation expresses nesting
3. **CSV-style arrays** — uniform object arrays become header + rows
4. **Standard literals** — `true`, `false`, `null` (lowercase, matching JSON/TOON community spec)
5. **Round-trip safe** — `decode(encode(x)) == x` for all JSON-serializable data

---

## 2. Scalar Types

| Type | JSON | TOON | Tokens (cl100k) |
|------|------|------|-----------------|
| Boolean | `true` | `true` | 1 |
| Boolean | `false` | `false` | 1 |
| Null | `null` | `null` | 1 |
| Integer | `42` | `42` | 1 |
| Float | `3.14` | `3.14` | 2 |
| String | `"hello"` | `hello` | 1 |

**No Unicode substitutions.** Earlier versions replaced `true`→`T`, `null`→`∅`, etc. These were removed in v0.3.0 because BPE tokenizers encode Unicode symbols as 2+ tokens, making them more expensive than the originals.

---

## 3. Objects

### Simple object

JSON:
```json
{"name": "search", "count": 3, "cached": true}
```

TOON:
```
name: search
count: 3
cached: true
```

### Empty object

```
{}
```

### Nested object

JSON:
```json
{"user": {"name": "Alice", "age": 30}}
```

TOON:
```
user:
  name: Alice
  age: 30
```

---

## 4. Arrays

### Uniform object array (CSV-style)

When all objects in an array share the same keys, TOON emits a field header followed by CSV rows.

JSON:
```json
[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
```

TOON:
```
[2]{id,name}:
  1,Alice
  2,Bob
```

Format: `[count]{field1,field2,...}:` followed by indented rows, one per item, values comma-separated.

### Scalar array

JSON:
```json
{"tags": ["python", "rust", "go"]}
```

TOON:
```
tags[3]:
  python
  rust
  go
```

### Mixed-type array

When array items have different types or non-uniform keys:

```
items[3]:
  value: hello
  value: 42
  value: true
```

### Empty array

```
[]
```

---

## 5. Escaping Rules

Values containing commas, newlines, or double quotes are wrapped in double quotes (CSV-style):

| Value | TOON encoding |
|-------|--------------|
| `hello` | `hello` |
| `hello, world` | `"hello, world"` |
| `say "hi"` | `"say ""hi"""` |
| `line1\nline2` | `"line1\nline2"` |

Internal double quotes are escaped by doubling (`"` → `""`), matching RFC 4180 CSV escaping.

---

## 6. Indentation

- **2 spaces per level** (not tabs)
- Indentation determines nesting depth
- A child line must be indented deeper than its parent
- De-indent signals end of a nested block

---

## 7. Round-Trip Safety

`toon_decode(toon_encode(x)) == x` for all JSON-serializable data:

- Objects preserve key order
- Arrays preserve element order
- All scalar types (bool, null, int, float, string) round-trip correctly
- Escaped strings unescape correctly

---

## 8. Token Comparison (tiktoken cl100k_base)

255 MCP tool schemas, 5 real servers:

| Format | Tokens | Savings vs JSON |
|--------|--------|-----------------|
| JSON (full schemas) | 39,964 | — |
| TOON (this spec) | ~20,000 | ~50% |
| SLIM (mcptoon-specific) | 3,511 | 91% |
| Compact (names only) | 581 | 98.5% |

Reproduce: `python _benchmark.py` → `assets/benchmark_data.json`

---

## 9. Relationship to mcptoon-Specific Formats

TOON is the standard format. mcptoon adds two proprietary formats on top:

| Format | Spec | Purpose |
|--------|------|---------|
| **TOON** (`--toon`) | This document, aligned with toon-format/toon v4.1 | General output, round-trip safe |
| **SLIM** (`--slim`) | mcptoon-specific, not in TOON spec | Ultra-compact tool schemas (`name\|param:type*`) |
| **Compact** (`--compact`) | mcptoon-specific | Tool names only |

SLIM and Compact are not part of the TOON spec. They are mcptoon optimizations for specific use cases (tool discovery).

---

## 10. Implementation

**Encoder/Decoder:** `src/mcptoon/toon_vendored.py` — vendored from [python-toon](https://github.com/xaviviro/python-toon) v0.1.1 (MIT License, by Xavi Vinaixa).

**Wrapper:** `src/mcptoon/output.py` (`toon_encode()` / `toon_decode()`) — delegates to vendored encoder/decoder with fallback to legacy parser.

- Pure Python stdlib, zero dependencies
- Vendored from python-toon v0.1.1 (MIT License, Copyright (c) Xavi Vinaixa)
- Spec-compliant with [toon-format/toon](https://github.com/toon-format/toon) v4.1 (25K stars, official TypeScript reference by Johann Schopplich)
- Non-strict decode mode by default (lenient parsing for real-world MCP outputs)
- 427+ tests cover encoding, decoding, round-trip safety, edge cases
- Known minor differences from official spec: empty containers (`{}`/`[]` vs empty string), 3 edge-case decode patterns (keyed tabular form, nested field groups) — all non-blocking for MCP use cases

---

## 11. What TOON Is Not

- **Not a replacement for JSON in tool calls.** LLMs are trained on JSON. Tool calls (`--json`) should remain JSON. TOON is for **discovery and display** (listing tools, showing results).
- **Not a general-purpose data format.** Optimized for LLM token efficiency, not human readability or machine parsing speed.
- **Not a streaming format.** Encodes complete objects, not incremental streams.
- **No schema validation.** TOON is a serialization format, not a data validation framework.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-08-17 | Initial SPEC.md. Aligned with toon-format/toon v4.1. Removed Unicode substitutions (v0.3.0). |
| 1.1 | 2026-08-18 | **Replaced custom encoder with vendored python-toon v0.1.1** (MIT, by Xavi Vinaixa). Now spec-compliant. 47/52 compatibility tests pass (was 35/52). |
