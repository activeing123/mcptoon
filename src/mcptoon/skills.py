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

"""
mcptoon skills — skill-catalog index + compression-safe routing.

The problem
-----------
An agent's skill catalog is a fixed tax: every skill's ``name: description``
sits in the session context whether it is used or not. Trimming it to bare
names saves ~93% of the tokens but costs about half the routing accuracy,
because skill names are often not self-explanatory (``houtai`` is a backend,
``kao`` is a memory quiz, ``tu-kami`` is PDF typesetting) — unlike MCP tool
names, which read as verbs.

The fix
-------
Do not compress what the model sees; move the full catalog out of context and
retrieve from it:

  1. ``index``   — scan skill roots, keep slug/description/triggers/aliases on
                   disk. Never injected into the session.
  2. ``resolve`` — zero-dependency BM25 shortlist over that index. Deterministic,
                   no LLM, no tokens. Correct skill lands in the top-5.
  3. ``route``   — hand only the shortlist (5 items, not 370) to an LLM to pick.
  4. ``manifest``— the tiny entry an agent keeps in context: how to call the above.

Measured on a 370-skill / 40-task set (see the skills-unify scratch report):
names-only single-shot routing 37.5% strict, shortlist-then-pick 87.5%, and a
4-model vote over the same shortlist 100%. The shortlist stage alone is 100%
recall when aliases are resolved.

Zero dependencies: standard library only.
"""
import hashlib
import json
import math
import os
import re
import shutil
import stat as _stat
import subprocess
import sys
import threading
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import CONFIG_DIR

INDEX_VERSION = 1


# ═══════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════

def _index_path() -> Path:
    """Where the built index lives (env-overridable so tests stay hermetic)."""
    return Path(os.environ.get(
        "MCPTOON_SKILLS_INDEX", str(CONFIG_DIR / "skills-index.json")))


def _gloss_path() -> Path:
    """Where the optional per-slug extra search terms live.

    Defaults to sitting beside the index, so one directory holds everything the
    catalog needs. Env-overridable for the same reason the index is.
    """
    env = os.environ.get("MCPTOON_SKILLS_GLOSS")
    if env:
        return Path(env)
    return _index_path().parent / "skills-gloss.json"


