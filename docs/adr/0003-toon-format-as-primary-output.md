# ADR-0003: TOON Format as Primary Output

## Status
Accepted (2026-08-16)

## Context
MCP returns JSON format: `{"content":[{"type":"text","text":"{\"name\":\"react\"}"}]}` — 80 tokens of wrapper to deliver 6 tokens of data. 200 calls = 15K tokens of pure syntax waste.

## Decision
mcptoon uses TOON (Token-Oriented Object Notation) as default output format:
1. `--toon`: Standard TOON (YAML-style + CSV tables), 30-60% smaller than JSON
2. `--slim`: Ultra-compact schemas, 93% smaller than JSON
3. `--compact`: Tool name list, 97-100% smaller than JSON
4. `--json`: Standard JSON (backward compatible)
5. Direct-call mode: no TOON needed, CLI output goes straight to agent context

## Consequences
- ✅ 30-97% token savings per call
- ✅ Direct-call mode = 0 tokens
- ✅ TOON is an open spec, other tools can adopt it
- ⚠️ TOON is not a standard format (but designed to be LLM-friendly)
- ⚠️ Need to maintain toon_encode/toon_decode correctness
