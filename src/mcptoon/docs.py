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

"""`mcptoon docs` — index a Markdown tree and route a query to the right file.

Why this exists
---------------
mcptoon already indexes *skills* (``<root>/<slug>/SKILL.md``) and compresses the
*MCP tool catalog*. Both answer "what can this machine do?". Neither answers
"what does this machine's documentation say?" — and that is the largest context
tax of all: an agent that opens a 42 KB ``CONTEXT.md`` pays the whole file every
session, because nothing gives it a cheaper way to find the one paragraph it
needs. Measured on this machine (2026-10-07, live sessions): an agent reading a
monolithic 554-line context file peaks at 40,467 tokens; the same question
against a router-plus-chapters layout peaks at 17,498.

``mcptoon docs`` indexes a directory of Markdown as first-class entries and
routes a query to the few files worth opening. It is the **same** retrieval
engine the skill router uses (BM25 over an index, then a ranked shortlist) —
pointed at documents instead of skills, so a machine gets one ranking behaviour
rather than two that drift.

What it does NOT do, stated so the limits are not mistaken for capabilities
-------------------------------------------------------------------------
- **It finds files; it does not read them.** ``resolve`` returns paths. The agent
  still opens the hit file — that is the point (one file, not nineteen).
- **Descriptions are derived, not authored.** Markdown rarely carries
  frontmatter, so the indexer synthesises a description from the file's own
  headings and opening paragraph, and marks the entry ``derived: true``. A weak
  match can then be told apart from a weak document.
- **No embeddings, no LLM, no network.** BM25 only, offline, instant — the same
  contract ``skills resolve`` keeps.

Design notes
------------
The index is a separate file from the skill index (``docs-index.json`` beside
``skills-index.json``) so the two catalogs never fight over one signature, and a
machine that indexes no docs behaves exactly as before. Roots are de-duplicated
by resolved real path, the same way :func:`mcptoon.skills.scan_roots` does it,
because documentation trees are commonly junctioned into several places.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR
from .skills import _BM25, _clean_desc, _skip_dir

DOCS_INDEX_VERSION = 1

# Markdown files that are packaging boilerplate, not documentation. Indexing
# them would put a dozen near-identical "how to install" files in every catalog
# and dilute the ranking. A caller who really wants one can pass it explicitly.
_SKIP_DOC_STEMS = frozenset({
    "license", "licence", "changelog", "code_of_conduct",
    "security", "notice", "authors", "contributors",
})

_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.M)
# Markdown emphasis left in a heading or a first line — ``**bold**``, ``*it*``,
# `` `code` `` — is noise in a description that is matched by a tokenizer, so it
# is stripped. Kept deliberately narrow: only paired markers, so a stray
# asterisk in prose is left as the author wrote it.
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|`+)(.+?)\1")


def _plain(text: str) -> str:
    """Markdown inline markup removed, whitespace collapsed."""
    text = _EMPHASIS.sub(r"\2", text or "")
    return re.sub(r"\s+", " ", text).strip()


def derive_description(text: str) -> tuple[str, str, list[str]]:
    """Synthesise ``(name, description, triggers)`` from Markdown headings.

    A document rarely carries frontmatter, so the indexer makes its own
    description out of the two things an author always writes: a title heading
    and an opening line. The title is the first heading of *any* level — a
    chapter file conventionally opens at ``##`` (its parent document owns the
    ``#``), and requiring ``#`` would silently leave every such file nameless.
    Every heading in the file becomes a trigger word, because headings are the
    author's own table of contents — exactly the vocabulary a router should
    match against.

    This is a heuristic and is recorded as one (``derived: true`` on the entry).
    It beats an empty description, which would make the file unroutable; it does
    not beat a hand-written one, which frontmatter still wins over.
    """
    text = text or ""
    m = _HEADING.search(text)
    name = _plain(m.group(1)) if m else ""
    body = text[m.end():] if m else text
    first = ""
    for line in body.splitlines():
        s = _plain(line)
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        first = s
        break
    if name and first and first != name:
        desc = f"{name}｜{first}"
    else:
        desc = name or first
    triggers: list[str] = []
    for h in _HEADING.findall(text):
        h = _plain(h)
        if h and h != name and len(h) <= 40 and h not in triggers:
            triggers.append(h)
    return name, desc[:300], triggers[:24]



def _docs_index_path() -> Path:
    """Where the built docs index lives (env-overridable so tests stay hermetic)."""
    return Path(os.environ.get(
        "MCPTOON_DOCS_INDEX", str(CONFIG_DIR / "docs-index.json")))


def _default_docs_roots() -> list[Path]:
    """Roots for a bare ``docs index``.

    Override with ``MCPTOON_DOCS_ROOTS`` (``os.pathsep``-separated). There is no
    guessed default: a documentation tree is a project's own choice, and
    inventing one would index the wrong thing silently. An empty list is the
    honest answer, and the CLI says so instead of scanning the cwd.
    """
    env = os.environ.get("MCPTOON_DOCS_ROOTS", "")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    return []


def _doc_slug(root: Path, path: Path) -> str:
    """A stable, readable slug: the path relative to its root, minus ``.md``.

    Path separators become ``-`` so ``context/18-台账域.md`` under root
    ``context`` is ``18-台账域``, while the same file under ``E:\\openthink`` is
    ``context-18-台账域``. The slug is what a user types back, so it stays
    recognisable rather than hashed.
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    stem = rel.with_suffix("")
    parts = [p for p in stem.parts if p not in ("", ".")]
    return "-".join(parts)