def _load_json_file(path: Path) -> dict:
    """Read a JSON object, or ``{}`` for anything unreadable or non-object."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _load_gloss() -> dict[str, list[str]]:
    """Extra search terms per slug: ``{slug: [term, ...]}``.

    A skill described only in English is unreachable from a Chinese request:
    ``_tokenize`` matches ASCII words plus CJK unigrams and bigrams, and an
    English document contains no CJK whatsoever, so there is nothing for the
    query to match. This sidecar gives the catalog the missing language without
    editing the skill file — which matters here because the affected skills are
    vendored (the ``seedance`` family ships as an upstream pack at
    ``metadata.version 6.6.0``) and ``skills sync``'s version gate treats any
    content change as a release that needs a version bump.

    The file ships absent, and is never fatal: a missing, unreadable or
    malformed gloss means "no extra terms", not a broken catalog.
    """
    out: dict[str, list[str]] = {}
    for slug, terms in _load_json_file(_gloss_path()).items():
        if isinstance(terms, list):
            out[str(slug).lower()] = [str(t) for t in terms if str(t).strip()]
    return out


def _clean_desc(desc: str) -> str:
    """A description with any surrounding YAML quotes removed.

    The indexer stores the raw frontmatter value, which for many skills is
    YAML-quoted (``description: "…"``). Both the rendered output and BM25 must
    see the same cleaned text, so a description is never quoted in one place and
    bare in another. Only a matching pair at the very start/end is stripped —
    internal quotes are content and are preserved.
    """
    desc = desc or ""
    if len(desc) >= 2 and desc[0] == desc[-1] and desc[0] in ("'", '"'):
        return desc[1:-1]
    return desc


def _default_roots() -> list[Path]:
    """Common agent skill roots, most-specific first.

    Override with ``MCPTOON_SKILLS_ROOTS`` (``os.pathsep``-separated) or pass
    explicit roots to ``skills index``.
    """
    env = os.environ.get("MCPTOON_SKILLS_ROOTS", "")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    home = Path.home()
    candidates = [
        home / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
    ]
    return [p for p in candidates if p.is_dir()]


def _view_roots() -> list[Path]:
    """Every agent skill folder a synced catalog should appear in.

    Unlike :func:`_default_roots` this does not require the folder to exist yet
    — sync creates it. ``MCPTOON_SKILLS_VIEWS`` (``os.pathsep``-separated)
    overrides, which is what tests use to stay in a sandbox.
    """
    env = os.environ.get("MCPTOON_SKILLS_VIEWS", "")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    home = Path.home()
    return [
        home / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
        home / ".catpaw" / "skills",
        home / ".codeium" / "windsurf" / "skills",
    ]


# ═══════════════════════════════════════════════════
# Scanning
# ═══════════════════════════════════════════════════

def _triggers(desc: str) -> list[str]:
    """Pull trigger words out of a description.

    Descriptions carry them as ``触发词：/a、b、c`` or ``Triggers: x / y``. The
    router needs them because a bare skill name is frequently uninformative.
    """
    m = re.search(r"(?:触发词|触发|Triggers?)\s*[:：]\s*(.+)", desc or "", re.I)
    if not m:
        return []
    parts = re.split(r"[、,，/|;；\s]+", m.group(1))
    out = []
    for p in parts:
        p = p.strip().lstrip("/").strip()
        if p and len(p) <= 24 and p not in out:
            out.append(p)
    return out


def _alias_target(desc: str) -> str:
    """``别名转发：/archify → /tu-archify`` yields ``tu-archify``; else ``""``.

    Alias cards are pointer stubs. Left unresolved they compete with their own
    target in retrieval and split the vote.
    """
    if "别名转发" not in (desc or ""):
        return ""
    m = re.search(r"→\s*/?([A-Za-z0-9_\-]+)", desc)
    return m.group(1).lower() if m else ""


def _split_terms(text: str, keep_whole: bool = False) -> list[str]:
    """Split a trigger line into individual terms.

    ``keep_whole`` is for list items: a short item with no separator is one term
    (``做 PDF``, ``landing page``), not two — splitting on whitespace would shred
    multi-word triggers.
    """
    text = (text or "").strip()
    if keep_whole and text and len(text) <= 24 and not re.search(r"[、,，/|;；]", text):
        return [text.lstrip("/").strip()]
    return [p.strip().lstrip("/").strip()
            for p in re.split(r"[、,，/|;；\s]+", text) if p.strip()]


def _declared_tools(md, frontmatter_parser) -> list[str]:
    """The tools a skill declares in its frontmatter, normalised to a list.

    A skill is a playbook, and a playbook usually needs instruments. Declaring
    them lets one search turn hand back both the skill and its toolkit, instead
    of the agent finding the skill and then hunting for the tools.

    Both spellings seen in the wild are read — ``tools:`` and the Agent Skills
    ``allowed-tools:`` — and a permission scope is stripped, so
    ``Bash(opencli:*)`` contributes ``Bash``.
    """
    try:
        fm = frontmatter_parser(md)
    except OSError:
        return []
    raw = fm.get("tools") or fm.get("allowed-tools") or []
    if isinstance(raw, str):
        raw = raw.split(",")
    out: list[str] = []
    seen = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        name = re.sub(r"\(.*\)\s*$", "", t).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _body_triggers(body: str) -> list[str]:
    """Mine retrieval terms from a SKILL.md *body*.

    Retrieval quality is otherwise hostage to how well each author wrote the
    frontmatter description — and most authors do not write one well. Measured on
    this machine's catalog: stripping the trigger clause from descriptions drops
    top-1 recall from 92.5% to 80%, and this recovery puts it back at 95%.

    Triggers, slash-commands and headings are already written down for humans;
    this reads them back so the router can use them. The file is untouched.
    Authors write triggers two ways — ``触发词：a、b`` on one line, or a
    ``## 触发词`` heading followed by a list — so both are handled.
    """
    body = body or ""
    found: list[str] = []
    lines = body.splitlines()
    # A trigger declaration starts the line (after markdown markers). Requiring the
    # anchor matters: "正文也没有触发词" is a *negative* sentence, not a declaration,
    # and reading it as one would invent triggers out of prose.
    decl = re.compile(r"^\s*(?:[-*•]\s*|\d+[.)]\s*|#{1,6}\s*)*(?:触发词|触发|Triggers?)\s*[:：]?\s*(.*)$",
                      re.I)
    i = 0
    while i < len(lines):
        m = decl.match(lines[i])
        if m:
            if m.group(1):
                found += _split_terms(m.group(1))
            # continuation: list items / short or separator-bearing lines, until a
            # heading or the blank line that ends the block
            j, taken = i + 1, 0
            while j < len(lines) and taken < 12:
                nxt = lines[j].strip()
                if not nxt:
                    if taken:
                        break
                    j += 1
                    continue
                if nxt.startswith("#") or decl.match(lines[j]):
                    break
                is_item = bool(re.match(r"^[-*•]\s+|^\d+[.)]\s+", nxt))
                if is_item or len(nxt) <= 24 or re.search(r"[、,，/|;；]", nxt):
                    found += _split_terms(
                        re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", nxt), keep_whole=is_item)
                    taken += 1
                    j += 1
                else:
                    break
            i = j
            continue
        i += 1
    found += re.findall(r"/([a-z][a-z0-9\-]{2,})", body)
    found += [h.strip() for h in re.findall(r"^#{1,3}\s+(.+)$", body, re.M)]
    out: list[str] = []
    seen = set()
    for t in found:
        t = t.strip()
        low = t.lower()
        if 1 < len(t) <= 30 and low not in seen and not re.fullmatch(r"触发词|触发|triggers?", low):
            seen.add(low)
            out.append(t)
    return out[:40]


def _walk_skill_dirs(base: Path, seen: set[str]):
    """Yield ``(slug, skill_md_path)`` anywhere under ``base``, depth-first.

    Skills nest: a catalog ships sub-catalogs (``<skill>/skills/<slug>/``) and
    bundled examples. A one-level walk indexed 376 of this machine's 405 skills
    and silently hid the other 29 — including the whole ``video-seedance``
    sub-family, which is the reason a one-line catalog entry can point at a
    family at all. Directories are visited once by resolved real path, so a
    junction pointing back into the tree cannot loop.

    ``os.scandir`` rather than ``iterdir``: it answers ``is_dir`` from the
    directory entry it already read instead of a fresh ``stat`` per child, which
    is the difference between a 350ms and a 50ms walk of this machine's catalog.
    The dedup key is ``realpath``, not ``st_ino`` — Windows reports ``st_ino``
    as 0 for junctions, so an inode key would collapse every junction onto one
    and silently drop the skills behind it.
    """
    dkey = os.path.normcase(os.path.realpath(base))
    if dkey in seen:
        return
    seen.add(dkey)
    try:
        with os.scandir(base) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=True):
                continue
        except OSError:
            continue
        if _skip_dir(entry.name):
            continue
        child = Path(entry.path)
        md = _find_skill_md(child)
        if md is not None:
            yield entry.name, md
        yield from _walk_skill_dirs(child, seen)


def _find_skill_md(directory: Path) -> Path | None:
    """The skill manifest in ``directory``, or None. Case-insensitive on name.

    One ``stat`` on the canonical spelling first — it hits for 386 of this
    machine's 407 skills, and on Windows it also answers for the 21 that spell
    the name ``skill.md``, because NTFS folds case. Only when that fails (i.e.
    on a case-sensitive filesystem holding a lower-case manifest) is the
    directory listed, which is the expensive path and therefore the rare one.

    Case folding is not decoration: 21 skills here ship ``skill.md``, and a
    strict ``== "SKILL.md"`` silently dropped every one of them. ``child /
    "SKILL.md"`` alone would find them on Windows and miss them on Linux, so the
    catalog would differ by platform; both spellings are accepted explicitly.
    """
    canonical = directory / "SKILL.md"
    if canonical.is_file():
        return canonical
    try:
        names = [e.name for e in os.scandir(directory)]
    except OSError:
        return None
    for name in names:
        if name.lower() == "skill.md":
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _iter_skill_dirs(root: Path):
    """Yield ``(slug, skill_md_path)`` for one root, recursively.

    Accepts both layouts seen in the wild — ``<root>/<slug>/SKILL.md`` and
    ``<root>/skills/<slug>/SKILL.md`` — and keeps descending past a skill
    directory, because a skill may carry nested skills of its own. The second
    layout is usually already inside the first, and sharing one ``seen`` set is
    what keeps it from being walked twice.
    """
    seen: set[str] = set()
    for base in (root, root / "skills"):
        if not base.is_dir():
            continue
        yield from _walk_skill_dirs(base, seen)


def scan_roots(roots: list[Path]) -> dict:
    """Build an index dict from skill roots. Read-only; never writes to roots.

    Roots are de-duplicated by resolved real path first, the same way ``bench``
    does it. Agent skill folders are commonly junctions onto one real catalog, so
    a naive walk would index the catalog once per alias and emit a
    ``SKILL_DUPLICATE`` per file — noise, not a real conflict. A machine with no
    aliases sees no change, because distinct roots keep distinct real paths.
    """
    from .plugin import parse_skill_frontmatter, parse_skill_md  # local: import-light

    skills: list[dict] = []
    warnings: list[dict] = []
    seen: dict[str, str] = {}
    seen_files: set[str] = set()
    seen_roots: set[str] = set()
    for root in roots:
        if not root.is_dir():
            warnings.append({"code": "ROOT_MISSING", "message": f"skill root not found: {root}"})
            continue
        try:
            root_key = str(root.resolve())
        except OSError:
            root_key = str(root)
        if root_key in seen_roots:
            continue  # alias of a root already walked — not a duplicate skill
        seen_roots.add(root_key)
        for slug, md in _iter_skill_dirs(root):
            try:
                md_key = str(md.resolve())
            except OSError:
                md_key = str(md)
            if md_key in seen_files:
                continue  # same real SKILL.md reached through another root
            seen_files.add(md_key)
            try:
                name, desc, body = parse_skill_md(md)
            except OSError as exc:
                warnings.append({"code": "SKILL_UNREADABLE", "message": f"{md}: {exc}"})
                continue
            tools = _declared_tools(md, parse_skill_frontmatter)
            if not desc:
                warnings.append({
                    "code": "SKILL_NO_DESC",
                    "message": f"{slug}: empty description — routing will miss it",
                })
            key = slug.lower()
            if key in seen:
                warnings.append({
                    "code": "SKILL_DUPLICATE",
                    "message": f"{slug}: also found at {seen[key]} — duplicates dilute retrieval",
                })
            else:
                seen[key] = str(md)
            front = _triggers(desc)
            extra = [t for t in _body_triggers(body)
                     if t.lower() not in {f.lower() for f in front}]
            skills.append({
                "slug": slug,
                "name": name or slug,
                "desc": desc,
                "triggers": front + extra,
                "alias_of": _alias_target(desc),
                "tools": tools,
                "root": str(root),
            })
    return {
        "version": INDEX_VERSION,
        "roots": [str(r) for r in roots],
        # Lets a later run tell — cheaply and exactly — whether the catalog still
        # matches. Computed from the same walk that produced `skills`, so the two
        # cannot disagree about which files the catalog covers.
        "signature": catalog_signature(roots),
        "skills": skills,
        "warnings": warnings,
    }


def build_and_save(roots: list[Path]) -> tuple[dict, Path]:
    """Scan ``roots`` and write the index atomically (tmp + ``os.replace``).

    Atomic because the index is now rebuilt automatically, possibly while another
    process is reading it: a reader must see the old index or the new one, never a
    half-written file.
    """
    index = scan_roots(roots)
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return index, path


def load_index() -> dict:
    """Load the built index; ``{}`` when absent or unreadable."""
    path = _index_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ═══════════════════════════════════════════════════
# Catalog views shared by the CLI and the MCP surface
# ═══════════════════════════════════════════════════
#
# `mcptoon skills list` and the `mcptoon_skills` tool must agree, and so must
# `mcptoon skills resolve` and `mcptoon_resolve_skills`. They are separate
# callers, so the projection lives here once rather than being re-implemented
# per surface: two rankings that drift are how a tool loses the argument that
# its answer is the catalog's answer.

def catalog_rows(index: dict, *, include_aliases: bool = False) -> list[dict]:
    """Canonical skill rows — ``{slug, desc}`` — sorted by slug.

    Alias cards are hidden unless asked for: they are pointer stubs that would
    otherwise compete with the skill they point at. ``desc`` is the same
    trigger-stripped one-liner ``mcptoon skills list`` prints.
    """
    rows = []
    for s in index.get("skills", []):
        if s.get("alias_of") and not include_aliases:
            continue
        rows.append({"slug": s["slug"],
                     "desc": _clean_desc(s.get("desc")).split("触发词")[0].strip()})
    rows.sort(key=lambda r: r["slug"])
    return rows


def resolve_shortlist(query: str, k: int = 5, index: dict | None = None) -> list[dict]:
    """The k best skills for ``query`` — ``[{slug, score, desc}]``, best first.

    Records the same usage counts the CLI records, so ``--usage`` reflects MCP
    calls too. ``index`` defaults to the on-disk index; an empty catalog yields
    ``[]`` rather than raising, so a machine with no skills still answers.
    """
    idx = load_index() if index is None else index
    if not idx:
        return []
    shortlist = _BM25(idx).search(query, k)
    record_skill_use([c["slug"] for c in shortlist])
    return shortlist


# ═══════════════════════════════════════════════════
# Keeping the index alive without a manual step
# ═══════════════════════════════════════════════════
#
# The catalog is only as good as its index, and the index was manual: a fresh
# install could not resolve anything until the user ran `mcptoon skills index`,
# and a skill added afterwards stayed invisible until they ran it again. Both
# are the kind of step a user reads about and never does, so the index now keeps
# itself current — built on first use, rebuilt when a skill changes.

def _iter_skill_mds(roots: list[Path]):
    """Yield every ``SKILL.md`` under ``roots``, de-duplicated by real path.

    The cheap half of a scan: no parsing, just the walk. Shares
    :func:`_iter_skill_dirs` so a staleness probe and a full scan can never
    disagree about which files belong to the catalog.
    """
    seen_roots: set[str] = set()
    seen_files: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            root_key = str(root.resolve())
        except OSError:
            root_key = str(root)
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        for _slug, md in _iter_skill_dirs(root):
            try:
                key = str(md.resolve())
            except OSError:
                key = str(md)
            if key in seen_files:
                continue
            seen_files.add(key)
            yield md


def catalog_signature(roots: list[Path]) -> str:
    """A hash of every ``SKILL.md`` under ``roots``: path, size and mtime.

    The staleness signal. mtime-of-newest alone cannot see a *deleted* skill (the
    files that remain are not newer than the index) and counting files cannot see
    an edit. A signature over the whole listing sees all three, and costs the same
    stat-only walk — 0.01s for 1,200 files.
    """
    rows = []
    for md in _iter_skill_mds(roots):
        try:
            st = md.stat()
        except OSError:
            continue  # vanished mid-walk; the next run sees the new truth
        rows.append(f"{md}\0{st.st_size}\0{st.st_mtime_ns}")
    rows.sort()  # walk order is not guaranteed stable across platforms
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def index_is_stale(index: dict) -> bool:
    """True when the catalog on disk no longer matches the index.

    Compares the stored :func:`catalog_signature` against the one the disk
    produces now. An index with no signature (written by an older mcptoon) reads
    as stale, so the first resolve after an upgrade refreshes it once and the
    signature is there from then on.

    A root that cannot be read contributes no rows, so its signature will not
    match — one rebuild is requested, and the index that rebuild produces carries
    the same signature, so it settles rather than looping. A permanently wrong
    index is worse than one rebuild.
    """
    if not index:
        return False
    stored = index.get("signature")
    if not stored:
        return True
    roots = [Path(r) for r in (index.get("roots") or []) if r]
    return catalog_signature(roots) != stored


def build_if_stale(*, verbose: bool = False) -> bool:
    """Rebuild the index when a skill changed under it. Returns True if rebuilt.

    Best-effort by design: a read-only home, a missing root or a scan error must
    never break a resolve, so every failure path is a quiet no-op and the caller
    falls back to whatever index already exists.
    """
    try:
        index = load_index()
        if not index or not index_is_stale(index):
            return False
        roots = [Path(r) for r in (index.get("roots") or []) if r] or _default_roots()
        if not roots:
            return False
        with _INDEX_LOCK:
            if not index_is_stale(load_index()):  # another thread rebuilt first
                return False
            build_and_save(roots)
        if verbose:
            print("mcptoon: skill catalog changed — index rebuilt", file=sys.stderr)
        return True
    except Exception:  # a stale index is not worth a crash
        return False


def ensure_index(*, verbose: bool = False) -> bool:
    """Guarantee an index exists and is current. Returns True when it was built.

    Called from the paths that need a catalog (``resolve``/``route``, the
    ``mcptoon_resolve_skills`` tool, ``sync``): a missing index is built, a stale
    one is rebuilt, a current one is left alone. The whole point is that the user
    never has to know `mcptoon skills index` exists.
    """
    try:
        index = load_index()
    except Exception:
        index = {}
    if index:
        return build_if_stale(verbose=verbose)
    try:
        roots = [p for p in _default_roots() if p.is_dir()]
        if not roots:
            return False
        with _INDEX_LOCK:
            if load_index():  # another thread built one first
                return False
            build_and_save(roots)
        if verbose:
            print(f"mcptoon: built a skill index from {len(roots)} root(s)", file=sys.stderr)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════
# Retrieval (BM25, zero dependency)
# ═══════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """ASCII words plus CJK unigrams and bigrams.

    Bigrams matter: skill descriptions are largely Chinese, where single
    characters are too ambiguous to rank on.
    """
    text = (text or "").lower()
    out = re.findall(r"[a-z0-9][a-z0-9_\-\.]*", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    out += cjk
    out += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return out


def resolve_aliases(index: dict) -> tuple[dict, dict]:
    """Split the catalog into canonical skills and alias→canonical map.

    Returns ``(canonical_by_slug, alias_map)``. Alias chains are followed with a
    cycle guard; an alias pointing outside the catalog stays an alias (callers
    treat it as unknown).
    """
    skills = index.get("skills", [])
    by_slug = {s["slug"].lower(): s for s in skills}
    alias_map: dict[str, str] = {}
    for s in skills:
        t = (s.get("alias_of") or "").lower()
        if t:
            alias_map[s["slug"].lower()] = t
    canonical = {k: v for k, v in by_slug.items() if k not in alias_map}

    def resolve_one(slug: str) -> str:
        seen = set()
        while slug in alias_map and slug not in seen:
            seen.add(slug)
            slug = alias_map[slug]
        return slug

    return canonical, {k: resolve_one(k) for k in alias_map}


# How much an exact skill-name hit is worth relative to a plain term match.
# Measured on a 30-case Chinese routing set: 2.0 lifts top-1 from 26/30 to 28/30
# and top-3 to 28/30, and 3.0/5.0/8.0 change nothing further — so the effect
# saturates early and the smallest value that works is the one kept.
_EXACT_NAME_BOOST = 2.0


class _BM25:
    """Ranked retrieval over canonical skills.

    Each canonical skill's document merges its own slug/description/triggers with
    those of every alias that points at it, so a query using the alias name
    still reaches the canonical entry.
    """

    def __init__(self, index: dict):
        canonical, alias_map = resolve_aliases(index)
        self.alias_map = alias_map
        self.slugs = set(canonical)
        self.descs: dict[str, str] = {}
        back: dict[str, list[str]] = defaultdict(list)
        for alias, target in alias_map.items():
            back[target].append(alias)

        by_slug = {s["slug"].lower(): s for s in index.get("skills", [])}
        gloss = _load_gloss()
        docs: dict[str, Counter] = {}
        df: Counter = Counter()
        for slug, s in canonical.items():
            parts = [slug, s.get("name") or "", _clean_desc(s.get("desc")),
                     " ".join(s.get("triggers") or [])]
            parts += gloss.get(slug.lower(), [])
            for a in back.get(slug, []):
                as_ = by_slug.get(a, {})
                parts += [a, _clean_desc(as_.get("desc")), " ".join(as_.get("triggers") or [])]
                parts += gloss.get(a.lower(), [])
            counts = Counter(_tokenize(" ".join(parts)))
            docs[slug] = counts
            self.descs[slug] = _clean_desc(s.get("desc"))
            for t in counts:
                df[t] += 1
        self.docs = docs
        self.df = df
        self.n = len(docs)
        self.avgdl = (sum(sum(c.values()) for c in docs.values()) / self.n) if self.n else 0.0
        self.declared = {slug: list(s.get("tools") or []) for slug, s in canonical.items()}

    def resolve(self, slug: str) -> str:
        """Map a possibly-aliased slug to its canonical form."""
        slug = (slug or "").strip().lower().lstrip("/")
        seen = set()
        while slug in self.alias_map and slug not in seen:
            seen.add(slug)
            slug = self.alias_map[slug]
        return slug

    def _score(self, q_tokens: list[str], doc: Counter) -> float:
        # b=0.5, not the textbook 0.75. Length here is verbosity, not scope: a
        # skill with a chatty description is not more likely to be the answer, so
        # normalising it twice as hard as a terse one only buries it. Measured:
        # 「用 ComfyUI 出一个视频」 put `comfyui` at rank 11 with b=0.75 while it
        # shared the same eight terms as a winner whose document was half as long.
        k1, b = 1.5, 0.5
        dl = sum(doc.values())
        total = 0.0
        for t in q_tokens:
            if t not in doc:
                continue
            idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            tf = doc[t]
            total += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / self.avgdl))
        return total

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Top-k ``[{slug, score, desc}]``, best first.

        ``k <= 0`` asks for nothing and gets ``[]``. It used to be clamped up to
        1, which made "no results, please" indistinguishable from "one result";
        a negative ``k`` was worse — ``ranked[:-1]`` sliced the ranking from the
        end and returned a silent wrong answer instead of nothing.

        A query token that names a skill outright is the strongest routing
        evidence there is, and plain BM25 dilutes it: 「用 ComfyUI 出一个视频」
        let five skills sharing only 泛词 and 视频 outrank ``comfyui`` itself. So
        an exact name hit is weighted, which is what `_EXACT_NAME_BOOST` records.
        """
        if k <= 0:
            return []
        q = _tokenize(_expand_query(query))
        named = {
            t for t in (query or "").lower().replace("/", " ").split()
            if t in self.slugs
        }
        scored: list[tuple[float, str]] = []
        for slug, d in self.docs.items():
            score = self._score(q, d)
            if score > 0 and slug in named:
                score *= _EXACT_NAME_BOOST
            scored.append((score, slug))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [
            {"slug": slug, "score": round(score, 4), "desc": self.descs.get(slug, "")}
            for score, slug in scored[:k]
            if score > 0
        ]

    def declared_tools(self, shortlist: list[dict]) -> list[str]:
        """Tools declared by the shortlisted skills, de-duplicated, in rank order.

        A skill that matched is evidence its instruments are relevant, so they
        are surfaced additively — never as a competitor to the skill bucket.
        """
        out: list[str] = []
        seen = set()
        for c in shortlist:
            for t in self.declared.get(c["slug"], []):
                if t.lower() not in seen:
                    seen.add(t.lower())
                    out.append(t)
        return out


