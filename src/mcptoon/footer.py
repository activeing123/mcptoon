"""The one savings broadcast, shared by every surface that can show it.

Why this module exists
----------------------
The savings line used to live only inside `cli._cmd_footer_facts`, and the only
thing that ever put it in front of a user was a *model* choosing to run that
command and paste the result. That is a soft channel: it depends on the agent
reading a directive, remembering it, and complying. When it was wired into DSH —
which speaks no MCP at all — nothing ever appeared, and the tool that compresses
the context was itself invisible.

The fix is to stop asking the model and start stamping the payloads mcptoon
already controls. There are exactly two such payloads:

1. **Any mcptoon CLI invocation.** Every agent that can run a shell sees the
   command's output, so a footer on the CLI reaches Codex, DSH, Gemini CLI,
   Aider and anything else with a terminal. `cli.main()` is the single entry
   point, and it prints this block to *stderr* so machine-readable stdout
   (`--json`, piped TOON) stays byte-exact.
2. **The first proxied tool result of an MCP session.** `serve._handle_call_tool`
   is the single funnel every successful upstream call passes through, so one
   stamp there is seen by Claude Desktop, Cursor, Cline, Windsurf, VS Code
   Copilot and any other MCP client — again with no per-client configuration and
   no reliance on the model's cooperation.

Both are gated by `config.footer_enabled()`, i.e. the same `footer` setting the
user already has (`mcptoon config set footer off`).

Three lines, since 2026-09-26
-----------------------------
The broadcast counts **every** axis of the savings story, and it did not always.
It counted the tool catalog; it never counted skills, so the product's own
headline (it manages both halves of a session's toolbox) was invisible on the
surface users read most; and it said nothing about result compression, which is
on by default since 2026-09-26.

The 2026-09-26 redesign (second pass) fixed a size problem the first pass
introduced. The first three-line version put the raw token pair, two percentages
and the running call count on line 1; measured at 166 display columns it wrapped
to three terminal rows on every turn. Every line is now budgeted at **≤80 display
columns** (CJK counts as two), so nothing wraps on an 80-column terminal, and the
figures that no longer fit on line 1 moved to line 2 or to `mcptoon report`.

* `line()` — the tools half, one figure per unit: reduction (`96→9`), rate
  (`省 88%`), and the **cumulative** estimate (`≈省 75M·4,000次`) with the moving
  call count beside it.
* `skills_line()` — the skills saving, the `mcptoon report` pointer, and the
  `/mcptoon` skill pointer. Omitted, never zeroed, when there is no skill catalog.
* `compression_line()` — result compression. Always printed: "off" is a fact the
  reader needs when they have turned it off, and the default line tells them the
  originals are recoverable. When *this run* compressed something, it says so and
  points at `/mcptoon` instead.

`block()` stacks them with the `note:` caveat last.

Cost, measured rather than guessed: the tools line is ~74 tokens on the
tiktoken cl100k_base caliber and a full catalog compression saves ~18,800. The
skills half is the expensive one to *measure* — tokenizing every SKILL.md body is
~481 ms and 1,030,628 tokens here — so it is cached and revalidated at most once
per 5-minute TTL (`skills.cached_skill_token_figures`), never recomputed per
turn. That is why the MCP side stamps **once per session** instead of on every
result: stamping every call would break even at ~162 calls, and a feature that can
eat its own savings is not a feature. The per-turn *narrative* line stays the
model's job (see `serve._INSTRUCTIONS` and the AGENTS.md block); this module only
guarantees that the numbers are on screen.

Repeat, not just cost
---------------------
A line that says the same thing every turn stops being read — that is the second
complaint, and cost was never its cause. The catalog figures change only when the
machine does, so the line now carries a figure that moves (`calls_recorded`, the
running total of calls routed through the gateway) and surfaces can skip a
byte-identical repeat via `changed`/`remember`, backed by
`config.FOOTER_STATE_FILE`. The change gate compares the **figure lines** and
ignores the `note:` age that ticks every minute, so a fresh caveat cannot
resurrect an identical figure block. The live figure makes the line worth
reading; the change gate stops it from being noise. `mcptoon footer-facts` still
prints on demand, so an agent that wants the line every turn can still get it.

One estimate, always labelled
-----------------------------
`≈ saved so far` (`_cumulative_estimate`) is the only number on any surface that
rests on an assumption — calls routed × the per-turn saving, assuming every
routed call stands in for a turn that would have carried the full catalog. That
makes it a lower bound, which is why it carries `≈` and never appears without it.

Single caliber (D3 rule): every figure comes from `bench._tokenizer`, the same
per-tool sums `status` and `stats` use, so all four surfaces agree.

Language
--------
The line is a sentence, so it has to pick a language, and this project cannot
guess: the author's machine reports a Chinese Windows UI language while its shell
exports `LANG=en_US.UTF-8`. `config.resolve_lang()` owns that decision (explicit
`lang` setting > `MCPTOON_LANG` > OS UI language > LC_*/LANG > English), and every
surface reaches it through this module, so one setting moves all of them.

Two things stay ASCII in both languages, deliberately: the `mcptoon:` prefix and
the `note: ` label. They are the stable handles every format test and every
parser keys on — localising them would turn "which language" into a parsing
problem for consumers who never asked for one. The `note: ` label doubles as the
split point for the change gate (`_figures_of`), which is only safe because it is
not translated.
"""

from __future__ import annotations

import json
import math

__all__ = ["facts", "line", "skills_line", "compression_line", "note", "block",
           "enabled", "lang", "changed", "remember", "MARK",
           "current_mode", "cli_credit", "cli_credit_line", "tool_schema_tokens",
           "next_action_hint", "note_next_action_shown", "caller_can_shell"]

# The savings line is meant to be *noticed* — the entire point of this feature is
# that an install stops being invisible. A single emoji is the cheapest way to
# make a line of numbers catch the eye in a chat transcript, and the user asked
# for this one by name (2026-09-22). Kept as a constant so it is trivial to
# change or drop; the string after it stays byte-identical to `footer-facts`'
# first line, which every format test pins on the `mcptoon:` prefix.
MARK = "🎉"


def enabled() -> bool:
    """Whether the footer is on. Same switch as every other surface."""
    from . import config as cfg

    return cfg.footer_enabled()


def lang() -> str:
    """The language these strings speak: 'zh' or 'en'.

    A thin re-export on purpose: surfaces import `footer`, not `config`, and one
    decision point is what keeps the CLI tail and the MCP stamp in step.
    """
    from . import config as cfg

    return cfg.resolve_lang()


