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
"""

from __future__ import annotations

import json

__all__ = ["facts", "line", "note", "block", "enabled"]


def enabled() -> bool:
    """Whether the footer is on. Same switch as every other surface."""
    from . import config as cfg

    return cfg.footer_enabled()


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
    # Both caveats can be true at once — a server that never resolves plus an old
    # cache — and they must both surface. These figures get quoted verbatim into a
    # chat turn, so a stale number reported as fresh is worse than a noisy note.
    # An earlier version used elif branches, which let an uncached server hide the
    # staleness: on the author's machine the cache was 2.1h old (TTL 5 min) and the
    # note still read as though only the count were partial.
    if not servers:
        note_text = "no servers configured"
    else:
        parts = []
        if uncached == len(servers):
            parts.append("catalog not cached yet - run `mcptoon manifest` once to populate it")
        elif uncached:
            parts.append(f"{uncached} of {len(servers)} servers not cached yet")
        if oldest_age is not None and oldest_age > ttl:
            parts.append(f"catalog is {oldest_age / 60:.0f} min old (cache TTL {ttl // 60} min)")
        if parts:
            parts.append("figures cover the cached servers and may lag")
            note_text = "; ".join(parts)
        else:
            note_text = None

    return {
        "servers": len(servers),
        "tools": total_tools,
        "tokens_full": full_tokens,
        "tokens_slim": slim_tokens,
        "tokens_saved": saved,
        "savings_pct": pct,
        "token_caliber": caliber,
        "calls_recorded": calls,
        "cache_age_seconds": round(oldest_age, 1) if oldest_age is not None else None,
        "note": note_text,
    }


def line(f: dict | None = None) -> str:
    """The one pasteable line. Byte-identical to `footer-facts`' first line."""
    d = facts() if f is None else f
    return (f"mcptoon: {d['tools']} tools in {d['servers']} servers — "
            f"{d['tokens_full']:,} → {d['tokens_slim']:,} tokens "
            f"(saved {d['tokens_saved']:,}, {d['savings_pct']:.0f}%) "
            f"[{d['token_caliber']}]")


def note(f: dict | None = None) -> str | None:
    """The staleness/coverage caveat, or None when the figures are trustworthy."""
    d = facts() if f is None else f
    return d.get("note")


def block(f: dict | None = None) -> str:
    """`line` plus its `note:` when there is one — the text a surface stamps.

    Deliberately identical to `mcptoon footer-facts` stdout, so "quote it
    verbatim" is true for every surface by construction rather than by luck.
    One `facts()` call backs both halves: computing them separately could report
    a line and a note about different cache states.
    """
    d = facts() if f is None else f
    out = line(d)
    n = note(d)
    if n:
        out += f"\nnote: {n}"
    return out