def tool_shortlist(query: str, k: int = 5, use_cache: bool = True) -> list[dict]:
    """The tools bucket: the k best tools for the query, or ``[]``.

    Skills and tools are ranked in separate buckets with separate budgets — the
    same call that returns a playbook also returns instruments, and neither can
    starve the other. Degrades to ``[]`` when no MCP servers are configured, so
    the skills half works on a machine that has only skills.
    """
    try:
        from .manifest import search_tools
        return search_tools(query, use_cache=use_cache, limit=k)
    except Exception:  # noqa: BLE001 — a missing/broken tool catalog must not kill skills
        return []


# ═══════════════════════════════════════════════════
# Routing (optional LLM pick over the shortlist)
# ═══════════════════════════════════════════════════

_ROUTE_PROMPT = (
    "You are a coding agent. Choose the SINGLE best skill for the user request.\n"
    'Reply ONLY compact JSON: {"skill":"<slug>","confidence":0-1}\n\n'
    "=== CANDIDATES ===\n<<CANDIDATES>>\n\n=== USER REQUEST ===\n<<TASK>>\n"
)


def _candidates_block(shortlist: list[dict]) -> str:
    return "\n".join(f"- {c['slug']}: {c['desc']}" for c in shortlist)


def _route_prompt(shortlist: list[dict], task: str) -> str:
    """Fill the template by literal substitution.

    ``str.format`` would treat the JSON braces in the template as fields.
    """
    return _ROUTE_PROMPT.replace("<<CANDIDATES>>", _candidates_block(shortlist)).replace(
        "<<TASK>>", task)


