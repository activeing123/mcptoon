"""The one savings line, shared by every surface that can show it.

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

Cost, measured rather than guessed: the block is ~32 tokens on the
tiktoken cl100k_base caliber, and a full catalog compression saves ~5,200. That
is why the MCP side stamps **once per session** instead of on every result —
stamping every call would break even at ~162 calls, and a feature that can eat
its own savings is not a feature. The per-turn *narrative* line stays the model's
job (see `serve._INSTRUCTIONS` and the AGENTS.md block); this module only
guarantees that the number is on screen.

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
problem for consumers who never asked for one.
"""

from __future__ import annotations

import json

__all__ = ["facts", "line", "note", "block", "enabled", "lang", "MARK"]

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

    English is byte-for-byte the wording the JSON payload has always carried;
    tests and downstream consumers already key on it.
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
                     else "catalog not cached yet - run `mcptoon manifest` once to populate it")
    elif uncached:
        parts.append(f"{servers} 个服务器里有 {uncached} 个还没缓存" if zh
                     else f"{uncached} of {servers} servers not cached yet")
    if age is not None and age > ttl:
        parts.append(f"目录已 {age / 60:.0f} 分钟没更新（缓存 TTL {ttl // 60} 分钟）" if zh
                     else f"catalog is {age / 60:.0f} min old (cache TTL {ttl // 60} min)")
    if not parts:
        return None
    parts.append("数字只覆盖已缓存的服务器，可能滞后" if zh
                 else "figures cover the cached servers and may lag")
    return ("；" if zh else "; ").join(parts)


def facts() -> dict:
    """The savings numbers, cache-only — never spawns a server.

    Mirrors `cli._cmd_footer_facts`: reads the schema cache at whatever age it
    has and reports the age in `note` rather than refreshing. The obvious
    implementation — call `status` — costs ~23s cold here because it spawns
    every configured server, which is unusable inside a tool call. A figure the
    caller can date is honest; a 23-second pause is not.

    Returns a dict with the keys `cli._cmd_footer_facts --json` documents.
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
    figures = {
        "servers": len(servers),
        "tools": total_tools,
        "tokens_full": full_tokens,
        "tokens_slim": slim_tokens,
        "tokens_saved": saved,
        "savings_pct": pct,
        "token_caliber": caliber,
        "calls_recorded": calls,
        "cache_age_seconds": round(oldest_age, 1) if oldest_age is not None else None,
        # The raw caveat inputs travel with the figures so `note(..., lng="zh")`
        # can translate a sentence it already has the numbers for, without
        # re-reading a cache — or, worse, contacting a server to do it.
        "servers_uncached": uncached,
        "cache_ttl_seconds": ttl,
    }
    # English is the payload's language, whatever the user's is: `--json` is a
    # machine channel and the note in it is data, not a message to a person.
    figures["note"] = _render_note(figures, "en")
    return figures


def line(f: dict | None = None, lng: str | None = None) -> str:
    """The one pasteable line, in `lng` (default: the resolved language).

    The English line stays byte-identical to `footer-facts`' first line apart from
    the leading `MARK`. The Chinese line keeps the ASCII `mcptoon:` prefix, the
    word `tokens` and the `[caliber]` suffix on purpose: every surface, every
    parser and every format test keys on those handles, and a handle that changes
    with the language is a parsing problem handed to someone who never asked for
    one.
    """
    d = facts() if f is None else f
    lng = lng or lang()
    if lng == "zh":
        return (f"{MARK} mcptoon: {d['tools']} 个工具，{d['servers']} 个服务器 — "
                f"{d['tokens_full']:,} → {d['tokens_slim']:,} tokens"
                f"（省 {d['tokens_saved']:,}，{d['savings_pct']:.0f}%）"
                f"[{d['token_caliber']}]")
    return (f"{MARK} mcptoon: {d['tools']} tools in {d['servers']} servers — "
            f"{d['tokens_full']:,} → {d['tokens_slim']:,} tokens "
            f"(saved {d['tokens_saved']:,}, {d['savings_pct']:.0f}%) "
            f"[{d['token_caliber']}]")


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
    """`line` plus its `note:` when there is one — the text a surface stamps.

    Deliberately identical to `mcptoon footer-facts` stdout, so "quote it
    verbatim" is true for every surface by construction rather than by luck.
    One `facts()` call and one language decision back both halves: computing them
    separately could report a line and a note about different cache states, or a
    line and a note in different languages.
    """
    d = facts() if f is None else f
    lng = lng or lang()
    out = line(d, lng)
    n = note(d, lng)
    if n:
        out += f"\nnote: {n}"
    return out