def _render_note(f: dict, lng: str) -> str | None:
    """The staleness/coverage caveat in `lng`, rendered from the figures.

    Both caveats can be true at once — a server that never resolves plus an old
    cache — and they must both surface, so this appends to a list instead of
    choosing a branch. An earlier version used `elif`, which let an uncached
    server hide the staleness: on the author's machine the cache was 2.1h old
    against a 5-minute TTL and the note still read as though only the tool count
    were partial. These figures get quoted verbatim into a chat turn, so a stale
    number reported as fresh is worse than a noisy note.

    The English wording is the same sentence the JSON payload has always carried,
    shortened (2026-09-26) only where it wrapped: `not cached yet` → `not cached`,
    `(cache TTL N min)` → `(TTL N)`, and the tail clause unified. The caveats
    themselves are unchanged — tests and downstream consumers key on them.
    """
    zh = lng == "zh"
    servers = int(f.get("servers") or 0)
    uncached = int(f.get("servers_uncached") or 0)
    ttl = int(f.get("cache_ttl_seconds") or 0)
    age = f.get("cache_age_seconds")

    if not servers:
        return "尚未配置任何服务器" if zh else "no servers configured"

    parts = []
    if uncached == servers:
        parts.append("目录还没缓存过 - 先跑一次 `mcptoon manifest`" if zh
                     else "catalog not cached yet - run `mcptoon manifest` once")
    elif uncached:
        # `1/12` not `1 of 12`: the worst case (uncached *and* a four-digit age)
        # measured 82 columns with the long form and 79 with this one.
        parts.append(f"{servers} 个服务器里有 {uncached} 个还没缓存" if zh
                     else f"{uncached}/{servers} servers not cached")
    if age is not None and age > ttl:
        # No `已` in the Chinese form: it pushed the worst case to 81 columns.
        parts.append(f"目录 {age / 60:.0f} 分钟没更新（TTL {ttl // 60}）" if zh
                     else f"catalog is {age / 60:.0f} min old (TTL {ttl // 60})")
    if not parts:
        return None
    # One generic tail, not one per caveat: the old line appended "数字只覆盖已缓存
    # 的服务器" unconditionally, so a *stale-but-fully-cached* machine got a sentence
    # about uncached servers it did not have. The specific clause above already
    # names any uncached servers; this only has to say the figures can be behind.
    # Wording is trimmed to keep the worst case (both caveats, four-digit age) at
    # 71 display columns — the old wording measured 90 and wrapped.
    parts.append("数字可能滞后" if zh
                 else "figures may lag")
    return ("；" if zh else "; ").join(parts)


def gateway_footprint() -> int | None:
    """What the gateway itself costs an agent, in tokens — or None if unknown.

    This is the figure the old footer was missing, and the reason the line read
    as a 24% saving on a product whose whole claim is much larger. Every other
    number here compares full schemas against *simplified* schemas — the same
    tools, described more tersely — measured at 24.3% on the author's machine.
    But under the default ``exposure=compact`` the upstream schemas are withheld
    entirely, and the agent's whole tool list is mcptoon's own 8 meta-tools plus
    the compact directive: 21,074 → 2,607 tokens (87.6%). Quoting 24% in the
    headline understated the product ~3.6x while *looking* like the conservative,
    honest number — the worst kind of wrong.

    Counted the way `serve._handle_list_tools` builds it: the native tool set
    through the same schema simplification, plus the compact directive that rides
    in context only while the upstream list is withheld. Best-effort: any failure
    returns None and the caller keeps the simplified-schema figure rather than
    inventing a number.
    """
    from . import native_tools
    from . import schema_simplifier
    from .bench import _tokenizer

    encode, _caliber, _exact = _tokenizer()
    total = 0
    for defn in native_tools.native_tools():
        total += max(1, int(encode(json.dumps(
            schema_simplifier.simplify_tool_def(defn), ensure_ascii=False))))
    try:
        from . import serve as serve_mod

        total += max(1, int(encode(serve_mod._COMPACT_TOOLS_DIRECTIVE)))
    except Exception:
        pass
    return total or None


def gateway_savings(full_tokens: int) -> tuple[int | None, float | None]:
    """``(gateway_tokens, gateway_pct)`` against a full-schema baseline.

    The one place the gateway percentage is computed, so the footer, ``status``
    and ``stats`` cannot round or baseline it differently — the 2026-09-26 audit
    found three surfaces quoting three savings numbers for one machine. Returns
    ``(None, None)`` when the baseline is empty or the gateway would not actually
    be smaller, so a caller omits the figure rather than printing a negative or
    undefined one.
    """
    if not full_tokens:
        return None, None
    gw = gateway_footprint()
    if not gw or full_tokens <= gw:
        return None, None
    return gw, round((full_tokens - gw) / full_tokens * 100, 1)


def _catalog_fingerprint(servers: list[str]) -> str:
    """A stat-only fingerprint of every cached schema file: `path:size:mtime`.

    Reads no file contents, so it costs ~0.1 ms for the whole catalog. Any change
    to a cache file (a refresh, a new server, a deletion) changes the fingerprint
    and invalidates the memoised token totals.

    Includes the legacy single-file cache (`schema_cache.json`), not just the
    per-server files: `cache._entry_for` falls back to it, so a server served from
    the legacy file must still bust the memo when that file changes (measured
    2026-10-19: omitting it made `footer-facts` return stale totals in tests).
    """
    import os

    from . import cache as cache_mod

    parts = []
    for name in servers:
        try:
            st = os.stat(cache_mod._server_file(name))
            parts.append(f"{name}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:-")
    try:
        st = os.stat(cache_mod._legacy_file())
        parts.append(f"legacy:{st.st_size}:{st.st_mtime_ns}")
    except OSError:
        parts.append("legacy:-")
    return "|".join(parts)


def _catalog_token_totals(servers: list[str], encode, caliber: str):
    """`(tools, full_tokens, slim_tokens, name_index_tokens)` for the cached catalog, memoised.

    Tokenizing every schema is the slow part of `facts()` and it was redone on
    every prompt. The result is cached in `_TOKEN_TOTALS_CACHE` keyed by a stat
    fingerprint plus the token caliber, so a turn that changes nothing pays a
    stat walk instead of a re-tokenize. Falls back to a full recompute on any
    error — a wrong figure is never cached, and a cache write failure only costs
    the next caller a recompute.

    The fourth element is the ``manifest`` name index — the cheap list of tool
    names a CLI call pulls to *pick* a tool. It is the per-use cost of the CLI
    path, so `cli_credit` can name what a call actually pays instead of quoting
    the gateway's fixed cost. Built with the exact ``compact()`` shape `bench`
    uses for its "manifest (name index)" row, so the two surfaces agree.
    """
    import json

    from . import cache as cache_mod
    from . import schema_simplifier
    from .output import compact

    fp = _catalog_fingerprint(servers)
    key = f"{caliber}\x00{fp}"
    cached = _TOKEN_TOTALS_CACHE.get(key)
    if cached is not None:
        return cached
    persisted = _load_token_totals(key)
    if persisted is not None:
        _TOKEN_TOTALS_CACHE[key] = persisted
        return persisted

    total_tools = 0
    full_tokens = 0
    slim_tokens = 0
    name_map: dict[str, list[str]] = {}
    for name in servers:
        tools, _age = cache_mod.get_cached_tools_any_age(name)
        if tools is None:
            continue
        names = []
        for t in tools:
            if not isinstance(t, dict) or "error" in t:
                continue
            total_tools += 1
            full_tokens += max(1, int(encode(json.dumps(t, ensure_ascii=False))))
            slim_tokens += max(1, int(encode(json.dumps(
                schema_simplifier.simplify_tool_def(t), ensure_ascii=False))))
            names.append(t.get("name", ""))
        if names:
            name_map[name] = names
    try:
        name_index_tokens = max(1, int(encode(compact(name_map)))) if name_map else 0
    except Exception:
        name_index_tokens = 0

    result = (total_tools, full_tokens, slim_tokens, name_index_tokens)
    # Keep the memo small: one entry per caliber/fingerprint is plenty, and a
    # bounded dict never grows with the number of turns a long session runs.
    if len(_TOKEN_TOTALS_CACHE) > 8:
        _TOKEN_TOTALS_CACHE.clear()
    _TOKEN_TOTALS_CACHE[key] = result
    # Best-effort: also persist so a *new process* (the usual case — every prompt
    # is a fresh `mcptoon statusline`) skips the recompute too.
    _save_token_totals(key, result)
    return result