def _chat(endpoint: str, model: str, prompt: str, timeout: int = 90) -> str:
    """One OpenAI-compatible chat call. urllib only — no dependency."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 120,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def _parse_pick(answer: str) -> str:
    m = re.search(r"\{.*?\}", answer or "", re.S)
    if not m:
        return ""
    try:
        return (json.loads(m.group(0)).get("skill") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        return ""


def route(index: dict, query: str, k: int, endpoint: str, models: list[str],
          timeout: int = 90) -> dict:
    """Shortlist with BM25, then have ``models`` pick; majority vote wins.

    ``models`` is a list — more than one turns the pick into a vote, which is
    what closes the last gap to 100% in the measurements.
    """
    bm = _BM25(index)
    shortlist = bm.search(query, k)
    if not shortlist:
        return {"query": query, "shortlist": [], "picks": {}, "skill": "", "vote": {}}
    prompt = _route_prompt(shortlist, query)

    picks: dict[str, str] = {}
    for model in models:
        raw = ""
        try:
            raw = _chat(endpoint, model, prompt, timeout)
        except Exception as exc:  # transport failures must not abort the vote
            picks[model] = f"!{type(exc).__name__}"
            continue
        picks[model] = bm.resolve(_parse_pick(raw))

    valid = [p for p in picks.values() if p and not p.startswith("!")]
    votes = Counter(valid)
    winner = votes.most_common(1)[0][0] if votes else ""
    top = votes.most_common(1)[0][1] if votes else 0
    return {
        "query": query,
        "shortlist": shortlist,
        "picks": picks,
        "vote": dict(votes),
        "skill": winner,
        "unanimous": bool(valid) and len(set(valid)) == 1 and len(valid) == len(models),
        "confidence": round(top / len(valid), 3) if valid else 0.0,
    }


# ═══════════════════════════════════════════════════
# The in-context entry
# ═══════════════════════════════════════════════════

MANIFEST_ENTRY = (
    "Skills: `mcptoon skills resolve \"<request>\" --k 5` returns the best-matching "
    "skills as JSON. Read only those SKILL.md files. Never load the whole catalog."
)


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# Remote search (skills.sh — the open skills registry)
# ═══════════════════════════════════════════════════

#: skills.sh exposes a live *search* endpoint but no enumerable listing, so this is
#: search-only: there is no "list all skills" call to make. Verified 2026-09-24.
SKILLS_SH_SEARCH_URL = "https://skills.sh/api/search"


def _search_skills_sh(query: str, limit: int = 10) -> list[dict]:
    """Search skills.sh. Returns ``[{id, source, skillId, name, installs}]``.

    Raises whatever ``_fetch_json`` raises (network/TLS/timeout) — the caller
    decides whether to fall back to the offline index. It never turns a failure
    into an empty list, which is what makes the offline fallback honest.
    """
    import urllib.parse
    from .installer import _fetch_json

    url = f"{SKILLS_SH_SEARCH_URL}?q={urllib.parse.quote(query)}"
    data = _fetch_json(url)
    rows = []
    for s in (data.get("skills") or [])[:limit]:
        rows.append({
            "id": s.get("id", ""),
            "source": s.get("source", ""),
            "skillId": s.get("skillId") or s.get("name", ""),
            "name": s.get("name", ""),
            "installs": s.get("installs") or 0,
        })
    return rows


def search_skills(query: str, limit: int = 10,
                  index: dict | None = None) -> tuple[list[dict], str]:
    """Search skills.sh, falling back to the local index when the network is down.

    Returns ``(rows, source)`` where ``source`` is ``"skills.sh"`` or ``"offline"``.
    The caller prints the source, so a degraded search is never passed off as a
    complete one — the same discipline the registry installer learned the hard way.
    """
    try:
        return _search_skills_sh(query, limit), "skills.sh"
    except Exception:
        local: list[dict] = []
        if index:
            for c in _BM25(index).search(query, limit):
                local.append({"id": c["slug"], "source": "local", "skillId": c["slug"],
                              "name": c["slug"], "installs": 0, "desc": c.get("desc", "")})
        return local, "offline"


def _cmd_skills_search(args: list[str], fmt: str) -> None:
    query = _query_of(args)
    if not query:
        print("mcptoon: search needs a query. Usage: mcptoon skills search <query>",
              file=sys.stderr)
        sys.exit(1)
    limit = _parse_k(args, "--limit", 10)
    rows, source = search_skills(query, limit, index=load_index())
    if fmt == "json":
        print(json.dumps({"query": query, "source": source, "skills": rows},
                         ensure_ascii=False, indent=1))
        return
    if not rows:
        if source == "offline":
            print(f"  Offline — skills.sh unreachable, and no local match for {query!r}.")
        else:
            print(f"  No skill found for {query!r} on skills.sh.")
        return
    print(f"  Found {len(rows)} skill(s) for {query!r} ({source}):")
    for i, r in enumerate(rows, 1):
        uses = f"   {r['installs']:,} installs" if r.get("installs") else ""
        print(f"    {i:>2}. {r['id']}{uses}")
    if source == "offline":
        print("  (skills.sh unreachable — results are from the local index)")
    else:
        print("  Third-party skills are not audited by mcptoon — check the source.")


def _skills_usage() -> str:
    return (
        "mcptoon skills — index, sync and route a skill catalog without keeping it in context\n\n"
        "  mcptoon skills index [ROOT ...]        Scan roots, build the on-disk index\n"
        "  mcptoon skills sync [SRC] [VIEW ...]   Distribute a source catalog to agent views\n"
        "                    [--copy] [--dry]      (link by default; never deletes a real dir)\n"
        "                    [--version-gate]      Block skills whose content moved but version did not\n"
        "                    [--derived roo|opencode|all]  Regenerate the flat .md views\n"
        "                    [--archive DIR]       Where drift/removals are parked (default <src>/../_archive)\n"
        "  mcptoon skills add <name> [--desc D]   Create a skill in the source\n"
        "  mcptoon skills remove <name>           Archive a skill out of the source\n"
        "                    [--tombstone]         Commit the removal (path-scoped) so git sync cannot revive it\n"
        "  mcptoon skills list [--usage]          List skills, optionally with hit counts\n"
        "  mcptoon skills search <query> [--limit N]  Search skills.sh (falls back to the local index)\n"
        "  mcptoon skills resolve <query> [--k N] BM25 shortlist (no LLM, no tokens)\n"
        "  mcptoon skills route <query> [--k N]   Shortlist then let an LLM pick\n"
        "                    [--model M[,M2]] [--endpoint URL]\n"
        "  mcptoon skills stats                   Catalog health (dupes, aliases, no-desc)\n"
        "  mcptoon skills manifest                The one-line entry to keep in context\n\n"
        "Roots default to MCPTOON_SKILLS_ROOTS or ~/.claude/skills and friends.\n"
        "Views default to MCPTOON_SKILLS_VIEWS or the same agent folders.\n"
        "Route endpoint/model default to MCPTOON_SKILLS_ENDPOINT / _MODEL."
    )


_VALUE_FLAGS = ("--k", "--tools-k", "--model", "--endpoint", "--desc",
                "--archive", "--derived", "--version-gate", "--limit")


def _query_of(args: list[str]) -> str:
    """The query text in ``args``, with flags *and their values* removed.

    Naively keeping every non-dash token leaks a flag's value into the query —
    ``--k 2`` contributed the token "2", which then scored against descriptions.
    """
    out: list[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            if "=" not in a and a in _VALUE_FLAGS:
                skip = True
            continue
        out.append(a)
    return " ".join(out)


def _flag(rest: list[str], name: str, default: str = "") -> str:
    """Read the value of a long option given as ``--<name> value`` or ``--<name>=value``."""
    for i, a in enumerate(rest):
        if a == name and i + 1 < len(rest):
            return rest[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def _parse_k(rest: list[str], name: str, default: int, minimum: int = 1) -> int:
    """Read an integer option, failing loudly instead of raising a traceback.

    ``--k abc`` used to escape as ``ValueError: invalid literal for int()`` with
    a stack trace, so a typo read as a crash inside mcptoon. An out-of-range
    value is refused for the same reason: ``--k 0`` silently became one result,
    which is a different answer from the one that was asked for. Both print one
    line on stderr and exit 1, matching every other bad-invocation path in this
    CLI (the repo has no exit-2 convention to join).
    """
    raw = _flag(rest, name, "")
    if raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        print(f"mcptoon: {name} needs an integer, got {raw!r}", file=sys.stderr)
        sys.exit(1)
    if value < minimum:
        print(f"mcptoon: {name} must be at least {minimum}, got {value}", file=sys.stderr)
        sys.exit(1)
    return value


# ═══════════════════════════════════════════════════
# Distribution: one source of truth -> N agent views
# ═══════════════════════════════════════════════════
#
# Skills are the same shape as MCP servers, which `mcptoon sync` already
# distributes: one canonical source, many agent-native views. The only new
# decision is what a view IS. For a directory the cheapest correct view is a
# LINK, not a copy — one edit at the source is instantly visible everywhere and
# there is no second copy to drift. A copy is the fallback for filesystems
# without links, or when freezing a version on purpose.
#
# The three disciplines that keep this safe (each one learned from a real
# failure in the tongbu-skills lineage):
#   1. A real directory where a link belongs is DRIFT -> archive it, never delete.
#   2. Removal happens at the SOURCE; the views follow on the next sync.
#   3. Never fight a view that is already managed by something else — report it.
#
# Nothing here ever writes inside the source, and nothing ever deletes a real
# directory. `--dry-run` proves the plan before a single link is made.

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_link(path: Path) -> bool:
    """True for a symlink or a Windows junction (both are reparse points)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if _stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _link_target(path: Path) -> str:
    """The raw target a link was created with, or "" if it is not a link.

    ``os.readlink`` is used rather than ``realpath`` on purpose. On Windows a
    junction stores whatever path it was made with — often 8.3 short form
    (``ADMINI~1``) — and ``realpath`` only expands that while the target still
    exists. After the source directory is deleted the link dangles and realpath
    stops expanding, so a realpath-based ownership test would suddenly report a
    link of ours as foreign. The stored string is stable either way.
    """
    try:
        raw = os.readlink(path)
    except OSError:
        return ""
    if not raw:
        return ""
    if raw.startswith("\\\\?\\"):  # NT namespace prefix on Windows junctions
        raw = raw[4:]
    if not os.path.isabs(raw):
        raw = os.path.join(str(path.parent), raw)
    return os.path.normpath(raw)


