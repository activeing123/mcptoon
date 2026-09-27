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

"""`mcptoon report` — the whole savings account on one screen.

Every other surface answers one slice of "how much does this save?": the footer
gives the tool half, `skills stats` gives the skill half, `bench` gives the
calibers, `usage` gives the call count. This command is the one place they are
added up, because a user asking "so how much am I actually saving?" should not
have to run four commands and reconcile four numbers in their head — which is
exactly how the 2026-09-26 "same machine, four numbers" confusion happened.

The design rule is the same one `docs/calibers.md` states: **every number is
labelled with the question it answers, and nothing is invented.** In particular
there is no "cumulative context saved" figure, because mcptoon does not count how
many turns an agent has run — a number that would need that count would be a
guess dressed as a measurement. What *is* counted (calls routed, result tokens
through the gateway) is reported as counted.
"""

from __future__ import annotations

import json

__all__ = ["build", "render", "run"]


def _tool_section(facts: dict) -> dict:
    """The MCP-tools half, from `footer.facts()` — the shared caliber."""
    full = int(facts.get("tokens_full") or 0)
    return {
        "count": int(facts.get("tools") or 0),
        "servers": int(facts.get("servers") or 0),
        "full_tokens": full,
        "gateway_tokens": facts.get("gateway_tokens"),
        "gateway_pct": facts.get("gateway_pct"),
        "slim_tokens": int(facts.get("tokens_slim") or 0),
        "slim_pct": float(facts.get("savings_pct") or 0.0),
        "name_index_tokens": int(facts.get("name_index_tokens") or 0) or None,
    }


def _skill_section(roots, query: str, k: int) -> dict:
    """The skills half, from the same helpers `mcptoon bench` uses."""
    from .bench import _skill_rows, _tokenizer

    encode, _cal, _exact = _tokenizer()
    rows, n_skills, dupes, note = _skill_rows(encode, roots, query, k)
    by_label = {label: toks for label, toks in rows}
    full = by_label.get("native: every SKILL.md, full text")
    pointer = by_label.get("skills manifest (pointer)")
    resolve = next((t for lab, t in rows if lab.startswith("skills resolve")), None)
    return {
        "count": n_skills,
        "full_tokens": full,
        "pointer_tokens": pointer,
        "resolve_tokens": resolve,
        "duplicates_skipped": dupes,
        "note": note,
    }


def _native_tool_count() -> int:
    """How many tools mcptoon itself exposes under the default compact exposure."""
    try:
        from .native_tools import native_tools
        return len(native_tools())
    except Exception:
        return 0


def build(query: str = "make a PDF", k: int = 5) -> dict:
    """Assemble every savings figure, each with the caliber it is measured on."""
    from . import footer as footer_mod
    from . import usage as usage_mod
    from .bench import _roots_from, _tokenizer

    _encode, caliber, exact = _tokenizer()
    facts = footer_mod.facts()

    tools = _tool_section(facts)
    skills = _skill_section(_roots_from([]), query, k)

    usage = usage_mod.get_usage_stats()

    # Per-turn context: the two halves added, on the same tiktoken caliber.
    native_total = (tools["full_tokens"] or 0) + (skills["full_tokens"] or 0)
    slim_total = ((tools["gateway_tokens"] or tools["slim_tokens"] or 0)
                  + (skills["pointer_tokens"] or 0))
    per_turn_pct = (round((native_total - slim_total) / native_total * 100, 1)
                    if native_total and slim_total and native_total > slim_total
                    else None)

    return {
        "caliber": caliber,
        "exact": exact,
        "note": footer_mod.note(facts) if hasattr(footer_mod, "note") else "",
        "tools": tools,
        "tools_exposed": _native_tool_count(),
        "skills": skills,
        "per_turn": {
            "native_tokens": native_total,
            "after_tokens": slim_total,
            "saved_tokens": max(0, native_total - slim_total),
            "saved_pct": per_turn_pct,
        },
        "calls": {
            "total": usage["total_calls"],
            "window": usage["window_calls"],
            "success_rate": usage["success_rate"],
            "result_tokens_lifetime": usage["lifetime_result_tokens"],
        },
    }


def _fmt(n) -> str:
    return f"{int(n):,}" if isinstance(n, (int, float)) and n is not None else "—"


def _row(label: str, tokens, suffix: str = "", width: int = 22) -> str:
    """One `label   tokens   suffix` line — never an f-string with nested quotes."""
    return f"     {label:<{width}}{_fmt(tokens):>12}{suffix}"