# Process-local memo. Persisted across processes in a small JSON file beside the
# schema cache; both are keyed by the same stat fingerprint.
_TOKEN_TOTALS_CACHE: dict[str, tuple[int, int, int, int]] = {}
_TOKEN_TOTALS_FILE = "footer-token-totals.json"


def _token_totals_path():
    from . import cache as cache_mod

    return cache_mod._cache_dir() / _TOKEN_TOTALS_FILE


def _load_token_totals(key: str):
    import json

    try:
        with open(_token_totals_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("key") == key:
            vals = data.get("totals")
            if isinstance(vals, list) and len(vals) in (3, 4):
                got = tuple(int(x) for x in vals)
                # A file written before `name_index_tokens` existed has three
                # elements; pad the fourth with 0 rather than discard a valid
                # memo and re-tokenize the whole catalog on the next prompt.
                return got if len(got) == 4 else (got[0], got[1], got[2], 0)
    except (OSError, ValueError, TypeError):
        pass
    return None


def _save_token_totals(key: str, totals) -> None:
    import json
    import os

    try:
        path = _token_totals_path()
        # Never create the cache directory. `mcptoon uninstall` deletes it, and the
        # footer runs again afterwards; mkdir here would resurrect the directory and
        # break the promise that uninstall leaves no cache behind (measured
        # 2026-10-19: this exact file recreated it and failed the uninstall test).
        if not path.parent.is_dir():
            return
        # Unique temp: the footer writes this at the end of nearly every command,
        # so two concurrent CLI processes shared a fixed ".tmp" and raced — one
        # os.replace won, the loser raised FileNotFoundError (swallowed) and the
        # cache could end up torn. mkstemp keeps each writer's scratch private.
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".toktot-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "totals": list(totals)}))
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass


def facts() -> dict:
    """The savings numbers, cache-only — never spawns a server.

    Mirrors `cli._cmd_footer_facts`: reads the schema cache at whatever age it
    has and reports the age in `note` rather than refreshing. The obvious
    implementation — call `status` — costs ~23s cold here because it spawns
    every configured server, which is unusable inside a tool call. A figure the
    caller can date is honest; a 23-second pause is not.

    Returns a dict with the keys `cli._cmd_footer_facts --json` documents.

    Two savings figures, and the difference between them is the point
    (2026-09-26 audit):

    * ``savings_pct`` — full vs **simplified** schemas, same tools (24.3% here).
      This is what ``manifest --slim`` buys, and it is the smaller, secondary
      claim.
    * ``gateway_pct`` — full schemas vs the **compact gateway** the agent
      actually loads: 8 meta-tools plus the directive (87.6% here). This is what
      installing mcptoon buys, and it is the honest headline.
    """
    from . import cache as cache_mod
    from . import config as cfg
    from . import usage as usage_mod
    from .bench import _tokenizer

    servers = cfg.list_servers()
    encode, caliber, _exact = _tokenizer()

    # Tokenizing every full schema is the expensive part (~440 ms on 209 tools,
    # measured 2026-10-19) and it was being redone on every prompt — `statusline`
    # and `footer-facts` both call this and both run per turn. The totals are
    # memoised on a stat-only fingerprint so an unchanged catalog costs ~0 ms.
    total_tools, full_tokens, slim_tokens, name_index_tokens = _catalog_token_totals(
        servers, encode, caliber)

    # Age and the uncached count are cheap (loading the cache is ~24 ms) and are
    # not cacheable — they change as the clock moves, not as the files change.
    oldest_age: float | None = None
    uncached = 0
    for name in servers:
        tools, age = cache_mod.get_cached_tools_any_age(name)
        if tools is None:
            uncached += 1
            continue
        if age is not None and (oldest_age is None or age > oldest_age):
            oldest_age = age

    saved = max(0, full_tokens - slim_tokens)
    pct = round(saved / full_tokens * 100, 1) if full_tokens else 0.0

    try:
        calls = int(usage_mod.get_usage_stats().get("total_calls", 0))
    except Exception:
        calls = 0

    ttl = cache_mod._get_ttl()
    # The gateway figure needs a non-empty cache to mean anything: with zero
    # cached tools there is no "what the agent would otherwise have loaded"
    # baseline, and a percentage against nothing is a lie. None → the line omits
    # it and the simplified-schema figure stands alone.
    gw_tokens, gw_pct = gateway_savings(full_tokens) if total_tools else (None, None)

    # The skills half (2026-09-26). Cache-only and best-effort, like everything
    # else here: `cached_skill_token_figures()` revalidates by a stat walk and
    # tokenizes only when the catalog actually changed, so the common turn pays
    # ~200 ms and no tokenizing. Absent → the skills line is omitted, never
    # invented.
    sk_count = sk_native = sk_pointer = 0
    try:
        from . import skills as skills_mod

        sk_figs = skills_mod.cached_skill_token_figures()
        sk_count = int(sk_figs.get("count") or 0)
        sk_native = int(sk_figs.get("native_tokens") or 0)
        sk_pointer = int(sk_figs.get("pointer_tokens") or 0)
    except Exception:
        pass

    figures = {
        "servers": len(servers),
        "tools": total_tools,
        "tokens_full": full_tokens,
        "tokens_slim": slim_tokens,
        "name_index_tokens": name_index_tokens,
        "tokens_saved": saved,
        "savings_pct": pct,
        "gateway_tokens": gw_tokens,
        "gateway_saved": (full_tokens - gw_tokens) if gw_tokens else None,
        "gateway_pct": gw_pct,
        "token_caliber": caliber,
        "calls_recorded": calls,
        "cache_age_seconds": round(oldest_age, 1) if oldest_age is not None else None,
        # The raw caveat inputs travel with the figures so `note(..., lng="zh")`
        # can translate a sentence it already has the numbers for, without
        # re-reading a cache — or, worse, contacting a server to do it.
        "servers_uncached": uncached,
        "cache_ttl_seconds": ttl,
        "skills": sk_count,
        "skills_tokens_full": sk_native,
        "skills_pointer_tokens": sk_pointer,
    }
    # English is the payload's language, whatever the user's is: `--json` is a
    # machine channel and the note in it is data, not a message to a person.
    figures["note"] = _render_note(figures, "en")
    return figures


def _cumulative_estimate(d: dict) -> tuple[int, int] | None:
    """``(calls, tokens)`` for the "≈ saved so far" figure, or None when unknown.

    The one number on the line that is an *estimate*, and the only one that is
    labelled with ``≈``. It multiplies the calls this machine has routed by what
    one turn saves when the catalog is not resident — the same per-turn figure the
    line prints two fields earlier. The assumption, stated plainly: every routed
    call stands in for a turn that would otherwise have carried the full schema
    list. That makes it a **lower bound** (an agent that made several calls in one
    turn is counted more than once) and it is why the figure carries ``≈`` and
    never appears without it.

    Deliberately computed from `calls_recorded` and the gateway pair, both already
    on the line: a "cumulative" that needed its own bookkeeping could drift from
    the figures beside it.

    The gateway *key* must be present, not merely non-zero: a legacy `--json`
    payload or hand-built dict without it would otherwise read `gateway_tokens`
    as 0 and multiply the calls by the *full* catalog size, inventing a saving
    that dwarfs every real one. The 2026-09-26 redesign moved this estimate onto
    `skills_line()`, which every dict reaches, so the guard is now load-bearing.
    """
    if "gateway_tokens" not in d or "gateway_pct" not in d:
        return None
    calls = int(d.get("calls_recorded") or 0)
    full = int(d.get("tokens_full") or 0)
    gw = int(d.get("gateway_tokens") or 0)
    if calls <= 0 or full <= gw:
        return None
    return calls, calls * (full - gw)


def _human_tokens(n: int) -> str:
    """`76M` / `4.3B` / `12,345` — short enough for a one-line broadcast."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        # Round to whole millions FIRST, then promote if rounding tipped it to
        # 1000 — otherwise 999,500,000 printed as "1000M" (a unit nobody reads as
        # ~1B) instead of "1B".
        millions = round(n / 1_000_000)
        if millions >= 1000:
            return f"{millions / 1000:.1f}B".replace(".0B", "B")
        return f"{millions}M"
    return f"{n:,}"


def floor_pct(saved: int, total: int, places: int = 2) -> float | None:
    """``saved/total`` as a percentage, *floored* to `places` decimals.

    Floored, not rounded, and that is the whole point. The skills pointer is 39
    tokens against 1,030,628 — 99.9962% saved — and any ordinary rounding prints
    ``100%``, which reads as a typo (nothing is ever fully free) and overstates the
    claim. Flooring gives ``99.99%``: true, and obviously a measurement rather than
    a marketing round number.

    Shared by the footer and `mcptoon report` so the two surfaces cannot print
    different percentages for the same pair of numbers — the exact
    "same machine, two numbers" failure this project keeps having to remove.

    Returns None when there is nothing to divide.
    """
    import math

    if not total or total <= 0 or saved <= 0:
        return None
    scale = 10 ** places
    return math.floor(saved / total * 100 * scale) / scale


def display_pct(saved: int, total: int) -> str:
    """A percentage for a *headline*: whole number, floored, never a rounded `100`.

    The tools line, `status`, `welcome` and `report` all used ``{pct:.0f}%``, which
    rounds 99.61% up to `100%` — mathematically wrong ("省 100%" claims the payload
    is free) and, worse, it disagrees with the skills line on the same screen, which
    floors (99.99%). Both halves of one report then quote different rules for the
    same kind of number (reported 2026-10-17: `status` printed 640,834 → 2,499 as
    "省 100%"; the true figure is 99.61%). Floor to a whole percent so every
    surface tells the same story: a big saving reads `99%`, and only an *exact*
    zero-cost would ever read `100` (and that never happens, because the gateway
    always costs a few tokens). Two-decimal callers (the skills line) keep using
    `floor_pct` directly.
    """
    pct = floor_pct(saved, total, places=0)
    return "" if pct is None else f"{pct:.0f}"


# ── CLI-mode credit ──────────────────────────────────────────────────────────
# Under `cli` delivery, the gateway is NOT wired into the agent: the agent runs
# `mcptoon call` through a shell and only ever pulls the one schema it needs. So
# the "209→9 via the gateway" story (a *serve* fact) is not what a CLI user is
# living. What a CLI user actually banks is "zero resident": every call avoids
# loading the whole catalog into context. These helpers give that second caliber
# one name, so every surface can print it instead of borrowing the gateway's.
#
# It is deliberately a *second* figure, never a replacement: a serve user's real
# saving is the small fixed gateway cost, and quoting "resident avoided" at them
# would overstate it. The caller decides which caliber fits the current mode.

def current_mode() -> str:
    """The live delivery mode (`cli` / `serve` / `direct` / `empty`), or "".

    A thin, import-cycle-free read of `mode.detect()` — the same classifier
    `status`, `mode` and `report` use, so a CLI-caliber line here can never
    disagree with the mode those screens name. Best-effort: any failure yields
    "" and the caller falls back to the gateway headline rather than guessing.
    """
    try:
        from . import mode as mode_mod

        return str(mode_mod.detect().get("mode") or "")
    except Exception:
        return ""


def caller_can_shell() -> bool:
    """Whether the reader asking for this footer is an agent that can run a shell.

    `current_mode()` classifies the *machine*; this classifies the *reader*, and on
    a `serve-alongside` machine the two disagree. Measured 2026-11-11: a DSH session
    was shown `未接管·未省` on every turn — a fact about four other applications
    (Claude Desktop, Cline, VS Code Copilot, Claude Code still holding direct MCP
    entries) — while DSH itself was already on the cheapest route that exists (no
    MCP mounted at all, 0 resident, the whole catalog fetched one schema at a time).
    A saving claim about someone else's config, printed at a reader who is already
    optimal, reads as "you are wasting tokens" and is simply false.

    `mode.detect_host()` reads the markers an agent's own process environment
    carries (`DSH_SHELL`, `CLAUDECODE`, `CODEX_HOME`, ...). Unknown returns False,
    and that is deliberate: guessing "yes" would print the CLI credit to a GUI user
    whose real cost is a different (serve) number.
    """
    try:
        from . import mode as mode_mod

        return mode_mod.detect_host().get("shell") is True
    except Exception:
        return False


def _cli_route_line(d: dict, lng: str) -> str:
    """The headline for a reader already on the CLI leg.

    Says the one true thing about *its* cost: nothing is resident. The absolute
    figure is the honest one here (`_human_tokens(full)`), not a rate — a rate
    depends on how many tools the reader *would* have loaded, which is the serve
    story, not this one (same rule as `cli_credit_line`).
    """
    calls = int(d.get("calls_recorded") or 0)
    full = d.get("tokens_full") or 0
    kept = _human_tokens(full) if full else ""
    cal = d.get("token_caliber") or ""
    # The 80-column budget binds before anything else (`test_footer_broadcast` grows
    # the catalog until it does), and the `[caliber]` handle eats 24 of those columns,
    # so the line keeps the two figures that carry the claim — what never loaded, and
    # how many calls that covered — and abbreviates `calls` to `c` in English for the
    # same reason the machine headline does.
    # Wording, third pass (owner asked twice, 2026-11-11):
    #   1. `全量 655,518 未加载` — `未加载` reads as "not loaded *yet*" (pending, or a
    #      failure) and never names the destination.
    #   2. `655,518 没进上下文` — true and unambiguous, but states only the fact and
    #      never the benefit: a savings line has to say what was saved.
    #   3. This: `0 常驻 · 省 655,518`. The order is load-bearing. `省 655,518` on its
    #      own invites the cumulative reading ("I have saved 655,518 so far"), and the
    #      cumulative figure is a different caliber — `mcptoon report` measures it at
    #      ~340M for this machine and labels it a lower bound. Leading with the
    #      resident fact ("0 常驻") anchors the number to the axis it belongs to, so
    #      the line claims exactly what it can prove and still names the saving.
    if lng == "zh":
        parts = [f"{MARK} mcptoon: CLI 路线"]
        if kept:
            parts.append("0 常驻")
            # `/轮` (owner's call, 2026-11-11): the bare `省 655,518` still read as a
            # running total, because that is what a savings figure usually is. The
            # suffix says it is the per-turn figure, which is the one this line can
            # prove — `mcptoon report` keeps the cumulative (a lower-bound estimate on
            # the serve caliber, explicitly not a CLI measurement).
            parts.append(f"省 {kept}/轮")
        if calls:
            parts.append(f"{calls:,} 次")
        return " · ".join(parts) + f" [{cal}]"
    # English uses the phrase `cli_credit_line` already established for this axis
    # (`tokens kept out of context`): it is the same claim in fewer columns, and the
    # English budget has no room for both the resident and the saved figure. `/turn`
    # carries the same job as the Chinese `0 常驻` anchor.
    parts = [f"{MARK} mcptoon: CLI route"]
    if kept:
        parts.append(f"saves {kept}/turn")
    if calls:
        parts.append(f"{calls:,}c")
    return " · ".join(parts) + f" [{cal}]"


def _direct_entry_count() -> int:
    """How many MCP entries still bypass the gateway, or 0 when unknown.

    Read-only and cache-only (`mode.detect` already walks this for the mode itself),
    so naming the count costs no server contact.
    """
    try:
        from . import mode as mode_mod

        return int(mode_mod.detect().get("direct_entries") or 0)
    except Exception:
        return 0


def cli_credit(f: dict | None = None) -> dict | None:
    """The CLI-mode credit figures, or None when this is not a CLI machine.

    Under CLI delivery the honest figure is what was *kept out of context*: the
    full catalog an agent would otherwise load, never resident because the call
    path fetches one tool at a time. Two derived numbers:

    * ``resident_avoided`` — ``tokens_full`` (the whole catalog), i.e. the cost
      the agent never pays at idle. Real, cache-only, no server touched.
    * ``per_call`` — the ``manifest`` name index, the one cheap thing a CLI call
      pulls to pick a tool. This is the *tiny* per-use cost that makes the saving
      real instead of rhetorical.

    Returns None when the mode is not ``cli`` (so callers keep the gateway
    headline untouched), or when there is no catalog to measure. The dict carries
    ``mode`` too, so a caller can phrase the line without a second detect().
    """
    d = facts() if f is None else f
    if current_mode() != "cli":
        return None
    full = d.get("tokens_full") or 0
    if not full:
        return None
    return {
        "mode": "cli",
        "resident_avoided": int(full),
        "per_call": int(d.get("name_index_tokens") or 0),
        "caliber": d.get("token_caliber") or "",
    }


def cli_credit_line(f: dict | None = None, lng: str | None = None) -> str | None:
    """One pasteable line naming the CLI-mode saving, or None off the CLI path.

    Shape (zh / en):

        CLI 模式：0 常驻 · 全量 640,606 token 没进上下文（按需只取 1 个 schema）
        CLI mode: 0 resident · 640,606 tokens kept out of context (fetch one schema on demand)

    Kept short and free of a percentage on purpose: the honest CLI claim is an
    absolute ("this much never loaded"), not a rate, because the rate depends on
    how many tools the agent *would* have loaded — which is exactly the serve
    story we are trying not to borrow. `per_call` is only shown when it was
    actually measured, so an uncached catalog never prints a made-up "0".
    """
    c = cli_credit(f)
    if c is None:
        return None
    lng = lng or lang()
    resident = _human_tokens(c["resident_avoided"])
    per = c.get("per_call") or 0
    if lng == "zh":
        tail = f"（按需只取 1 个 schema ≈ {per:,} token）" if per else "（按需只取 1 个 schema）"
        return f"CLI 模式：0 常驻 · 全量 {resident} token 没进上下文{tail}"
    tail = f" (fetch one schema on demand ≈ {per:,} tokens)" if per else " (fetch one schema on demand)"
    return f"CLI mode: 0 resident · {resident} tokens kept out of context{tail}"


def tool_schema_tokens(server: str, tool: str, encode=None, caliber: str | None = None) -> int:
    """The token cost of one tool's *full* schema, from the on-disk cache, or 0.

    The per-call receipt's key figure: "this call pulled one schema, ~N tokens"
    versus the whole catalog it did not pull. Cache-only — the receipt must never
    open a server just to count. An uncached server yields 0 (the receipt then
    omits the number rather than inventing one), matching the rest of the footer's
    "a figure the caller can date, never a guess" rule.
    """
    try:
        from . import cache as cache_mod

        cached, _age = cache_mod.get_cached_tools_any_age(server)
        if not cached:
            return 0
        for t in cached:
            if isinstance(t, dict) and t.get("name") == tool and "error" not in t:
                if encode is None or caliber is None:
                    from .bench import _tokenizer

                    encode, _cal, _exact = _tokenizer()
                import json

                return max(1, int(encode(json.dumps(t, ensure_ascii=False))))
    except Exception:
        return 0
    return 0


def line(f: dict | None = None, lng: str | None = None) -> str:
    """The headline figure line, in `lng` (default: the resolved language).

    The English line stays byte-identical to `footer-facts`' first line apart from
    the leading `MARK`. Both languages keep the ASCII `mcptoon:` prefix and the
    `[caliber]` suffix on purpose: every surface, every parser and every format
    test keys on those handles, and a handle that changes with the language is a
    parsing problem handed to someone who never asked for one.

    Three figures, one per unit of the same fact (2026-09-26 redesign): the count
    reduction a user experiences (``96→8``), the rate (``省 88%``), and the
    cumulative saving since install (``累计 ≈省 75M（4,000 次）``). The previous
    version put the raw token pair, *two* percentages and the running call count on
    this one line; measured at 166 display columns, it wrapped to three terminal
    rows on every single turn, which is what made the broadcast feel like noise.
    The omitted figures are not lost — `mcptoon report` carries the raw pair, the
    per-turn saving and the slim-schema percentage.

    The rate and the absolute saving both describe the *gateway* (what an agent
    actually loads) when the figures carry a gateway measurement. A dict without
    the gateway key — a catalog smaller than the gateway footprint, a legacy
    `--json` payload, a hand-built one — renders the same *shape*: the tool count,
    the rate, and the live call count. It deliberately does **not** keep the old
    byte-for-byte fallback string (tools, servers, the raw token pair, two
    percentages, the call count): measured at 143 display columns it wrapped on
    every turn, and it fired precisely on a fresh install, where a small catalog
    has no gateway baseline. `mcptoon report` carries the omitted pair and
    per-turn saving. The `[caliber]` handle stays on both shapes.

    The third figure is the *cumulative* estimate, not the per-turn one
    (2026-09-26, second pass). A per-turn figure is a constant: it says the same
    number every turn, and a badge that never moves stops being read — the exact
    complaint that had suppressed the line entirely. The cumulative figure is the
    one number on the line that grows as the user works, so "it is saving me
    something" is visible turn over turn instead of asserted. It carries `≈`
    because it is a lower bound (`_cumulative_estimate`), and the call count rides
    beside it in parentheses for the same reason: it moves, and movement is the
    point. The per-turn figure is not lost — `mcptoon report` carries it.
    """
    d = facts() if f is None else f
    lng = lng or lang()
    # On a direct machine (installed, not wired) nothing is saved: the agent loads
    # the full catalog natively. The gateway rate/cumulative below are a saving
    # that machine does not have, so the per-turn line must say so plainly rather
    # than broadcast "saves 88% · ≈1.9B". Same rule as the statusline fix; this is
    # the surface that fires every single turn, so it matters most.
    #
    # `serve-alongside` is the same "no saving yet" truth wearing a gateway badge:
    # the gateway is registered, but host configs still list the upstream entries
    # it manages, so those hosts load the full catalog directly and the gateway
    # saves nothing. Broadcasting the gateway rate here would credit mcptoon for a
    # saving it is not delivering — the exact "credit points the wrong way" defect.
    _cmode = current_mode()
    # A reader that can run a shell is on the cheapest route there is, whatever the
    # *machine's* mode says: it pulls one schema per call and keeps the catalog out
    # of its context entirely. So for that reader the honest headline is its own cost
    # (`_cli_route_line`), and the machine-global "not saving" verdict below — which
    # is about the OTHER hosts that still hold direct entries — must not be printed
    # at it. See `caller_can_shell` for the measurement behind this branch.
    if _cmode in ("cli", "serve-alongside") and caller_can_shell():
        return _cli_route_line(d, lng)
    if _cmode in ("direct", "serve-alongside"):
        _along = _cmode == "serve-alongside"
        _dfull = d.get("tokens_full") or 0
        _dtools = int(d.get("tools") or 0)
        _dcalls = int(d.get("calls_recorded") or 0) if "calls_recorded" in d else 0
        if lng == "zh":
            if _along:
                body = (f"{MARK} mcptoon: 工具 {_dtools:,}"
                        + (f"（全量 {_human_tokens(_dfull)} 仍直连）" if _dfull else "")
                        + " · 未接管·未省"
                        + (f" · {_dcalls:,} 次" if _dcalls else ""))
            else:
                body = (f"{MARK} mcptoon: 工具 {_dtools:,}"
                        + (f"（全量 {_human_tokens(_dfull)} 常驻）" if _dfull else "")
                        + " · 未接线·未省"
                        + (f" · {_dcalls:,} 次" if _dcalls else ""))
        else:
            if _along:
                body = (f"{MARK} mcptoon: tools {_dtools:,}"
                        + (f" (full {_human_tokens(_dfull)} still direct)" if _dfull else "")
                        + " · not taken over·no saving"
                        + (f" · {_dcalls:,} calls" if _dcalls else ""))
            else:
                body = (f"{MARK} mcptoon: tools {_dtools:,}"
                        + (f" (full {_human_tokens(_dfull)} resident)" if _dfull else "")
                        + " · not wired·no saving"
                        + (f" · {_dcalls:,} calls" if _dcalls else ""))
        return f"{body} [{d.get('token_caliber') or ''}]"
    gw_pct = d.get("gateway_pct") if "gateway_pct" in d else None
    gw_tok = d.get("gateway_tokens") if "gateway_tokens" in d else None
    if gw_pct is not None and gw_tok:
        exposed = _exposed_tool_count()
        # Compute the rate from the token pair when we have it, floored — not from
        # the pre-rounded `gateway_pct`. `gateway_savings` rounds to 1 decimal
        # (99.6), which a whole-number format then rounds *again* to 100; flooring
        # the raw ratio gives 99 and cannot overstate. Falls back to `gateway_pct`
        # only for a hand-built dict that has no `tokens_full`.
        _full = d.get("tokens_full")
        gw_saved = (_full - gw_tok) if isinstance(_full, int) and _full > gw_tok else None
        if gw_saved is not None:
            gw_pct_s = display_pct(gw_saved, _full)
        else:
            gw_pct_s = f"{math.floor(float(gw_pct)):.0f}" if gw_pct is not None else ""
        if not gw_pct_s:
            gw_pct_s = "0"
        # Three figures, one per unit of the same fact, and only three fit the
        # budget: the count reduction (`96→8`), the rate (`88%`), and the
        # cumulative saving since install (`≈75M（4,000 次）`). The 2026-09-26
        # redesign exists because the old line packed the raw token pair *and* two
        # percentages *and* the call count onto one line, which pushed it to 166
        # display columns and wrapped to three terminal rows on every turn. The
        # per-turn figure, the raw pair and the slim-schema percentage are not
        # lost: `mcptoon report` carries all three.
        est = _cumulative_estimate(d)
        calls = int(d.get("calls_recorded") or 0)
        if est:
            # The count is the exact figure, not a `k`-rounded one: the line is
            # meant to be *seen moving* turn over turn, and `4k` only ticks once
            # per thousand calls — long enough to look frozen again, which is the
            # very complaint this redesign answers. A rounded form would fit the
            # budget more comfortably, but at the cost of the movement that earns
            # the line its place. The English form abbreviates `calls` to `c` for
            # the same reason the Chinese uses `次`: the 80-column budget binds
            # first, and `c` is unambiguous beside a token figure.
            cum_zh = f" · ≈省{_human_tokens(est[1])}·{calls:,}次"
            cum_en = f" · ≈{_human_tokens(est[1])}·{calls:,}c"
        else:
            cum_zh = cum_en = ""
        # `tools` is formatted with a thousands separator: at 1,209 tools the bare
        # form saves one column, but the whole point of the 80-column budget is
        # that growth must not silently re-wrap the line (the width test in
        # `test_footer_broadcast.py` grew the catalog until it did).
        if lng == "zh":
            return (f"{MARK} mcptoon: 工具 {int(d['tools']):,}"
                    + (f"→{exposed}" if exposed else "")
                    + f"（省 {gw_pct_s}%）{cum_zh}"
                    f" [{d['token_caliber']}]")
        # English drops the word `tokens` before `/turn` — the `[tiktoken …]`
        # suffix on the same line already names the unit, and keeping it wrapped
        # the line at four-digit tool counts.
        return (f"{MARK} mcptoon: tools {int(d['tools']):,}"
                + (f"→{exposed}" if exposed else "")
                + f" (saves {gw_pct_s}%){cum_en}"
                f" [{d['token_caliber']}]")
    # No gateway measurement — a catalog smaller than the gateway footprint, or a
    # legacy `--json` dict without the gateway keys. The line keeps the same
    # *shape* as the gateway branch (count reduction, rate, live count) so the two
    # never disagree about what the headline means. The raw token pair and the
    # per-turn absolute saving are not lost: `mcptoon report` carries both. The
    # old fallback printed tools, servers, the raw pair, two percentages and the
    # call count on one line — measured at 143 display columns (zh), it wrapped on
    # every turn for exactly the machines that never had a gateway figure, which
    # is the defect the 2026-09-26 redesign set out to remove.
    live_en = f" · {d['calls_recorded']:,} calls" if "calls_recorded" in d else ""
    live_zh = f" · {d['calls_recorded']:,} 次" if "calls_recorded" in d else ""
    # Floor from the token pair when present (same rule as the gateway branch);
    # only a hand-built dict without the pair falls back to its stored percentage.
    _tf, _ts = d.get("tokens_full"), d.get("tokens_saved")
    if isinstance(_tf, int) and isinstance(_ts, int):
        sp = display_pct(_ts, _tf)
    else:
        sp = f"{math.floor(float(d['savings_pct'])):.0f}"
    if not sp:
        sp = "0"  # zero tools: keep "省 0%", not an empty "省 %"
    if lng == "zh":
        return (f"{MARK} mcptoon: 工具 {int(d['tools']):,}"
                f"（省 {sp}%）{live_zh}"
                f" [{d['token_caliber']}]")
    return (f"{MARK} mcptoon: tools {int(d['tools']):,}"
            f" (saves {sp}%){live_en}"
            f" [{d['token_caliber']}]")


def _exposed_tool_count() -> int:
    """How many tools the agent sees through the gateway, or 0 if unknown.

    The `compact` exposure registers mcptoon's own meta-tools and withholds the
    upstream schemas, so this is the number a user would count if they opened
    their agent's tool panel. Best-effort: a failure yields 0 and the line omits
    the reduction rather than printing a made-up one.
    """
    try:
        from . import native_tools

        return len(native_tools.native_tools())
    except Exception:
        return 0


def compression_facts() -> dict:
    """Whether result compression is on, and what it would save.

    The third axis of the savings story. Since 2026-09-26 it is **on by
    default** (`compress = smart`), so the honest report is the state: a fresh
    install compresses redundant results and says so, and `config set compress
    off` makes the line read "off" instead.

    `potential_pct` is a deliberately conservative floor, not a benchmark. It used to
    be documented as "the static benchmark (assets/benchmark_tiktoken.json, ~34%)", but
    that file's 34% is the TOON *schema* number, which says nothing about compression —
    the same confusion that put "~34%" on `--toon` in the README until 2026-10-02.
    Compression actually measures far higher (~88% for --slim). Quoting 34% understates
    it, which is the safe direction for a line the user reads as an offer rather than a
    banked saving. Do not "fix" it upward without a per-shape measurement, and do not
    cite benchmark_tiktoken.json as its source again.

    Cheap by construction — one `stat` and one `os.environ` read, no subprocess,
    no server: the footer may not open a connection.
    """
    import os

    enabled = False
    reason = ""
    try:
        from . import config as cfg

        if cfg.auto_smart_enabled():
            enabled = True
            reason = "smart"  # on by default — the "install and it works" path
        elif cfg.load_policies():
            enabled = True
            reason = "policy"
        elif os.environ.get("MCPTOON_AGENT_TYPE", "").lower() == "claude":
            enabled = True
            reason = "agent"
    except Exception:
        pass
    return {
        "enabled": enabled,
        "reason": reason,
        "potential_pct": 34,
        "caliber": "conservative floor; see compression_context() docstring",
    }


def compression_line(f: dict | None = None, lng: str | None = None) -> str:
    """The result-compression half, as its own line.

    Separate from `skills_line` because it answers a different question: the first
    two lines are about what the *catalog* costs, this one is about what tool
    *results* cost. It always prints — "off" is a fact the user needs, since the
    feature cannot save anything until they turn it on, and a line that vanishes
    when disabled would hide the one lever they have.

    When *this run* actually compressed a result, the line says so and points at
    `/mcptoon` (the skill that explains the feature and the way back) instead of
    reciting the retrieve path — the compressed result itself already carries the
    `mcptoon_retrieve` handle next to the data, so repeating it here would spend
    columns on what the reader just saw. That hint is conditional on purpose. The
    gateway cannot tell whether a compressed result was *good enough* —
    compression happens before the model reads it, so "did this hurt the answer?"
    is not a question the process can observe. What it can observe is that it
    compressed something, and a caution about damaged results is only worth
    reading on a turn that produced one; on every other turn it is noise, and
    noise is what stopped this line being read in the first place.
    """
    lng = lng or lang()
    c = compression_facts()
    pct = c["potential_pct"]
    if c["enabled"]:
        try:
            from . import compressor as _comp

            just_compressed = _comp.compressed_this_run()
        except Exception:
            just_compressed = False
        # The two states are alternatives, not a base plus an append: a turn that
        # compressed something already carries the `mcptoon_retrieve` handle *in
        # the result itself* (`compressor.notice`), so repeating "originals via
        # mcptoon_retrieve" here would spend columns on what the reader just read.
        # The compressed state instead names the way to a human-readable
        # explanation, which is what a user who suspects a damaged result needs.
        if just_compressed:
            if lng == "zh":
                return "   结果压缩（对话）— 已启用 · 本轮已压缩，失真问 /mcptoon 技能"
            return ("   result compression — on · compressed this turn; "
                    "ask /mcptoon skill")
        if c.get("reason") == "smart":
            if lng == "zh":
                return ("   结果压缩（对话）— 已启用（自动）· 原文可 "
                        "mcptoon_retrieve 取回")
            return ("   result compression — on (auto) · originals via "
                    "mcptoon_retrieve")
        if lng == "zh":
            return f"   结果压缩（对话）— 已启用 · 列表/搜索结果约省 {pct}%"
        return f"   result compression — on · ~{pct}% on list/search results"
    if lng == "zh":
        return (f"   结果压缩（对话）— 未启用 · `--toon` 可省约 {pct}%"
                f"（列表/搜索结果）")
    return (f"   result compression — off · `--toon` saves ~{pct}% "
            f"(list/search)")


def skills_line(f: dict | None = None, lng: str | None = None) -> str | None:
    """The skills line — skills saving, the details entry, the skill pointer.

    The second line of the broadcast. It answers the skills half of the same
    question the first line answers for tools: the count, the full catalog text,
    and what the agent gets instead (the pointer). It ends with two entry points:
    `mcptoon report`, the single command that carries every figure the two
    headline lines leave out (the raw token pair, the per-turn saving, the
    slim-schema percentage, the per-server breakdown), and `/mcptoon`, the skill
    that explains the whole feature and the way back (`config set compress off`,
    `config set exposure full`).

    Why a *second line* rather than more of the first: a chat transcript is
    scanned, not parsed, and one line already carries three figures. A separate
    line keeps the tools story readable and gives the skills story room for the
    numbers that make it credible.

    Returns None when the figures carry no skills count, so a machine with no
    skill catalog shows only the tools line (never a zero dressed as a saving).
    """
    d = facts() if f is None else f
    lng = lng or lang()
    count = int(d.get("skills") or 0)
    if not count:
        return None
    full = int(d.get("skills_tokens_full") or 0)
    pointer = int(d.get("skills_pointer_tokens") or 0)
    if lng == "zh":
        if not full:
            return f"   技能 {count} 个 · 详看 /mcptoon 技能"
        # Two decimals, *floored* not rounded — see `floor_pct`. 39/1,030,628 is
        # 99.9962%, which rounds to a "100%" that reads as a typo.
        pct = floor_pct(full - pointer, full)
        pct_s = f"{pct:.2f}" if pct is not None else ""
        return (f"   技能 {count} — {full:,}→{pointer}"
                f"（省 {pct_s}%）· mcptoon report · /mcptoon 技能")
    if not full:
        return f"   skills {count} · see /mcptoon skill"
    pct = floor_pct(full - pointer, full)
    pct_s = f"{pct:.2f}" if pct is not None else ""
    return (f"   skills {count} — {full:,}→{pointer}"
            f" ({pct_s}%) · mcptoon report · /mcptoon skill")


def note(f: dict | None = None, lng: str | None = None) -> str | None:
    """The staleness/coverage caveat in `lng`, or None when the figures are trustworthy.

    One rule for both languages: a dict carrying the caveat inputs is *rendered*,
    a dict that does not (an older `--json` payload, a caller's hand-built one)
    keeps the note it carries. The first version short-circuited English to the
    stored note, which made the same dict answer differently depending on the
    language asked for — the kind of asymmetry that reads as a bug later.
    """
    d = facts() if f is None else f
    lng = lng or lang()
    if "servers_uncached" in d:
        return _render_note(d, lng)
    return d.get("note")


def block(f: dict | None = None, lng: str | None = None) -> str:
    """`line` plus the skills and compression lines plus its `note:`.

    Order is tools → skills → compression → note. The note is a caveat on the
    figures above it, so it stays last; the skills and compression lines are
    further *figures*, so they sit with the first one rather than after the
    caveat. A machine with no skill catalog gets the tools line alone, which is
    why `skills_line` returns None instead of a zero; the compression line always
    prints, because "off" is itself the fact the reader needs.

    Deliberately identical to `mcptoon footer-facts` stdout, so "quote it
    verbatim" is true for every surface by construction rather than by luck.
    One `facts()` call and one language decision back every part: computing them
    separately could report a line and a note about different cache states, or a
    line and a note in different languages.
    """
    d = facts() if f is None else f
    lng = lng or lang()
    out = line(d, lng)
    for extra in (skills_line(d, lng), compression_line(d, lng)):
        if extra:
            out += f"\n{extra}"
    n = note(d, lng)
    if n:
        out += f"\nnote: {n}"
    return out


def changed(text: str) -> bool:
    """Whether `text` differs from the block shown last time.

    The per-turn complaint was that the footer recited the same number every
    turn. The figures in it change only when the machine does — a call is routed,
    the catalog is refreshed — so an identical block is, by construction, a turn
    that learned nothing new. Suppressing it is the honest reading of the old
    line's own caveat: a status readout that never changes is not a status
    readout.

    Compared on the **figure lines only** — everything above the `note:`, which
    is the tools line and the skills line. The `note:` beneath them carries a
    "catalog is N min old" age that ticks every minute; comparing the whole block
    would let the same figures reappear every minute wearing a fresh age, which is
    the repetition this removes. The note is a caveat on the figures, so it
    travels with them: shown when the figures change, silent otherwise.

    True when nothing has been shown yet, so the first line always appears.
    """
    from . import config as cfg

    last = cfg.last_footer_line()
    if last is None:
        return True
    return _figures_of(last) != _figures_of(text)


def _figures_of(text: str) -> str:
    """The figure lines of a block: everything before the `note:` caveat.

    The `note: ` label is ASCII in both languages on purpose (see the module
    docstring), which makes it a stable split point rather than a translated one.
    """
    lines = text.splitlines()
    figures = []
    for ln in lines:
        if ln.startswith("note: "):
            break
        figures.append(ln)
    return "\n".join(figures)


def remember(text: str) -> None:
    """Record the line just shown, so an identical one is suppressed next turn."""
    from . import config as cfg

    cfg.remember_footer_line(text)


# ─── The one action that turns "installed" into "saving" ───
#
# Measured problem this exists for: a machine can carry mcptoon for weeks and still
# save nothing, because the hosts that matter keep listing their MCP servers
# directly (`serve-alongside`) or the gateway was never wired at all (`direct`). The
# figures are honest about it — the tools line already says `未接管·未省` — but that
# is a *status*, and a status does not tell a reader what to type. Field evidence,
# 2026-11-11 on a 285-tool / 12-server machine: 16 days installed, 522 calls routed,
# `resident_avoided` still 0, and nothing on the per-turn channel said so.
#
# Shown only while nothing is being saved, at most once per interval and at most
# `MAX_SHOWS` times in total. That is the whole design: a nudge has to be seen to
# work, and has to stop to stay read. The cap is what keeps a user who has decided
# against the gateway from being nagged for the life of the install.

NEXT_ACTION_INTERVAL_SECONDS = 24 * 3600
NEXT_ACTION_MAX_SHOWS = 5


def next_action_hint(lng: str | None = None, now: float | None = None) -> str | None:
    """One pasteable command that would make this machine save, or None.

    Reads state only (`config.next_action_state`); nothing is recorded here, so this
    stays safe to call from any surface — including a renderer that may be asked for
    the same block twice in one turn. `note_next_action_shown` does the bookkeeping.
    """
    import time

    lng = lng or lang()
    mode = current_mode()
    if mode not in ("direct", "serve-alongside"):
        return None  # the machine is saving; there is no next action to name
    state = _next_action_state()
    shown = int(state.get("shown") or 0)
    if shown >= NEXT_ACTION_MAX_SHOWS:
        return None
    last = state.get("ts")
    try:
        last_ts = float(last) if last is not None else None
    except (TypeError, ValueError):
        last_ts = None
    clock = time.time() if now is None else now
    if last_ts is not None and clock - last_ts < NEXT_ACTION_INTERVAL_SECONDS:
        return None
    action = "mcptoon sync --takeover" if mode == "serve-alongside" else "mcptoon quickstart"
    if mode == "serve-alongside":
        # Name the subject. The unattributed version ("现在还没省") was read, correctly,
        # as a claim about the reader — which is how a DSH session already on the CLI
        # leg got told it was saving nothing. The entries belong to *other* hosts.
        n = _direct_entry_count()
        if lng == "zh":
            what = f"{n} 条" if n else "若干条"
            # Avoid the second sense of `全量` on this screen: the headline's `全量`
            # is the size of the whole catalog, and reusing the word here for "loads
            # everything each turn" made one word mean two things one line apart.
            return f"→ 另有宿主仍直连 {what},每次照旧直接加载:{action}"
        what_en = f"{n} direct entries" if n else "direct entries"
        return f"-> other hosts: {what_en} still load: {action}"
    if lng == "zh":
        return f"→ 现在还没省:跑 {action}(接上网关)"
    return f"-> not saving yet: run {action} (wire the gateway)"


def note_next_action_shown(now: float | None = None) -> None:
    """Record one showing of the nudge, so the interval and the cap advance.

    Called by the surfaces that actually printed it. Best-effort throughout: a
    read-only home must never turn a footer into a crash.
    """
    import time

    state = _next_action_state()
    try:
        shown = int(state.get("shown") or 0)
    except (TypeError, ValueError):
        shown = 0
    from . import config as cfg

    cfg.remember_next_action_state({
        "shown": shown + 1,
        "ts": float(time.time() if now is None else now),
    })


def _next_action_state() -> dict:
    """Thin wrapper so tests can patch one name instead of the config module."""
    from . import config as cfg

    return cfg.next_action_state()