def _points_into(target: str, source: Path) -> bool:
    """Whether a link target lives under ``source`` (either may be 8.3 short)."""
    if not target:
        return False

    def norm(p) -> str:
        return os.path.normcase(os.path.normpath(str(p)))

    t, s = norm(target), norm(source)
    if t == s or t.startswith(s + os.sep):
        return True
    # Fallback for a link stored in the other form (long vs short): realpath
    # expands 8.3 while the path exists, so try the resolved pair too.
    try:
        tr = os.path.normcase(os.path.realpath(target))
        sr = os.path.normcase(os.path.realpath(str(source)))
    except OSError:
        return False
    return tr == sr or tr.startswith(sr + os.sep)


def _make_link(src: Path, dst: Path) -> None:
    """Create a directory link. Junction on Windows (no admin), symlink elsewhere."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout).strip() or "mklink failed")
    else:
        os.symlink(src, dst, target_is_directory=True)


def _source_skills(source: Path) -> dict[str, Path]:
    """``{slug: skill_dir}`` for a source root. A skill is a dir with SKILL.md."""
    out: dict[str, Path] = {}
    for base in (source, source / "skills"):
        if not base.is_dir():
            continue
        try:
            children = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            if _skip_dir(child.name):
                continue
            if (child / "SKILL.md").is_file():
                out.setdefault(child.name, child)
    return out


def sync_skills(source: Path, views: list[Path], *, strategy: str = "link",
                dry_run: bool = False, archive: Path | None = None,
                skills: dict[str, Path] | None = None) -> dict:
    """Distribute ``source`` skills into every view. Idempotent; never deletes.

    ``skills`` overrides the discovered catalog — the caller passes the
    version-gate survivors so a blocked skill is never placed in a view.
    Returns a report dict: per-view ``added`` / ``ok`` / ``drifted`` / ``pruned``
    and, separately, ``foreign`` — links owned by another manager, which are left
    untouched. A real directory in a view is moved to ``archive`` (never removed)
    and the link is then created.
    """
    if strategy not in ("link", "copy"):
        raise ValueError(f"strategy must be 'link' or 'copy', not {strategy!r}")
    skills = skills if skills is not None else _source_skills(source)
    archive = archive or (source.parent / "_archive")
    report: dict = {"source": str(source), "strategy": strategy,
                    "skills": sorted(skills), "views": {}, "dryRun": dry_run}

    for view in views:
        acts = {"added": [], "ok": [], "drifted": [], "pruned": [], "foreign": []}

        # A view that is ITSELF a link must never be descended into. The common
        # real-world case is a whole-directory junction (`~/.claude/skills ->
        # ~/skills`), which is already a perfect view; iterating it would show
        # the source's own children as "real directories" and archive every one
        # of them — destroying the user's view to "fix" a drift that is not
        # there. Report it and move on, whoever owns it.
        if _is_link(view):
            if _points_into(_link_target(view), source):
                acts["wholeDirLink"] = True
            else:
                acts["foreign"].append("(whole directory linked elsewhere)")
            report["views"][str(view)] = acts
            continue

        if not dry_run:
            try:
                view.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                acts["error"] = str(e)
                report["views"][str(view)] = acts
                continue
        wanted = set(skills)

        # 1) prune links whose source is gone (removal happens at the source)
        if view.is_dir():
            try:
                existing = sorted(view.iterdir())
            except OSError:
                existing = []
            for item in existing:
                if item.name in wanted:
                    continue
                if not _is_link(item):
                    continue  # a real dir here belongs to someone else; leave it
                target = _link_target(item)
                # only prune a link that points back into OUR source
                if not _points_into(target, source):
                    acts["foreign"].append(item.name)
                    continue
                if not dry_run:
                    try:
                        item.unlink()
                    except OSError:
                        continue
                acts["pruned"].append(item.name)

        # 2) place each skill
        for slug, src in sorted(skills.items()):
            dest = view / slug
            if _is_link(dest):
                target = _link_target(dest)
                if not _points_into(target, source):
                    acts["foreign"].append(slug)   # another manager owns it
                else:
                    acts["ok"].append(slug)
                continue
            if dest.exists():
                # a real directory where a link belongs = drift; archive, never delete
                stamp = int(os.stat(dest).st_mtime)
                dst = archive / view.name / f"{slug}.{stamp}"
                if not dry_run:
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(dest), str(dst))
                    except OSError:
                        acts.setdefault("error", f"could not archive {slug}")
                        continue
                acts["drifted"].append(slug)
            if not dry_run:
                try:
                    if strategy == "link":
                        _make_link(src, dest)
                    else:
                        shutil.copytree(src, dest)
                except OSError as e:
                    acts.setdefault("error", f"{slug}: {e}")
                    continue
            acts["added"].append(slug)
        report["views"][str(view)] = acts
    return report


def _print_sync_report(report: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return
    tag = " (dry run — nothing written)" if report["dryRun"] else ""
    print(f"mcptoon skills sync{tag}")
    print(f"  source: {report['source']}  ({len(report['skills'])} skills)")
    for view, a in report["views"].items():
        if a.get("wholeDirLink"):
            print(f"  {view}")
            print("    already a link to the source — nothing to do")
            continue
        bits = []
        if a["added"]:
            bits.append(f"+{len(a['added'])} new")
        if a["ok"]:
            bits.append(f"{len(a['ok'])} ok")
        if a["drifted"]:
            bits.append(f"{len(a['drifted'])} drifted->archived")
        if a["pruned"]:
            bits.append(f"{len(a['pruned'])} pruned")
        if a.get("foreign"):
            bits.append(f"{len(a['foreign'])} left alone (other manager)")
        print(f"  {view}")
        print(f"    {', '.join(bits) if bits else 'no change'}")
        if a.get("error"):
            print(f"    ⚠ {a['error']}")
    print("\n  one source, many views — edits at the source are already live.")


# ═══════════════════════════════════════════════════
# Parity with the tongbu-skills lineage: the version gate,
# the derived flat views, and a tombstoned removal
# ═══════════════════════════════════════════════════
#
# Four things a catalog manager needs before it can take over from a
# long-running script — each one learned from a real failure in the
# tongbu-skills v7 lineage:
#
#   * a VERSION GATE, so "content changed but version did not" is caught
#     before it reaches every agent view;
#   * DERIVED flat views (Roo / OpenCode), regenerated from the same source;
#   * a TOMBSTONED removal that lands as a git commit, so a two-way git sync
#     cannot resurrect a deleted skill;
#   * a SHARED graveyard, so a rollback is the same `mv` on either side.
#
# The gate reads the SAME ledger file tongbu wrote, so during the coexistence
# phase both managers reach the same verdict on the same bytes. Its hash
# therefore mirrors tongbu's algorithm exactly (sha256 over sorted relative
# paths + raw bytes, dot-entries skipped, the ledger's own files excluded) —
# any difference would make the two managers disagree on unchanged content.

# Files that must never enter their own content hash: the gate rewrites them on
# every run, so hashing them would make the hash drift forever and the gate
# would block the very skill that owns the ledger (tongbu-skills hit exactly
# this, and it was the one block of six that was not a stale-ledger artefact).
_VERSION_HASH_EXCLUDE = {"skill_versions.json", "sync_log.json"}
# Directory names that are never a skill, wherever the tree is walked. `_index`
# is the vault's own index card: it carries a SKILL.md and would otherwise be
# published to every agent view as if it were a skill (tongbu-skills has skipped
# it in all 13 of its walkers since v5, and the derived views prove why — the
# byte-parity check against the live ~/.roo/commands caught this as the one
# file mcptoon added that tongbu had never written).
_SKIP_DIR_NAMES = {"_index", ".git", "__pycache__", "node_modules", ".DS_Store"}


def _skip_dir(name: str) -> bool:
    return name in _SKIP_DIR_NAMES or name.startswith(".")


def _version_ledger_path(source: Path) -> Path:
    """The version ledger for ``source``.

    Defaults to the tongbu-skills location so the two managers share one
    ledger; override with MCPTOON_SKILLS_LEDGER (tests, or a second catalog).
    """
    env = os.environ.get("MCPTOON_SKILLS_LEDGER")
    if env:
        return Path(env)
    return source / "tongbu-skills" / "skill_versions.json"


def _load_version_ledger(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_version_ledger(path: Path, ledger: dict) -> None:
    """Atomic write (tmp + os.replace) — the discipline the ledger already had."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def _skill_content_hash(skill_dir: Path) -> str:
    """tongbu-compatible content hash: raw bytes over sorted relative paths."""
    h = hashlib.sha256()
    files = []
    for f in skill_dir.rglob("*"):
        if not f.is_file():
            continue
        parts = f.relative_to(skill_dir).parts
        if any(_skip_dir(p) for p in parts):
            continue
        if f.name in _VERSION_HASH_EXCLUDE:
            continue
        files.append(f)
    for f in sorted(files, key=lambda x: str(x.relative_to(skill_dir))):
        h.update(str(f.relative_to(skill_dir)).replace("\\", "/").encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


def version_gate(skills: dict[str, Path], ledger_path: Path, *, force: bool = False,
                 update_ledger: bool = True) -> dict:
    """Filter ``skills`` through the version ledger.

    A skill is BLOCKED when its content hash moved but its frontmatter
    ``version`` did not — the exact rule tongbu enforces. ``force`` lets it
    through and refreshes the ledger. A skill with no version is only warned
    about (gradual enforcement), and a skill absent from the ledger is
    onboarded on first sight. Returns a report dict.
    """
    from .plugin import parse_skill_frontmatter  # local: import-light
    ledger = _load_version_ledger(ledger_path)
    allowed: list[str] = []
    blocked: list[tuple[str, str]] = []
    onboard: list[str] = []
    legacy: list[str] = []
    forced: list[str] = []
    for slug, skill_dir in sorted(skills.items()):
        try:
            meta = parse_skill_frontmatter(skill_dir / "SKILL.md")
        except OSError:
            meta = {}
        ver = str(meta.get("version") or "").strip()
        digest = _skill_content_hash(skill_dir)
        rec = ledger.get(slug)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if rec is None:
            ledger[slug] = {"hash": digest, "version": ver, "at": now}
            allowed.append(slug)
            onboard.append(slug)
            continue
        if rec.get("hash") == digest:
            if rec.get("version", "") != ver:
                ledger[slug] = {**rec, "version": ver, "at": now}
            allowed.append(slug)
            continue
        if not rec.get("version"):
            ledger[slug] = {"hash": digest, "version": ver, "at": now}
            allowed.append(slug)
            legacy.append(slug)
            continue
        if ver == rec["version"] and not force:
            blocked.append((slug, ver))
            continue
        if ver == rec["version"]:
            forced.append(slug)
        ledger[slug] = {"hash": digest, "version": ver, "at": now}
        allowed.append(slug)
    if update_ledger:
        _save_version_ledger(ledger_path, ledger)
    return {"allowed": allowed, "blocked": blocked, "onboarded": onboard,
            "legacy": legacy, "forced": forced, "ledger": str(ledger_path)}


# Derived views: a flat ``<slug>.md`` per skill plus its ``.py`` attachments.
# This is how Roo and OpenCode consume a catalog (slash commands load on demand,
# so the whole catalog can live there without costing session context).
_DERIVED_VIEWS = {
    "roo": Path.home() / ".roo" / "commands",
    "opencode": Path.home() / ".config" / "opencode" / "commands",
}


def _derived_view_paths() -> dict[str, Path]:
    env = os.environ.get("MCPTOON_SKILLS_DERIVED")
    if env:  # "roo=path,opencode=path2" — tests stay hermetic
        out: dict[str, Path] = {}
        for part in env.split(","):
            if "=" in part:
                name, _, p = part.partition("=")
                out[name.strip()] = Path(p.strip())
        return out
    return dict(_DERIVED_VIEWS)


def _derive_one(skill_dir: Path, slug: str, view: Path, *, dry_run: bool) -> list[str]:
    """Write one skill's flat ``<slug>.md`` (+ ``<slug>_*.py``).

    Byte-identical to tongbu's output: the source is read with universal
    newlines and written back with the platform separator, which on Windows
    turns the source's LF into CRLF. Reproducing that exactly is the whole
    point — a derived view that differs by a line ending is not "the same
    catalog", it is a diff the next sync has to fight.
    """
    actions: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return actions
    text = skill_md.read_text(encoding="utf-8")          # universal newlines -> \n
    if not dry_run:
        view.mkdir(parents=True, exist_ok=True)
        (view / f"{slug}.md").write_text(text, encoding="utf-8")  # -> os.linesep
    actions.append(f"WRITE {slug}.md")
    for item in sorted(skill_dir.iterdir()):
        if item.name == "SKILL.md" or item.name.startswith("."):
            continue
        if item.is_file() and item.suffix == ".py":
            if not dry_run:
                shutil.copy2(item, view / f"{slug}_{item.name}")
            actions.append(f"COPY {slug}_{item.name}")
    return actions


def sync_derived(source: Path, skills: dict[str, Path], views: dict[str, Path],
                 *, dry_run: bool = False, archive: Path | None = None) -> dict:
    """Regenerate every derived flat view from the source.

    Stale files (a ``<slug>.md`` whose skill left the source) are MOVED into the
    graveyard, never deleted — a generated file is cheap to lose, but the rule
    is the rule, and a wrong guess here should still be a `mv` back.
    """
    archive = archive or (source.parent / "_archive")
    report: dict = {"dryRun": dry_run, "views": {}}
    wanted = {s.lower() for s in skills}
    for name, view in views.items():
        acts: dict = {"written": 0, "stale": [], "errors": []}
        for slug, skill_dir in sorted(skills.items()):
            try:
                _derive_one(skill_dir, slug, view, dry_run=dry_run)
                acts["written"] += 1
            except OSError as e:
                acts["errors"].append(f"{slug}: {e}")
        if view.is_dir():
            stale = [f for f in view.glob("*.md") if f.stem.lower() not in wanted]
            stale += [f for f in view.glob("*.py")
                      if f.stem.split("_")[0].lower() not in wanted]
            for f in stale:
                acts["stale"].append(f.name)
                if dry_run:
                    continue
                dst = archive / f"derived-{name}" / f.name
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(dst))
                except OSError:
                    pass
        report["views"][name] = acts
    return report