def _iter_doc_files(root: Path):
    """Yield ``(slug, path)`` for every Markdown file under ``root``.

    Skips dot-directories and the usual build noise via the shared
    :func:`mcptoon.skills._skip_dir`, so a docs tree and a skill tree agree on
    what counts as "not part of the catalog". Sorted for a stable walk.
    """
    seen_dirs: set[str] = set()

    def walk(base: Path):
        key = os.path.normcase(os.path.realpath(base))
        if key in seen_dirs:
            return
        seen_dirs.add(key)
        try:
            with os.scandir(base) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=True):
                    if _skip_dir(entry.name):
                        continue
                    yield from walk(Path(entry.path))
                    continue
                if not entry.is_file(follow_symlinks=True):
                    continue
            except OSError:
                continue
            name = entry.name
            if not name.lower().endswith(".md"):
                continue
            if Path(name).stem.lower() in _SKIP_DOC_STEMS:
                continue
            p = Path(entry.path)
            yield _doc_slug(root, p), p

    yield from walk(root)


def scan_docs(roots: list[Path]) -> dict:
    """Build a docs index dict from ``roots``. Read-only; never writes to roots.

    Roots are de-duplicated by resolved real path (a docs tree is often
    junctioned into several agent folders); files are de-duplicated by resolved
    path too, so the same chapter reached through two roots is indexed once.
    """
    docs: list[dict] = []
    warnings: list[dict] = []
    seen_roots: set[str] = set()
    seen_files: set[str] = set()
    seen_slugs: dict[str, str] = {}

    for root in roots:
        if not root.is_dir():
            warnings.append({"code": "ROOT_MISSING",
                             "message": f"docs root not found: {root}"})
            continue
        try:
            root_key = str(root.resolve())
        except OSError:
            root_key = str(root)
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)

        for slug, path in _iter_doc_files(root):
            try:
                file_key = str(path.resolve())
            except OSError:
                file_key = str(path)
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                warnings.append({"code": "DOC_UNREADABLE",
                                 "message": f"{path}: {exc}"})
                continue
            name, desc, triggers = derive_description(text)
            if not desc:
                warnings.append({
                    "code": "DOC_NO_DESC",
                    "message": f"{slug}: no heading and no text — routing will miss it",
                })
            prev = seen_slugs.get(slug.lower())
            if prev is not None:
                warnings.append({
                    "code": "DOC_DUPLICATE",
                    "message": f"{slug}: also found at {prev} — duplicates dilute retrieval",
                })
            else:
                seen_slugs[slug.lower()] = str(path)
            try:
                st = path.stat()
                size, mtime = st.st_size, st.st_mtime_ns
            except OSError:
                size, mtime = 0, 0
            docs.append({
                "slug": slug,
                "name": name or slug,
                "desc": desc,
                "triggers": triggers,
                "path": str(path),
                "root": str(root),
                "size": size,
                "mtime": mtime,
                "derived": True,
            })

    return {
        "version": DOCS_INDEX_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roots": [str(r) for r in roots],
        "signature": docs_signature(roots),
        "docs": docs,
        "warnings": warnings,
    }


