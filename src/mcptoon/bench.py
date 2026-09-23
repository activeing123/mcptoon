# Copyright 2025-2026 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""``mcptoon bench`` — prove the savings on your own machine, both halves.

One command, one table, the whole pitch: what an agent would load natively
versus what it loads through mcptoon.

    MCP tools   every full schema        vs  manifest (names)  vs  manifest --slim
    Skills      every SKILL.md, full text vs  skills manifest  vs  resolve --k 5

Why this exists next to ``scripts/bench_tokens.py`` and ``scripts/bench_skills.py``:
those are *repository* tools (tiktoken, a clone, a separate run each). A user who
just ran ``pip install mcptoon`` cannot run either one, so the proof was only ever
available to someone who already trusted us. This ships in the wheel, needs no
network, and covers both halves in a single call.

Two honesty rules this module is built around:

1. **Never mix calibers.** With tiktoken installed the numbers are the ones the
   README quotes. Without it, a ``len//4`` estimate is used and *labelled* as an
   estimate — silently swapping them would make the table a lie.
2. **Never double-count a junction.** A machine where several agent folders are
   junctions onto one real skills directory is the *normal* multi-agent layout, and
   walking each root naively inflates the catalog by the number of links (4x on the
   reference machine). Roots and files are de-duplicated by real ``SKILL.md`` path
   first, and the skipped duplicate roots are reported rather than hidden.

   The walk is **recursive**, because skills nest: a one-level walk silently hid 30
   of this machine's 406 skills (the whole ``video-seedance`` sub-family) and made
   ``bench`` disagree with ``skills index`` by exactly that much. A bench that
   measures a *different* catalog than the manager serves is worse than no bench,
   so the two now walk the same way.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# A 128K context window, in tokens — the yardstick the closing line divides by.
_WINDOWS_128K = 131072


def _dedup_roots(roots: list[Path]) -> tuple[list[Path], int]:
    """Roots with junctions collapsed, and how many alias roots were dropped.

    Roots are de-duplicated by *resolved* real path so the same catalog reached
    through several agent folders is walked once. That is the whole point of the
    number ``dupes`` reports, and it is why the note says "roots" rather than
    "files": a junction farm is a root-level alias, not a duplicated skill.

    The count is deliberately ``roots seen - distinct real paths`` (i.e. the
    number of alias roots), not "SKILL.md files skipped mid-walk". Both used to
    be the same number when the walk was one level deep, so the note could not
    tell them apart; once the walk became recursive the mid-walk skip count
    inflated with every nested duplicate and stopped meaning anything.
    """
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique, len(roots) - len(unique)


def _unique_skill_files(roots: list[Path]):
    """Yield ``(slug, skill_md_path)`` once per *real* file.

    **Recursive**, matching what the catalog manager (``skills index`` /
    ``scan_roots``) treats as a managed skill, and accepting both layouts seen in
    the wild (``<root>/<slug>`` and ``<root>/skills/<slug>``). It used to be one
    level deep, which undercounted nested sub-catalogs — on this machine it hid
    the entire ``video-seedance`` family and printed 376 where the catalog had
    406. Roots are de-duplicated by resolved path first (see ``_dedup_roots``) so
    a junction farm counts each SKILL.md exactly once; files are de-duplicated by
    real path too, so a catalog reachable by two distinct roots cannot
    double-count either.

    Returns ``(files, dupes)`` where ``dupes`` is the number of alias *roots*
    dropped, not files skipped.
    """
    from . import skills as sk

    unique, dupes = _dedup_roots(roots)
    seen_files: set[str] = set()
    out: list[tuple[str, Path]] = []
    for root in unique:
        if not root.is_dir():
            continue
        for slug, md in sk._iter_skill_dirs(root):
            try:
                key = str(md.resolve())
            except OSError:
                key = str(md)
            if key in seen_files:
                continue
            seen_files.add(key)
            out.append((slug, md))
    return out, dupes