def _git_tombstone(source: Path, rel_path: str, message: str) -> tuple[bool, str]:
    """Commit the removal of ``rel_path`` as a git tombstone.

    The commit is PATH-SCOPED. A whole-repo ``git add -A`` is refused here on
    purpose: the repo holding a real skill source routinely has hundreds of
    unrelated edits in flight, and sweeping them into a "tombstone" commit is
    how one manager silently commits another session's work. Every git call
    below carries an explicit pathspec.
    """
    repo = None
    for cand in (source, source.parent):
        if (cand / ".git").exists():
            repo = cand
            break
    if repo is None:
        return False, "not a git repository — tombstone skipped"
    rel = os.path.relpath(source / rel_path, repo).replace("\\", "/")
    add = subprocess.run(["git", "add", "-A", "--", rel], cwd=str(repo),
                         capture_output=True, text=True)
    if add.returncode != 0:
        return False, (add.stderr or add.stdout).strip()[:200]
    commit = subprocess.run(["git", "commit", "-m", message, "--", rel],
                            cwd=str(repo), capture_output=True, text=True)
    if commit.returncode != 0:
        out = (commit.stderr or commit.stdout).strip()
        if "nothing to commit" in out or "no changes added" in out:
            return False, "nothing to commit"
        return False, out[:200]
    return True, rel


def _print_derived_report(report: dict) -> None:
    tag = " (dry run — nothing written)" if report["dryRun"] else ""
    print(f"mcptoon skills sync --derived{tag}")
    for name, a in report["views"].items():
        bits = [f"{a['written']} regenerated"]
        if a["stale"]:
            bits.append(f"{len(a['stale'])} stale->archived")
        print(f"  {name}: {', '.join(bits)}")
        for e in a["errors"]:
            print(f"    ⚠ {e}")


# ═══════════════════════════════════════════════════
# Catalog management: add / remove / list --usage
# ═══════════════════════════════════════════════════
#
# Removal follows the same rule the rest of this module does: never delete.
# A removed skill is MOVED into a dated archive beside the source, so a wrong
# removal is a `mv` back, not a re-clone. "Uninstall" that cannot be undone is
# how a manager loses a user's trust the first time they fat-finger a name.
#
# Usage is recorded only for skills this gateway routed (resolve/route). Skills
# an agent loaded directly are invisible here — the counts are a floor, not a
# census, and `list --usage` says so rather than implying full coverage.

def _usage_path() -> Path:
    return Path(os.environ.get(
        "MCPTOON_SKILLS_USAGE", str(CONFIG_DIR / "skills-usage.json")))


# Guards the read-modify-write in record_skill_use against in-process races.
_USAGE_LOCK = threading.Lock()

# Guards index rebuilds: two resolves that both see a stale index must not scan
# the catalog twice, and neither may write the file while the other reads it.
_INDEX_LOCK = threading.Lock()


def _load_skill_usage() -> dict:
    path = _usage_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def record_skill_use(slugs: list[str]) -> None:
    """Bump the hit counter for skills a route/resolve just surfaced.

    Serialized in-process, then written atomically. Two callers reach this now —
    the CLI (`resolve`/`route`) and the MCP tool (`mcptoon_resolve_skills`) — so a
    bare `write_text` was wrong twice over: a concurrent reader could catch a torn
    file, and two writers could each read the old counts and write back the same
    "+1", collapsing a burst of calls into one. Measured 2026-09-24: 30 concurrent
    resolves recorded a count of 1. The unique tmp name is the discipline
    `usage._save_usage` already uses; the lock covers the in-process case, which is
    the reachable one (the HTTP transport is single-threaded, but a thread pool in
    a host, or the CLI running beside a gateway, is not).

    A cross-process lost update is still possible and accepted: the repo's other
    counters (usage, cache) make the same trade rather than take a file lock, and
    these counts are a floor, not a census — `list --usage` says so.
    """
    if not slugs:
        return
    with _USAGE_LOCK:
        data = _load_skill_usage()
        for slug in slugs:
            entry = data.get(slug) or {"count": 0}
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            data[slug] = entry
        path = _usage_path()
        tmp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{id(data)}")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            # a read-only home must never break a resolve