def _iter_doc_paths(roots: list[Path]):
    for root in roots:
        if not root.is_dir():
            continue
        for _, p in _iter_doc_files(root):
            yield p


def docs_signature(roots: list[Path]) -> str:
    """A hash of every Markdown file under ``roots``: path, size and mtime.

    Same staleness signal the skill index uses, for the same reason: mtime alone
    cannot see a *deleted* file, and counting files cannot see an edit.
    """
    import hashlib

    rows = []
    for p in _iter_doc_paths(roots):
        try:
            st = p.stat()
        except OSError:
            continue
        rows.append(f"{p}\0{st.st_size}\0{st.st_mtime_ns}")
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def build_docs_and_save(roots: list[Path]) -> tuple[dict, Path]:
    """Scan ``roots`` and write the docs index atomically (tmp + ``os.replace``).

    Atomic for the same reason the skill index is: it is rebuilt on demand,
    possibly while another process reads it, and a reader must see the old index
    or the new one — never a half-written file.
    """
    index = scan_docs(roots)
    path = _docs_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)
    return index, path


def load_docs_index() -> dict:
    """Load the built docs index; ``{}`` when absent or unreadable."""
    path = _docs_index_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _as_rank_index(index: dict) -> dict:
    """Project the docs index into the shape :class:`mcptoon.skills._BM25` reads.

    The ranking engine is shared, not copied: this is the whole adapter. The
    skill ranker reads ``{"skills": [{slug, name, desc, triggers, alias_of}]}``,
    so docs are presented under that key with no alias cards (a document does
    not point at another document).
    """
    rows = []
    for d in index.get("docs", []):
        rows.append({
            "slug": d.get("slug", ""),
            "name": d.get("name") or d.get("slug", ""),
            "desc": d.get("desc", ""),
            "triggers": d.get("triggers") or [],
            "alias_of": "",
            "tools": [],
        })
    return {"skills": rows}


def resolve_docs(query: str, k: int = 5, index: dict | None = None) -> list[dict]:
    """The k best documents for ``query`` — ``[{slug, score, desc, path}]``, best first.

    Returns ``[]`` rather than raising when no index exists, so a machine with
    no docs still answers. The ``path`` is carried through because that is what
    the caller acts on: a slug alone would send the agent looking for the file.
    """
    idx = load_docs_index() if index is None else index
    if not idx or not idx.get("docs"):
        return []
    ranked = _BM25(_as_rank_index(idx)).search(query, k)
    by_slug = {d["slug"]: d for d in idx.get("docs", [])}
    out = []
    for r in ranked:
        d = by_slug.get(r["slug"], {})
        out.append({
            "slug": r["slug"],
            "score": r["score"],
            "desc": r["desc"],
            "path": d.get("path", ""),
            "size": d.get("size", 0),
        })
    return out


def docs_are_stale(index: dict) -> bool:
    """True when the docs on disk no longer match the index (or it has none)."""
    if not index or not index.get("signature"):
        return True
    roots = [Path(r) for r in index.get("roots", [])]
    if not roots:
        return False
    try:
        return docs_signature(roots) != index["signature"]
    except OSError:
        return False


# ═══════════════════════════════════════════════════
# CLI surface
# ═══════════════════════════════════════════════════

