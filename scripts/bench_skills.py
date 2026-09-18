#!/usr/bin/env python3
"""Measure the token cost of your own agent skill catalog.

This is the reproduction path behind the "Bill 3" numbers in README.md. It walks a
skill source directory and counts, with the real OpenAI BPE tokenizer (cl100k_base,
the same encoding the tool-schema benchmark uses):

  * every SKILL.md in full (what an agent pays if it loads the catalog)
  * only each skill's frontmatter `description` (what a catalog listing costs)
  * `mcptoon skills manifest` (the one line mcptoon keeps resident)
  * `mcptoon skills resolve "<query>" --k N` (what a single lookup costs)

tiktoken is a third-party package on purpose: this is a measurement tool, not part
of the zero-dependency runtime. Install it first:

    pip install tiktoken

Usage:
    python scripts/bench_skills.py
    python scripts/bench_skills.py --roots ~/skills --k 5
    python scripts/bench_skills.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"_index", ".git", "__pycache__", "node_modules", ".DS_Store"}
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def tokenizer():
    """Return (encode_fn, name). Falls back loudly so a wrong number is never silent."""
    try:
        import tiktoken
    except ImportError:
        print("! tiktoken is not installed - falling back to chars/4.", file=sys.stderr)
        print("! These numbers are NOT the README caliber. Run: pip install tiktoken",
              file=sys.stderr)
        return (lambda s: max(1, round(len(s) / 4))), "chars/4 (fallback)"

    enc = tiktoken.get_encoding("cl100k_base")
    return (lambda s: len(enc.encode(s))), "tiktoken cl100k_base"


def collect(root: Path):
    """Return (full_text, descriptions, slugs, n_skills) for a skill source directory.

    Counts exactly what the catalog manager manages: `root/<skill>/SKILL.md`, one
    level deep. A recursive walk finds more files (nested bundles ship sub-skills
    under `skills/`), but those are not separately managed skills, and quoting a
    count that depends on the walker would make the README's number ambiguous.
    """
    full, descs, slugs = [], [], []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in SKIP_DIRS or child.name.startswith("."):
            continue
        md = child / "SKILL.md"
        if not md.is_file():
            continue
        slugs.append(child.name)
        text = md.read_text(encoding="utf-8", errors="replace")
        full.append(text)
        m = FRONTMATTER.match(text)
        if m:
            d = re.search(r"^description:\s*(.+?)(?=^\w+:|\Z)", m.group(1),
                          re.S | re.M)
            if d:
                descs.append(" ".join(d.group(1).split()))
    return "\n".join(full), descs, slugs, len(full)


def run_cli(args: list[str]) -> str:
    r = subprocess.run([sys.executable, "-m", "mcptoon", *args],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+",
                    default=[str(Path.home() / ".claude" / "skills")],
                    help="skill source directories (default: ~/.claude/skills)")
    ap.add_argument("--query", default="make a PDF", help="query for the resolve probe")
    ap.add_argument("-k", type=int, default=5, help="resolve shortlist size")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    encode, tokname = tokenizer()

    roots = [Path(r).expanduser() for r in args.roots]
    roots = [r for r in roots if r.is_dir()]
    if not roots:
        print("No skill source directory found. Pass --roots <dir>.", file=sys.stderr)
        return 1

    full_text, descs, slugs, n = "", [], [], 0
    for r in roots:
        t, d, sl, c = collect(r)
        full_text += "\n" + t
        descs += d
        slugs += sl
        n += c

    full_tok = encode(full_text)
    desc_tok = sum(encode(d) for d in descs) if descs else 0
    names_tok = encode(" ".join(slugs))
    manifest_tok = encode(run_cli(["skills", "manifest"]).strip())
    resolve_tok = encode(run_cli(["skills", "resolve", args.query, "--k", str(args.k), "--json"]))

    def pct(a, b):
        # Two decimals would round 39/961,164 to "100.0%", which reads as a typo.
        # Three decimals keeps the honest 99.996%.
        return round((1 - a / b) * 100, 3) if b else None

    out = {
        "tokenizer": tokname,
        "roots": [str(r) for r in roots],
        "skills": n,
        "full_body_tokens": full_tok,
        "description_only_tokens": desc_tok,
        "name_index_tokens": names_tok,
        "manifest_tokens": manifest_tok,
        "resolve_k_tokens": resolve_tok,
        "resolve_k": args.k,
        "manifest_vs_full_pct": pct(manifest_tok, full_tok),
        "resolve_vs_full_pct": pct(resolve_tok, full_tok),
        "description_only_vs_full_pct": pct(desc_tok, full_tok),
        "name_index_vs_full_pct": pct(names_tok, full_tok),
        "windows_128k": round(full_tok / 131072, 2),
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"tokenizer: {tokname}")
    print(f"roots    : {', '.join(out['roots'])}")
    print(f"SKILL.md : {n} files in the source (one level deep; alias dirs included,")
    print(f"           which is what the token cost is charged against)\n")
    print("  what the agent loads                        tokens     vs full")
    print("  " + "-" * 62)
    print(f"  every SKILL.md, full text            {full_tok:>12,}          -")
    print(f"  every skill description only         {desc_tok:>12,}    {out['description_only_vs_full_pct']}%")
    print(f"  every skill NAME only (name index)   {names_tok:>12,}    {out['name_index_vs_full_pct']}%")
    print(f"  mcptoon skills manifest (pointer)    {manifest_tok:>12,}    {out['manifest_vs_full_pct']}%")
    print(f"  mcptoon skills resolve -k {args.k} (one lookup)  {resolve_tok:>12,}    {out['resolve_vs_full_pct']}%")
    print()
    print(f"  the full catalog is {out['windows_128k']} x a 128K context window")
    print()
    print("  NOTE the two different jobs, so the ratio is not misread:")
    print(f"    - manifest ({manifest_tok} tok) is a POINTER: it holds no skill names.")
    print(f"    - the name index ({names_tok:,} tok) is what a skills-as-tool manifest")
    print(f"      would cost: every skill name, still {out['name_index_vs_full_pct']}% below full text.")
    print(f"    - one resolve ({resolve_tok} tok) replaces loading the catalog at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
