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
import json
import math
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict
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


def _iter_skill_dirs(root: Path):
    """Yield ``(slug, skill_md_path)`` for one root.

    Accepts both layouts seen in the wild: ``<root>/<slug>/SKILL.md`` and
    ``<root>/skills/<slug>/SKILL.md``. One level only, never recursive.
    """
    for base in (root, root / "skills"):
        if not base.is_dir():
            continue
        try:
            children = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            md = child / "SKILL.md"
            if md.is_file():
                yield child.name, md


def scan_roots(roots: list[Path]) -> dict:
    """Build an index dict from skill roots. Read-only; never writes to roots."""
    from .plugin import parse_skill_frontmatter, parse_skill_md  # local: import-light

    skills: list[dict] = []
    warnings: list[dict] = []
    seen: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            warnings.append({"code": "ROOT_MISSING", "message": f"skill root not found: {root}"})
            continue
        for slug, md in _iter_skill_dirs(root):
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
        "skills": skills,
        "warnings": warnings,
    }


def build_and_save(roots: list[Path]) -> tuple[dict, Path]:
    index = scan_roots(roots)
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
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


class _BM25:
    """Ranked retrieval over canonical skills.

    Each canonical skill's document merges its own slug/description/triggers with
    those of every alias that points at it, so a query using the alias name
    still reaches the canonical entry.
    """

    def __init__(self, index: dict):
        canonical, alias_map = resolve_aliases(index)
        self.alias_map = alias_map
        self.descs: dict[str, str] = {}
        back: dict[str, list[str]] = defaultdict(list)
        for alias, target in alias_map.items():
            back[target].append(alias)

        by_slug = {s["slug"].lower(): s for s in index.get("skills", [])}
        docs: dict[str, Counter] = {}
        df: Counter = Counter()
        for slug, s in canonical.items():
            parts = [slug, s.get("name") or "", s.get("desc") or "", " ".join(s.get("triggers") or [])]
            for a in back.get(slug, []):
                as_ = by_slug.get(a, {})
                parts += [a, as_.get("desc") or "", " ".join(as_.get("triggers") or [])]
            counts = Counter(_tokenize(" ".join(parts)))
            docs[slug] = counts
            self.descs[slug] = s.get("desc") or ""
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
        k1, b = 1.5, 0.75
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
        """Top-k ``[{slug, score, desc}]``, best first."""
        q = _tokenize(query)
        ranked = sorted(
            ((self._score(q, d), slug) for slug, d in self.docs.items()),
            key=lambda pair: (-pair[0], pair[1]),
        )
        return [
            {"slug": slug, "score": round(score, 4), "desc": self.descs.get(slug, "")}
            for score, slug in ranked[:max(1, k)]
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

def _skills_usage() -> str:
    return (
        "mcptoon skills — index and route a skill catalog without keeping it in context\n\n"
        "  mcptoon skills index [ROOT ...]        Scan roots, build the on-disk index\n"
        "  mcptoon skills resolve <query> [--k N] BM25 shortlist (no LLM, no tokens)\n"
        "  mcptoon skills route <query> [--k N]   Shortlist then let an LLM pick\n"
        "                    [--model M[,M2]] [--endpoint URL]\n"
        "  mcptoon skills stats                   Catalog health (dupes, aliases, no-desc)\n"
        "  mcptoon skills manifest                The one-line entry to keep in context\n\n"
        "Roots default to MCPTOON_SKILLS_ROOTS or ~/.claude/skills and friends.\n"
        "Route endpoint/model default to MCPTOON_SKILLS_ENDPOINT / _MODEL."
    )


_VALUE_FLAGS = ("--k", "--tools-k", "--model", "--endpoint")


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


def _cmd_skills(rest: list[str], fmt: str) -> None:
    action = rest[0] if rest else ""
    args = rest[1:]

    if action in ("", "help", "-h", "--help"):
        print(_skills_usage())
        return

    if action == "manifest":
        print(MANIFEST_ENTRY)
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

    index = load_index()
    if not index:
        print("mcptoon: no skills index yet. Run: mcptoon skills index", file=sys.stderr)
        sys.exit(1)

    if action == "resolve":
        query = _query_of(args)
        if not query:
            print("mcptoon: resolve needs a query", file=sys.stderr)
            sys.exit(1)
        k = int(_flag(args, "--k", "5") or 5)
        # Opt-in: `resolve` is documented as instant and offline, so it does not
        # reach for MCP servers unless asked. Declared tools come from the index
        # and cost nothing; the tool bucket is a separate, explicit budget.
        tk = int(_flag(args, "--tools-k", "0") or 0)
        bm = _BM25(index)
        shortlist = bm.search(query, k)
        declared = bm.declared_tools(shortlist)
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
        k = int(_flag(args, "--k", "5") or 5)
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
        if fmt == "json":
            print(json.dumps(result, ensure_ascii=False, indent=1))
            return
        print(f"skill: {result['skill'] or '(no pick)'}  "
              f"confidence: {result['confidence']}  unanimous: {result['unanimous']}")
        for model, pick in result["picks"].items():
            print(f"  {model}: {pick or '(empty)'}")
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
        desc = (s.get("desc") or "").strip()
        triggers = s.get("triggers") or []
        if not desc and not triggers:
            out.append({"slug": s["slug"], "reason": "no description and no triggers — only the slug can find it"})
    return out


def index_stats(index: dict, fmt: str = "auto") -> None:
    """Catalog health — the cleanup that must precede any compression."""
    skills = index.get("skills", [])
    canonical, alias_map = resolve_aliases(index)
    by_slug = {s["slug"].lower(): s for s in skills}
    no_desc = [s["slug"] for s in skills if not s.get("desc")]
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
    stats = {
        "skills": len(skills),
        "canonical": len(canonical),
        "aliases": len(alias_map),
        "no_description": no_desc,
        "duplicate_names": sorted(dupes),
        "cli_twins": cli_twins,
        "recovered_from_body": body_helped,
        "unroutable": unreachable,
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
    print(f"warnings:   {len(stats['warnings'])}")
    for w in stats["warnings"][:10]:
        print(f"  [{w['code']}] {w['message']}")