_DOCS_USAGE = """mcptoon docs — index a Markdown tree and route a query to the right file

    mcptoon docs index <dir> [<dir>...]   Index Markdown under one or more roots
    mcptoon docs resolve "<query>"        Best files for a query (paths included)
    mcptoon docs resolve "<q>" --k 3      How many to return (default 5)
    mcptoon docs resolve "<q>" --json     Machine-readable
    mcptoon docs list                     Every indexed document, by slug
    mcptoon docs stats                    Catalog health (counts, derived descs)
    mcptoon docs doctor                   Check the index against the disk
    mcptoon docs clear                    Delete the docs index (reversible)

Why: an agent that opens a whole 42 KB context file pays for all of it every
session. `resolve` returns the two or three files worth opening instead, so the
agent reads one chapter — not nineteen. It finds files; it does not read them.
"""


def _flag_value(rest: list[str], name: str, default: str = "") -> str:
    for i, a in enumerate(rest):
        if a == name and i + 1 < len(rest):
            return rest[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _parse_k(rest: list[str], default: int = 5) -> int:
    raw = _flag_value(rest, "--k", "")
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _positional(rest: list[str]) -> list[str]:
    """Args that are not flags and not a flag's value."""
    out, skip = [], False
    for i, a in enumerate(rest):
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            if a in ("--k", "--query", "--dir") and i + 1 < len(rest):
                skip = True
            continue
        out.append(a)
    return out


def _human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _cmd_index(args: list[str], fmt: str) -> None:
    roots = [Path(a).expanduser() for a in _positional(args)]
    if not roots:
        roots = _default_docs_roots()
    if not roots:
        print("mcptoon: no docs roots. Pass a path: mcptoon docs index <dir> "
              "(or set MCPTOON_DOCS_ROOTS)", file=sys.stderr)
        sys.exit(1)
    index, path = build_docs_and_save(roots)
    n = len(index["docs"])
    total = sum(d.get("size", 0) for d in index["docs"])
    if fmt == "json":
        print(json.dumps({"indexed": n, "roots": index["roots"],
                          "index": str(path), "bytes": total,
                          "warnings": index["warnings"]},
                         ensure_ascii=False, indent=1))
        return
    print(f"indexed {n} documents ({_human(total)}) from {len(index['roots'])} root(s)")
    print(f"index: {path}")
    if index["warnings"]:
        print(f"warnings: {len(index['warnings'])} "
              f"(run 'mcptoon docs doctor' for detail)")


def _cmd_resolve(args: list[str], fmt: str) -> None:
    query = _flag_value(args, "--query", "") or " ".join(_positional(args))
    if not query:
        print("mcptoon: resolve needs a query", file=sys.stderr)
        sys.exit(1)
    k = _parse_k(args)
    index = load_docs_index()
    if not index:
        print("mcptoon: no docs index yet. Run: mcptoon docs index <dir>",
              file=sys.stderr)
        sys.exit(1)
    hits = resolve_docs(query, k, index=index)
    if fmt == "json":
        print(json.dumps({"query": query, "k": k, "hits": hits},
                         ensure_ascii=False, indent=1))
        return
    if not hits:
        print(f"no document matches {query!r}")
        return
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h['slug']}  ({h['score']})")
        if h["desc"]:
            print(f"   {h['desc'][:110]}")
        if h["path"]:
            print(f"   -> {h['path']}")
    print(f"\nOpen only the file(s) you need — not all {len(index['docs'])}.")


def _cmd_list(args: list[str], fmt: str) -> None:
    index = load_docs_index()
    if not index:
        print("mcptoon: no docs index yet. Run: mcptoon docs index <dir>",
              file=sys.stderr)
        sys.exit(1)
    rows = sorted(index.get("docs", []), key=lambda d: d.get("slug", ""))
    if fmt == "json":
        print(json.dumps([{"slug": d["slug"], "desc": d.get("desc", ""),
                           "path": d.get("path", "")} for d in rows],
                         ensure_ascii=False, indent=1))
        return
    print(f"{len(rows)} documents")
    for d in rows:
        print(f"  {d['slug']:<34} {_clean_desc(d.get('desc', ''))[:70]}")