def _skills_root(source: Path, slug: str) -> Path:
    """Where a new skill dir for ``slug`` belongs inside a source root."""
    if (source / "skills").is_dir() or not (source / slug).exists():
        # prefer the nested layout only when it already exists, else flat
        return (source / "skills" / slug) if (source / "skills").is_dir() else (source / slug)
    return source / slug


def _archive_dir(source: Path, archive: Path | None = None) -> Path:
    """The graveyard a removal is parked in.

    Defaults beside the source, but ``archive`` lets a second manager point at
    the SAME graveyard so a rollback is the same `mv` whichever manager
    performed the removal.
    """
    return (archive or (source.parent / "_archive")) / "removed"


def _cmd_skills_add(source: Path, name: str, desc: str, fmt: str) -> int:
    if not name or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        print("mcptoon: add needs a slug name ([A-Za-z0-9._-]+)", file=sys.stderr)
        return 1
    dest = _skills_root(source, name)
    if dest.exists():
        print(f"mcptoon: {name} already exists at {dest}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    desc = desc or f"{name} — TODO: one line describing when to use this skill."
    (dest / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\n"
        f"TODO: write the skill body. Keep the trigger words in the description —\n"
        f"the router only reads the frontmatter before loading.\n",
        encoding="utf-8")
    if fmt == "json":
        print(json.dumps({"added": name, "path": str(dest)}, ensure_ascii=False))
    else:
        print(f"added {name}\n  {dest / 'SKILL.md'}")
        print("  next: write the body, then run `mcptoon skills sync` to publish it.")
    return 0


def _cmd_skills_remove(source: Path, name: str, fmt: str, *,
                       tombstone: bool = False, archive: Path | None = None) -> int:
    if not name:
        print("mcptoon: remove needs a slug name", file=sys.stderr)
        return 1
    target = None
    for base in (source / "skills", source):
        cand = base / name
        if cand.is_dir() and (cand / "SKILL.md").is_file():
            target = cand
            break
    if target is None:
        print(f"mcptoon: no skill named {name!r} under {source}", file=sys.stderr)
        return 1
    rel = os.path.relpath(target, source).replace("\\", "/")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    dest = _archive_dir(source, archive) / f"{stamp}_{name}"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(dest))
    except OSError as e:
        print(f"mcptoon: could not archive {name}: {e}", file=sys.stderr)
        return 1
    committed, detail = (False, "")
    if tombstone:
        committed, detail = _git_tombstone(
            source, rel, f"skills: remove {name} (tombstone)")
    if fmt == "json":
        out = {"removed": name, "archivedTo": str(dest), "tombstone": committed}
        if tombstone:
            out["git"] = detail
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"removed {name}")
        print(f"  archived to: {dest}   (recover with a plain move; nothing was deleted)")
        if tombstone:
            if committed:
                print(f"  ✅ git tombstone committed (path-scoped to {detail})")
            else:
                print(f"  ⚠ no git tombstone: {detail}")
        print("  next: run `mcptoon skills sync` so the views drop it too.")
    return 0


def _cmd_skills_list(index: dict, fmt: str, show_usage: bool,
                     include_aliases: bool = False) -> None:
    skills_list = index.get("skills", [])
    usage = _load_skill_usage() if show_usage else {}
    rows = []
    for s in skills_list:
        if s.get("alias_of") and not include_aliases:
            continue
        row = {"slug": s["slug"],
               "desc": _clean_desc(s.get("desc")).split("触发词")[0].strip()}
        if s.get("alias_of"):
            row["aliasOf"] = s["alias_of"]
        if show_usage:
            u = usage.get(s["slug"]) or {}
            row["uses"] = int(u.get("count", 0))
            row["lastUsed"] = u.get("last", "")
        rows.append(row)
    rows.sort(key=lambda r: (-r.get("uses", 0), r["slug"]) if show_usage else (r["slug"],))
    if fmt == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    if show_usage:
        print(f"{'uses':>5}  {'last':<11}  skill")
        for r in rows:
            print(f"{r['uses']:>5}  {r['lastUsed'] or '-':<11}  {r['slug']}")
        print("\n  counts cover skills mcptoon routed; a skill an agent loaded "
              "directly is invisible here.")
    else:
        for r in rows:
            print(f"{r['slug']:32s} {r['desc'][:70]}")
        print(f"\n  {len(rows)} skills (alias cards hidden; --all to include)")


def _cmd_skills(rest: list[str], fmt: str) -> None:
    action = rest[0] if rest else ""
    args = rest[1:]

    if action in ("", "help", "-h", "--help"):
        print(_skills_usage())
        return

    if action == "manifest":
        print(MANIFEST_ENTRY)
        return

    if action == "search":
        # Remote search needs no index (it falls back to one only if present).
        _cmd_skills_search(args, fmt)
        return

    if action == "sync":
        # Distribute a source catalog into every agent's skill folder. Needs no
        # index, so it is handled before the index gate below.
        positional = [a for a in args if not a.startswith("-")]
        source = Path(positional[0]).expanduser() if positional else None
        if source is None:
            roots = _default_roots()
            if not roots:
                print("mcptoon: no source. Usage: mcptoon skills sync <source-dir>",
                      file=sys.stderr)
                sys.exit(1)
            source = roots[0]
        if not source.is_dir():
            print(f"mcptoon: source is not a directory: {source}", file=sys.stderr)
            sys.exit(1)
        archive = Path(_flag(args, "--archive")).expanduser() if _flag(args, "--archive") else None
        dry = "--dry" in args or "--dry-run" in args
        catalog = _source_skills(source)

        # The version gate runs BEFORE anything is written to a view, so a
        # blocked skill is never half-published.
        gate_on = "--version-gate" in args
        if gate_on:
            gate = version_gate(catalog, _version_ledger_path(source),
                                force="--force" in args, update_ledger=not dry)
            blocked = gate["blocked"]
            if blocked:
                for slug, ver in blocked:
                    print(f"🚫 version gate blocked {slug}: content changed but "
                          f"version is still {ver!r} — bump it, or pass --force",
                          file=sys.stderr)
            if fmt != "json":
                if gate["onboarded"]:
                    print(f"🧮 version gate: onboarded {len(gate['onboarded'])} new skill(s)")
                if gate["legacy"]:
                    print(f"🧮 version gate: {len(gate['legacy'])} unversioned skill(s) "
                          f"changed — allowed, but add a version to gate them")
            allowed = set(gate["allowed"])
            catalog = {s: d for s, d in catalog.items() if s in allowed}
            if not catalog and blocked:
                print("mcptoon: every skill was blocked by the version gate; nothing synced",
                      file=sys.stderr)
                sys.exit(1)

        if "--derived" in args:
            derived = _flag(args, "--derived")
            views = (_derived_view_paths() if derived in ("", "all")
                     else {derived: _derived_view_paths().get(derived)
                           or Path(derived).expanduser()})
            views = {k: v for k, v in views.items() if v}
            rep = sync_derived(source, catalog, views, dry_run=dry, archive=archive)
            if fmt == "json":
                print(json.dumps(rep, ensure_ascii=False, indent=1))
            else:
                _print_derived_report(rep)
            return

        views = ([Path(p).expanduser() for p in positional[1:]] if len(positional) > 1
                 else _view_roots())
        strategy = "copy" if "--copy" in args else "link"
        report = sync_skills(source, views, strategy=strategy, dry_run=dry,
                             archive=archive, skills=catalog)
        _print_sync_report(report, fmt)
        return

    if action in ("add", "remove"):
        # Catalog management edits the SOURCE, so it needs a source but no index.
        positional = [a for a in args if not a.startswith("-")]
        roots = _default_roots()
        source = Path(positional[0]).expanduser() if len(positional) > 1 else (
            roots[0] if roots else None)
        name = positional[1] if len(positional) > 1 else (positional[0] if positional else "")
        if source is None:
            print("mcptoon: no skills root. Pass one: mcptoon skills "
                  f"{action} <source> <name>", file=sys.stderr)
            sys.exit(1)
        if action == "add":
            desc = _flag(args, "--desc")
            rc = _cmd_skills_add(source, name, desc, fmt)
        else:
            rc = _cmd_skills_remove(
                source, name, fmt, tombstone="--tombstone" in args,
                archive=(Path(_flag(args, "--archive")).expanduser()
                         if _flag(args, "--archive") else None))
        if rc:
            sys.exit(rc)
        return

    if action == "index":
        roots = [Path(a).expanduser() for a in args if not a.startswith("-")]
        if not roots:
            roots = _default_roots()
        if not roots:
            print("mcptoon: no skill roots found. Pass a path or set MCPTOON_SKILLS_ROOTS",
                  file=sys.stderr)
            sys.exit(1)
        index, path = build_and_save(roots)
        n_alias = sum(1 for s in index["skills"] if s.get("alias_of"))
        print(f"indexed {len(index['skills'])} skills "
              f"({n_alias} alias cards) from {len(index['roots'])} root(s)")
        print(f"index: {path}")
        if index["warnings"]:
            print(f"warnings: {len(index['warnings'])} "
                  f"(run 'mcptoon skills stats' for detail)")
        return

    # `list`/`stats` stay strict readers — they report on the index and must not
    # change it. `resolve`/`route` need a catalog to answer, so they build one on
    # first use and refresh a stale one, rather than making the user run
    # `skills index` first (the step that made "installed" not mean "working").
    if action in ("resolve", "route"):
        ensure_index()

    index = load_index()
    if not index:
        print("mcptoon: no skills index yet, and no skill roots were found to build "
              "one. Pass a path or set MCPTOON_SKILLS_ROOTS, then run: "
              "mcptoon skills index", file=sys.stderr)
        sys.exit(1)

    if action == "resolve":
        query = _query_of(args)
        if not query:
            print("mcptoon: resolve needs a query", file=sys.stderr)
            sys.exit(1)
        k = _parse_k(args, "--k", 5)
        # Opt-in: `resolve` is documented as instant and offline, so it does not
        # reach for MCP servers unless asked. Declared tools come from the index
        # and cost nothing; the tool bucket is a separate, explicit budget.
        tk = _parse_k(args, "--tools-k", 0, minimum=0)
        shortlist = resolve_shortlist(query, k, index=index)
        declared = _BM25(index).declared_tools(shortlist)
        tools = tool_shortlist(query, tk) if tk > 0 else []
        if fmt == "json":
            print(json.dumps({"query": query, "k": k, "shortlist": shortlist,
                              "declared_tools": declared, "tools": tools},
                             ensure_ascii=False, indent=1))
            return
        if not shortlist:
            print(f"no skill matches {query!r}")
        else:
            for i, c in enumerate(shortlist, 1):
                print(f"{i}. {c['slug']}  ({c['score']})")
                if c["desc"]:
                    print(f"   {c['desc'][:110]}")
        if declared:
            print(f"declared tools (from matched skills): {' '.join(declared)}")
        if tools:
            print("tools (separate bucket):")
            for t in tools:
                print(f"  {t['server']}/{t['name']}  ({t['score']})")
        return

    if action == "route":
        query = _query_of(args)
        if not query:
            print("mcptoon: route needs a query", file=sys.stderr)
            sys.exit(1)
        k = _parse_k(args, "--k", 5)
        endpoint = _flag(args, "--endpoint") or os.environ.get(
            "MCPTOON_SKILLS_ENDPOINT", "")
        models = [m.strip() for m in (
            _flag(args, "--model") or os.environ.get("MCPTOON_SKILLS_MODEL", "")
        ).split(",") if m.strip()]
        if not endpoint or not models:
            print("mcptoon: route needs an LLM. Set MCPTOON_SKILLS_ENDPOINT and "
                  "MCPTOON_SKILLS_MODEL, or pass --endpoint/--model.\n"
                  "Tip: 'mcptoon skills resolve' works with no LLM at all.",
                  file=sys.stderr)
            sys.exit(1)
        result = route(index, query, k, endpoint, models)
        if result.get("skill"):
            record_skill_use([result["skill"]])
        if fmt == "json":
            print(json.dumps(result, ensure_ascii=False, indent=1))
            return
        print(f"skill: {result['skill'] or '(no pick)'}  "
              f"confidence: {result['confidence']}  unanimous: {result['unanimous']}")
        for model, pick in result["picks"].items():
            print(f"  {model}: {pick or '(empty)'}")
        return

    if action == "list":
        _cmd_skills_list(index, fmt, show_usage="--usage" in args,
                         include_aliases="--all" in args)
        return

    if action == "stats":
        index_stats(index, fmt)
        return

    print(f"mcptoon: unknown skills action {action!r}\n", file=sys.stderr)
    print(_skills_usage())
    sys.exit(1)