def render(data: dict, lng: str = "en") -> str:
    """The report as pasteable text. One language, no escape codes."""
    from . import footer as footer_mod

    zh = lng == "zh"
    t, s, pt, c = data["tools"], data["skills"], data["per_turn"], data["calls"]
    L = []
    a = L.append

    def L_(en: str, zh_text: str) -> str:
        return zh_text if zh else en

    a(L_("mcptoon savings report", "mcptoon 省 token 全账")
      + f"  ·  {data['caliber']}")
    a("")

    # ① tools
    gw = t["gateway_tokens"]
    a(L_("① MCP tools", "① MCP 工具")
      + f"  —  {_fmt(t['count'])} " + L_("tools", "个工具")
      + f" / {_fmt(t['servers'])} " + L_("servers", "个服务器"))
    if data["tools_exposed"]:
        a(_row(L_("tools the agent sees", "agent 看到的工具数"), data["tools_exposed"])
          + "   " + L_(f"(down from {_fmt(t['count'])})", f"（原 {_fmt(t['count'])} 个）"))
    a(_row(L_("every full schema", "完整 schema"), t["full_tokens"]))
    if gw:
        a(_row(L_("gateway (what loads)", "网关实际加载"), gw, f"   ↓ {t['gateway_pct']:.0f}%")
          + "   " + L_("(default compact exposure)", "（默认 compact 暴露）"))
    a(_row(L_("manifest --slim", "瘦身 schema"), t["slim_tokens"], f"   ↓ {t['slim_pct']:.0f}%"))
    a("")

    # ② skills
    a(L_("② Agent skills", "② 技能")
      + f"  —  {_fmt(s['count'])} " + L_("skills", "个技能"))
    a(_row(L_("every SKILL.md", "全部 SKILL.md"), s["full_tokens"]))
    if s["pointer_tokens"]:
        # Floored via the shared helper: 39/1,030,628 rounds to a "100%" that reads
        # as a typo, and the footer must not print a different number for the same
        # pair — see `footer.floor_pct`.
        p = footer_mod.floor_pct((s["full_tokens"] or 0) - s["pointer_tokens"],
                                 s["full_tokens"] or 0)
        a(_row(L_("resident pointer", "常驻指针"), s["pointer_tokens"],
               f"   ↓ {p:.2f}%" if p is not None else ""))
    if s["resolve_tokens"]:
        # Also floored, for the same reason the pointer row is: `99.9%` was a
        # hardcoded string that could drift from the numbers beside it.
        r = footer_mod.floor_pct((s["full_tokens"] or 0) - s["resolve_tokens"],
                                 s["full_tokens"] or 0, places=1)
        a(_row(L_("one resolve (k=5)", "一次检索 (k=5)"), s["resolve_tokens"],
               f"   ↓ {r:.1f}%" if r is not None else ""))
    a("")

    # ③ per turn
    a(L_("③ Per-turn context (①+②)", "③ 每轮上下文合计（①+②）"))
    a(_row(L_("native", "完整"), pt["native_tokens"]))
    a(_row(L_("after mcptoon", "装 mcptoon 后"), pt["after_tokens"],
           f"   ↓ {pt['saved_pct']:.1f}%" if pt["saved_pct"] is not None else ""))
    a("")

    # ④ call-result compression (on by default since 2026-09-26)
    a(L_("④ Call-result compression (on by default)", "④ 对话结果压缩（默认开启）"))
    a("     " + L_("structure-aware: shrinks redundant results, keeps every key",
                   "结构感知：压缩冗余结果，保留全部键名"))
    a("     " + L_("originals recoverable via mcptoon_retrieve; turn off: config set compress off",
                   "原文可经 mcptoon_retrieve 取回；关闭：config set compress off"))
    a("")

    # ⑤ cumulative
    a(L_("⑤ Cumulative (counted, since install)", "⑤ 累计（自安装，真实计数）"))
    a(_row(L_("calls routed", "累计转发调用"), c["total"],
           f"   ({c['success_rate']} ok)" if c["total"] else ""))
    a(_row(L_("result tokens through", "累计处理结果 token"), c["result_tokens_lifetime"]))
    a("     " + L_("note: turns are not counted, so no cumulative-turn figure is invented",
                   "注：不统计『轮数』，故不编造累计轮次节省"))
    a("")

    if data.get("note"):
        a("note: " + data["note"])
    return "\n".join(L)


def run(rest: list[str], fmt: str = "auto") -> None:
    """CLI entry: `mcptoon report [--query Q] [-k N] [--json]`."""
    query = "make a PDF"
    k = 5
    for i, a in enumerate(rest):
        if a == "--query" and i + 1 < len(rest):
            query = rest[i + 1]
        elif a.startswith("--query="):
            query = a.split("=", 1)[1]
        elif a == "-k" and i + 1 < len(rest):
            try:
                k = int(rest[i + 1])
            except ValueError:
                pass
        elif a.startswith("-k="):
            try:
                k = int(a.split("=", 1)[1])
            except ValueError:
                pass

    data = build(query=query, k=k)
    if fmt == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    from . import config as cfg
    print(render(data, lng=cfg.resolve_lang()))