def _cmd_stats(args: list[str], fmt: str) -> None:
    index = load_docs_index()
    if not index:
        print("mcptoon: no docs index yet. Run: mcptoon docs index <dir>",
              file=sys.stderr)
        sys.exit(1)
    docs = index.get("docs", [])
    total = sum(d.get("size", 0) for d in docs)
    no_desc = [d["slug"] for d in docs if not (d.get("desc") or "").strip()]
    stale = docs_are_stale(index)
    payload = {
        "documents": len(docs),
        "roots": index.get("roots", []),
        "bytes": total,
        "avg_bytes": round(total / len(docs)) if docs else 0,
        "no_description": no_desc,
        "stale": stale,
        "built_at": index.get("built_at", ""),
        "warnings": len(index.get("warnings", [])),
    }
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return
    print(f"documents   : {len(docs)}")
    print(f"total size  : {_human(total)} (avg {_human(payload['avg_bytes'])})")
    print(f"roots       : {len(index.get('roots', []))}")
    print(f"built at    : {index.get('built_at', '—')}")
    print(f"stale       : {'yes — run: mcptoon docs index <dir>' if stale else 'no'}")
    if no_desc:
        print(f"no desc     : {len(no_desc)} (unroutable: {', '.join(no_desc[:5])})")
    if index.get("warnings"):
        print(f"warnings    : {len(index['warnings'])}")


def _cmd_doctor(args: list[str], fmt: str) -> None:
    index = load_docs_index()
    problems: list[str] = []
    if not index:
        print("docs index: absent")
        print("  fix: mcptoon docs index <dir>")
        sys.exit(1)
    docs = index.get("docs", [])
    missing = [d["slug"] for d in docs if d.get("path") and not Path(d["path"]).is_file()]
    if missing:
        problems.append(f"{len(missing)} indexed file(s) no longer on disk "
                        f"(e.g. {missing[0]})")
    if docs_are_stale(index):
        problems.append("index is stale (a file was added, edited or deleted)")
    no_desc = [d["slug"] for d in docs if not (d.get("desc") or "").strip()]
    if no_desc:
        problems.append(f"{len(no_desc)} document(s) have no description — "
                        f"routing will miss them")
    dupes = [w for w in index.get("warnings", []) if w.get("code") == "DOC_DUPLICATE"]
    if dupes:
        problems.append(f"{len(dupes)} duplicate slug(s) — duplicates dilute retrieval")
    if fmt == "json":
        print(json.dumps({"documents": len(docs), "problems": problems},
                         ensure_ascii=False, indent=1))
        return
    print(f"docs index: {len(docs)} documents from {len(index.get('roots', []))} root(s)")
    if not problems:
        print("all checks passed")
        return
    for p in problems:
        print(f"  ! {p}")
    print("\nfix: mcptoon docs index <dir>")


def _cmd_clear(args: list[str], fmt: str) -> None:
    path = _docs_index_path()
    if not path.is_file():
        print("docs index: nothing to clear")
        return
    try:
        path.unlink()
    except OSError as exc:
        print(f"mcptoon: could not remove {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"removed {path}")
    print("reversible: rebuild with 'mcptoon docs index <dir>'")


def run(rest: list[str], fmt: str = "auto", head_n: int = 0, max_chars: int = 0,
        full: bool = False) -> None:
    """CLI entry: `mcptoon docs <action> [...]`.

    ``head_n``/``max_chars``/``full`` are the global output flags, accepted so
    they are not silently ignored on this command.
    """
    action = rest[0] if rest else ""
    args = rest[1:]

    if action in ("", "help", "-h", "--help"):
        print(_DOCS_USAGE)
        return
    if action == "index":
        _cmd_index(args, fmt)
        return
    if action in ("resolve", "route", "search"):
        _cmd_resolve(args, fmt)
        return
    if action == "list":
        _cmd_list(args, fmt)
        return
    if action == "stats":
        _cmd_stats(args, fmt)
        return
    if action == "doctor":
        _cmd_doctor(args, fmt)
        return
    if action in ("clear", "reset"):
        _cmd_clear(args, fmt)
        return

    print(f"mcptoon: unknown docs action {action!r}", file=sys.stderr)
    print(_DOCS_USAGE, file=sys.stderr)
    sys.exit(1)