def unroutable(index: dict) -> list[dict]:
    """Skills the router cannot reach, with the reason.

    A skill is unreachable when it offers the router nothing to match on: no
    description and no triggers from either the frontmatter or the body. Only its
    slug remains, and an opaque slug (``houtai``, ``kao``) is not something a user
    types.

    This is the honest answer to "how do you guarantee it works for a user who
    installs mcptoon and never reads the docs" — you do not, by promising; you do
    it by naming exactly which of their skills will fail, so they fix the handful
    that matter instead of all of them.
    """
    canonical, _ = resolve_aliases(index)
    out = []
    for slug, s in canonical.items():
        desc = _clean_desc(s.get("desc")).strip()
        triggers = s.get("triggers") or []
        if not desc and not triggers:
            out.append({"slug": s["slug"], "reason": "no description and no triggers — only the slug can find it"})
    return out


def _load_synonyms() -> dict[str, list[str]]:
    """Query-side expansion: a term maps to other spellings the catalog may use.

    A user says 分角色; the skill says 说话人分离. No amount of BM25 tuning matches
    a word that is absent from the document, so the *query* carries the synonyms
    instead of every skill carrying every phrasing. Measured on a 30-case Chinese
    set: +1 case fixed, 0 broken (28/30 -> 29/30 top-1).

    Zero-dependency and, like the gloss, data-only: the map lives in the same
    local file under ``_synonyms`` and an absent file means "no expansion". A
    hand-written Chinese *stopword* list was tried for the same problem and
    measured net-zero, so no list is shipped — only this.
    """
    raw = _load_json_file(_gloss_path())
    entries = raw.get("_synonyms") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        return {}
    out: dict[str, list[str]] = {}
    for term, reps in entries.items():
        if isinstance(reps, list):
            extra = [str(r) for r in reps if str(r).strip()]
            if extra:
                out[str(term).lower()] = extra
    return out


def _expand_query(query: str) -> str:
    """``query`` plus any synonym spellings it implies, or ``query`` unchanged."""
    synonyms = _load_synonyms()
    if not synonyms:
        return query
    low = (query or "").lower()
    extra: list[str] = []
    for term, reps in synonyms.items():
        if term in low:
            extra.extend(reps)
    return f"{query} {' '.join(extra)}" if extra else query


def _has_cjk(text: str) -> bool:
    """True when *text* contains at least one CJK character."""
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _cjk_unreachable(index: dict) -> list[str]:
    """Canonical slugs no CJK-language query can reach.

    ``_tokenize`` matches ASCII words plus CJK n-grams. A skill documented only
    in English has no CJK for a Chinese request to match, so it is invisible to
    ``resolve`` until a gloss entry supplies terms — this is the check that keeps
    that blind spot from growing back unnoticed, the way it did for 32 skills.
    Alias descriptions count, because BM25 folds them into the canonical entry.
    """
    canonical, alias_map = resolve_aliases(index)
    by_slug = {s["slug"].lower(): s for s in index.get("skills", [])}
    back: dict[str, list[str]] = defaultdict(list)
    for alias, target in alias_map.items():
        back[target].append(alias)
    gloss = _load_gloss()
    out: list[str] = []
    for slug, s in canonical.items():
        text = f"{s.get('desc') or ''} {' '.join(s.get('triggers') or [])}"
        for a in back.get(slug, []):
            as_ = by_slug.get(a, {})
            text += f" {as_.get('desc') or ''} {' '.join(as_.get('triggers') or [])}"
        if not _has_cjk(text) and not gloss.get(slug.lower()):
            out.append(slug)
    return sorted(out)


def index_stats(index: dict, fmt: str = "auto") -> None:
    """Catalog health — the cleanup that must precede any compression."""
    skills = index.get("skills", [])
    canonical, alias_map = resolve_aliases(index)
    by_slug = {s["slug"].lower(): s for s in skills}
    no_desc = [s["slug"] for s in skills if not _clean_desc(s.get("desc")).strip()]
    dupes: dict[str, list[str]] = defaultdict(list)
    for s in skills:
        dupes[s["slug"].lower()].append(s["root"])
    dupes = {k: v for k, v in dupes.items() if len(v) > 1}
    cli_twins = sorted(
        s["slug"] for s in skills
        if s["slug"].endswith("-cli") and s["slug"][:-4].lower() in by_slug
    )
    body_helped = sum(1 for s in skills if s.get("triggers") and not _triggers(s.get("desc") or ""))
    unreachable = unroutable(index)
    no_cjk = _cjk_unreachable(index)
    stats = {
        "skills": len(skills),
        "canonical": len(canonical),
        "aliases": len(alias_map),
        "no_description": no_desc,
        "duplicate_names": sorted(dupes),
        "cli_twins": cli_twins,
        "recovered_from_body": body_helped,
        "unroutable": unreachable,
        "no_cjk": no_cjk,
        "warnings": index.get("warnings", []),
    }
    if fmt == "json":
        print(json.dumps(stats, ensure_ascii=False, indent=1))
        return
    print(f"skills:     {stats['skills']}")
    print(f"canonical:  {stats['canonical']}  (aliases folded in: {stats['aliases']})")
    print(f"no-desc:    {len(no_desc)}")
    print(f"duplicates: {len(dupes)}")
    print(f"-cli twins: {len(cli_twins)}")
    print(f"recovered from body (desc had no triggers): {body_helped}")
    print(f"unroutable: {len(unreachable)}"
          + ("" if not unreachable else "  <-- these cannot be found by any query"))
    for u in unreachable[:10]:
        print(f"  {u['slug']}: {u['reason']}")
    print(f"no-CJK:     {len(no_cjk)}"
          + ("" if not no_cjk else "  <-- CJK queries cannot reach these; add a gloss entry"))
    for s in no_cjk[:10]:
        print(f"  {s}")
    print(f"warnings:   {len(stats['warnings'])}")
    for w in stats["warnings"][:10]:
        print(f"  [{w['code']}] {w['message']}")