# ═══════════════════════════════════════════════════
# Tokenizer
# ═══════════════════════════════════════════════════

def _tokenizer():
    """Return ``(encode, name, exact)``.

    ``exact`` is False for the fallback so callers can label the numbers instead
    of letting an estimate pass as a measurement.
    """
    try:
        import tiktoken  # optional: never a hard dependency
    except ImportError:
        def encode(text: str) -> int:
            return max(1, round(len(text) / 4))
        return encode, "chars/4 estimate (pip install tiktoken for the README caliber)", False

    enc = tiktoken.get_encoding("cl100k_base")
    return (lambda text: len(enc.encode(text))), "tiktoken cl100k_base", True


def _pct(part: int, whole: int):
    """Percent saved, or None when there is no baseline to compare against."""
    if not whole:
        return None
    return round((1 - part / whole) * 100, 3)


# ═══════════════════════════════════════════════════
# MCP tools half
# ═══════════════════════════════════════════════════

def _load_cached_tools() -> dict:
    """Read the on-disk schema cache directly.

    Deliberately not ``cache.get_cached_tools()``: a measurement must see the
    schemas actually on disk, not obey the runtime freshness TTL.
    """
    from .config import CACHE_DIR

    cache_file = CACHE_DIR / "schema_cache.json"
    if not cache_file.exists():
        return {}
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {name: entry["tools"] for name, entry in cache.items() if entry.get("tools")}


def _tool_rows(encode):
    """Return ``(rows, n_tools, n_servers)`` for the MCP-tools half."""
    from .output import compact, slim_toon

    tools = _load_cached_tools()
    flat = [t for server in tools.values() for t in server if "error" not in t]
    if not flat:
        return [], 0, 0

    native = json.dumps(
        [
            {
                "name": t.get("name"),
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema") or t.get("parameters") or {},
            }
            for t in flat
        ],
        ensure_ascii=False,
    )
    # compact() on a *list* truncates to 30 names, which would understate the
    # saving by orders of magnitude; the manifest shape has no such limit.
    names = compact(
        {s: [t.get("name", "") for t in ts if "error" not in t]
         for s, ts in tools.items() if any("error" not in t for t in ts)}
    )
    rows = [
        ("native: every full schema", encode(native)),
        ("manifest (name index)", encode(names)),
        ("manifest --slim", encode(slim_toon(flat))),
    ]
    return rows, len(flat), len(tools)


# ═══════════════════════════════════════════════════
# Skills half
# ═══════════════════════════════════════════════════

