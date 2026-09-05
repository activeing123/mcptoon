#!/usr/bin/env python3
"""Measure the token cost of your own MCP tool listing.

This is the reproduction path behind the numbers in README.md. It takes a
mcptoon config (default: ~/.mcptoon/config.json, override with --config or
MCPTOON_CONFIG_FILE) and counts, with the real OpenAI BPE tokenizers:

  * the raw JSON tool list an agent would receive
  * the --slim listing (names + params)
  * the --compact name index (what mcptoon actually puts in context)

tiktoken is a third-party package on purpose: this is a measurement tool, not
part of the zero-dependency runtime. Install it first:

    pip install tiktoken

Usage:
    python scripts/bench_tokens.py                     # your own config
    python scripts/bench_tokens.py --config my.json    # a specific config
    python scripts/bench_tokens.py --json              # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcptoon.config import CACHE_DIR  # noqa: E402
from mcptoon.output import compact, slim_toon  # noqa: E402  (dev tool, path shim is fine)

ENCODINGS = ("cl100k_base", "o200k_base")


def load_tools() -> dict[str, list[dict]]:
    """Return {server_name: [tool, ...]} from the schema cache.

    Reads ~/.cache/mcptoon/schema_cache.json directly rather than through
    cache.get_cached_tools(): a measurement should see the schemas that are
    actually on disk, not obey the runtime freshness TTL.
    """
    cache_file = CACHE_DIR / "schema_cache.json"
    if not cache_file.exists():
        return {}
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    return {name: entry["tools"] for name, entry in cache.items() if entry.get("tools")}


def as_json_blob(tools: dict[str, list[dict]]) -> str:
    """What an agent receives at tools/list time: name + description + schema."""
    payload = [
        {
            "name": t.get("name"),
            "description": t.get("description", ""),
            "inputSchema": t.get("inputSchema") or t.get("parameters") or {},
        }
        for server in tools.values()
        for t in server
    ]
    return json.dumps(payload, ensure_ascii=False)


def as_slim(tools: dict[str, list[dict]]) -> str:
    """--slim: name|param:type per tool, descriptions and schema wrappers stripped."""
    return slim_toon([t for server in tools.values() for t in server])


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure your MCP context tax with tiktoken.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    try:
        import tiktoken
    except ImportError:
        print("tiktoken is required:  pip install tiktoken", file=sys.stderr)
        return 2

    tools = load_tools()
    n_tools = sum(len(v) for v in tools.values())
    if not n_tools:
        print(
            f"no cached tool lists in {CACHE_DIR / 'schema_cache.json'} yet - run "
            "`mcptoon manifest` once so mcptoon fetches the schemas it would replace",
            file=sys.stderr,
        )
        return 2

    samples = {
        "raw JSON schemas": as_json_blob(tools),
        "--slim names+params": as_slim(tools),
        "--compact name index": compact({s: [t.get("name", "") for t in ts] for s, ts in tools.items()}),
    }

    counts: dict[str, dict[str, int]] = {}
    for enc_name in ENCODINGS:
        enc = tiktoken.get_encoding(enc_name)
        for label, text in samples.items():
            counts.setdefault(label, {})[enc_name] = len(enc.encode(text))

    if args.json:
        print(json.dumps({"servers": len(tools), "tools": n_tools, "counts": counts}, indent=2))
        return 0

    print(f"source: {CACHE_DIR / 'schema_cache.json'}")
    print(f"servers: {len(tools)}   tools: {n_tools}\n")
    header = f"{'format':<22}" + "".join(f"{e:>14}" for e in ENCODINGS)
    print(header)
    print("-" * len(header))
    base = counts["raw JSON schemas"]["cl100k_base"]
    for label, per_enc in counts.items():
        row = f"{label:<22}" + "".join(f"{per_enc[e]:>14,}" for e in ENCODINGS)
        if not base or per_enc["cl100k_base"] == base:
            print(f"{row}  (baseline)")
        else:
            saved = 100.0 * (1 - per_enc["cl100k_base"] / base)
            print(f"{row}  ({saved:.1f}% smaller)")
    print("\nOnly the --compact row enters the context; the schemas stay on disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
