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

__all__ = ["facts", "line", "skills_line", "compression_line", "note", "block",
           "enabled", "lang", "changed", "remember", "MARK"]

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
    from . import schema_simplifier
    from . import usage as usage_mod
    from .bench import _tokenizer

    servers = cfg.list_servers()
    encode, caliber, _exact = _tokenizer()

    total_tools = 0
    full_tokens = 0
    slim_tokens = 0
    oldest_age: float | None = None
    uncached = 0
    for name in servers:
        tools, age = cache_mod.get_cached_tools_any_age(name)
        if tools is None:
            uncached += 1
            continue
        if age is not None and (oldest_age is None or age > oldest_age):
            oldest_age = age
        for t in tools:
            if not isinstance(t, dict) or "error" in t:
                continue
            total_tools += 1
            full_tokens += max(1, int(encode(json.dumps(t, ensure_ascii=False))))
            slim_tokens += max(1, int(encode(json.dumps(
                schema_simplifier.simplify_tool_def(t), ensure_ascii=False))))

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
        return f"{n / 1_000_000:.0f}M"
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
    gw_pct = d.get("gateway_pct") if "gateway_pct" in d else None
    gw_tok = d.get("gateway_tokens") if "gateway_tokens" in d else None
    if gw_pct is not None and gw_tok:
        exposed = _exposed_tool_count()
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
                    + f"（省 {gw_pct:.0f}%）{cum_zh}"
                    f" [{d['token_caliber']}]")
        # English drops the word `tokens` before `/turn` — the `[tiktoken …]`
        # suffix on the same line already names the unit, and keeping it wrapped
        # the line at four-digit tool counts.
        return (f"{MARK} mcptoon: tools {int(d['tools']):,}"
                + (f"→{exposed}" if exposed else "")
                + f" (saves {gw_pct:.0f}%){cum_en}"
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
    if lng == "zh":
        return (f"{MARK} mcptoon: 工具 {int(d['tools']):,}"
                f"（省 {d['savings_pct']:.0f}%）{live_zh}"
                f" [{d['token_caliber']}]")
    return (f"{MARK} mcptoon: tools {int(d['tools']):,}"
            f" (saves {d['savings_pct']:.0f}%){live_en}"
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