def _skill_rows(encode, roots, query, k):
    """Return ``(rows, n_skills, dupes, resolve_note)`` for the skills half."""
    from . import skills as sk

    files, dupes = _unique_skill_files(roots)
    if not files:
        return [], 0, 0, "no skill catalog found"

    bodies = []
    for _slug, md in files:
        try:
            bodies.append(md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

    # Join exactly the way scripts/bench_skills.py accumulates it (a "\n" before
    # every body, not just between), so this prints the same resident number the
    # README quotes and the two repo tools can never disagree by a token.
    native = encode("\n" + "\n".join(bodies))
    pointer = encode(sk.MANIFEST_ENTRY)

    resolve_tok, note = None, ""
    index = sk.load_index()
    if index:
        shortlist = sk._BM25(index).search(query, k)
        if shortlist:
            declared = sk._BM25(index).declared_tools(shortlist)
            payload = json.dumps(
                {"query": query, "k": k, "shortlist": shortlist,
                 "declared_tools": declared, "tools": []},
                ensure_ascii=False, indent=1,
            )
            resolve_tok = encode(payload)
        else:
            note = f"no skill matched {query!r}"
    else:
        note = "run 'mcptoon skills index' for the resolve row"

    rows = [
        ("native: every SKILL.md, full text", native),
        ("skills manifest (pointer)", pointer),
    ]
    if resolve_tok is not None:
        rows.append((f"skills resolve --k {k} (one lookup)", resolve_tok))
    return rows, len(files), dupes, note


# ═══════════════════════════════════════════════════
# Rendering
# ═══════════════════════════════════════════════════

def _render(tokname, exact, tool_rows, n_tools,
            skill_rows, n_skills, dupes, note, query, roots):
    lines = [f"mcptoon bench — {tokname}", ""]
    if not exact:
        lines += ["  ! these are estimates, not the README's tiktoken numbers", ""]

    header = (f"  {'half':<13} {'what the agent loads':<38} {'tokens':>11} {'vs native':>11}")
    rule = "  " + "-" * (len(header) - 2)
    lines += [header, rule]

    for label, count, rows in (
        (f"MCP tools ({n_tools})", n_tools, tool_rows),
        (f"Agent skills ({n_skills})", n_skills, skill_rows),
    ):
        if not rows:
            continue
        base = rows[0][1]
        for i, (what, tok) in enumerate(rows):
            first = label if i == 0 else ""
            saved = "-" if i == 0 else (
                f"{_pct(tok, base):.1f}%" if _pct(tok, base) is not None else "-")
            lines.append(f"  {first:<13} {what:<38} {tok:>11,} {saved:>11}")
        lines.append("")

    if dupes:
        lines.append(f"  note: {dupes} duplicate root path(s) skipped "
                     f"({len(roots)} roots -> {n_skills} unique skills)")
    if note:
        lines.append(f"  note: {note}")
    if skill_rows:
        lines.append(f"  query: {query!r}   (the resolve row depends on it)")
        lines.append("  caliber: recursive (nested sub-catalogs counted), `_index` "
                     "excluded, roots de-duplicated by real path")
    lines.append("")
    if skill_rows and skill_rows[0][1]:
        lines.append(f"  {skill_rows[0][1]:,} tokens of skill text is "
                     f"{skill_rows[0][1] / _WINDOWS_128K:.2f} x 128K windows "
                     "an agent would have to hold.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════

def _roots_from(rest: list[str]) -> list[Path]:
    from . import skills as sk

    for i, a in enumerate(rest):
        if a == "--roots":
            vals = [v for v in rest[i + 1:] if not v.startswith("-")]
            return [Path(v).expanduser() for v in vals]
        if a.startswith("--roots="):
            return [Path(p).expanduser()
                    for p in a.split("=", 1)[1].split(os.pathsep) if p.strip()]
    return list(sk._default_roots())


def _flag(rest: list[str], name: str, default: str) -> str:
    for i, a in enumerate(rest):
        if a == name and i + 1 < len(rest):
            return rest[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def run_bench(rest: list[str], fmt: str = "auto") -> None:
    """Measure both halves and print one table (or JSON)."""
    encode, tokname, exact = _tokenizer()
    roots = _roots_from(rest)
    query = _flag(rest, "--query", "make a PDF")
    try:
        k = int(_flag(rest, "-k", "5") or 5)
    except ValueError:
        k = 5

    tool_rows, n_tools, n_servers = _tool_rows(encode)
    skill_rows, n_skills, dupes, note = _skill_rows(encode, roots, query, k)

    if not tool_rows and not skill_rows:
        print("Nothing to measure yet.")
        print("  MCP tools: run `mcptoon manifest` once to fetch the schemas")
        print("  Skills   : run `mcptoon skills index` to build the catalog index")
        return

    if fmt == "json":
        print(json.dumps(
            {
                "tokenizer": tokname,
                "exact": exact,
                "tools": {"servers": n_servers, "count": n_tools,
                          "rows": {w: t for w, t in tool_rows}},
                "skills": {"roots": [str(r) for r in roots], "count": n_skills,
                           "duplicates_skipped": dupes, "query": query, "k": k,
                           "rows": {w: t for w, t in skill_rows},
                           "note": note},
            },
            ensure_ascii=False, indent=2,
        ))
        return

    print(_render(tokname, exact, tool_rows, n_tools,
                  skill_rows, n_skills, dupes, note, query, roots))
