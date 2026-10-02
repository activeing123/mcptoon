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

"""Tests for `mcptoon report` — the one screen that adds every caliber up.

The load-bearing claim is consistency: `report` must never quote a tool count or
a schema-token figure that disagrees with `status`/the footer, and it must never
invent a number it cannot measure (there is deliberately no "cumulative turns
saved" figure). Both are pinned here.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import report  # noqa: E402


# ─── the tools half must equal what the footer/status say ───

def test_report_tool_numbers_match_the_footer_caliber():
    """One source of truth: whatever `facts()` says, `report` repeats verbatim."""
    from mcptoon import footer

    facts = footer.facts()
    data = report.build(query="zzz-no-match")
    assert data["tools"]["count"] == int(facts.get("tools") or 0)
    assert data["tools"]["full_tokens"] == int(facts.get("tokens_full") or 0)
    if facts.get("gateway_tokens"):
        assert data["tools"]["gateway_tokens"] == facts["gateway_tokens"]
        assert data["tools"]["gateway_pct"] == facts["gateway_pct"]


def test_report_gateway_is_the_headline_not_the_slim_row():
    """The 89% gateway figure is the honest headline; slim (24%) is secondary."""
    data = report.build(query="zzz-no-match")
    t = data["tools"]
    if t["gateway_pct"] is not None:
        assert t["gateway_pct"] > t["slim_pct"], (
            "gateway must beat slim — that is the whole reason it leads"
        )


def test_per_turn_is_the_two_halves_added():
    data = report.build(query="zzz-no-match")
    pt = data["per_turn"]
    # `full_tokens` is None when that half has nothing cached — a third state,
    # distinct from 0 ("measured, empty"). `build` adds it as 0, so the test must
    # too, or it fails on a machine with no tool catalog and passes on one with.
    native = (data["tools"]["full_tokens"] or 0) + (data["skills"]["full_tokens"] or 0)
    assert pt["native_tokens"] == native
    assert pt["saved_tokens"] == pt["native_tokens"] - pt["after_tokens"]


# ─── the skills half ───

def test_skills_half_reports_a_count_and_a_full_size():
    data = report.build(query="zzz-no-match")
    assert data["skills"]["count"] >= 0
    if data["skills"]["count"]:
        assert data["skills"]["full_tokens"] > 0
        assert data["skills"]["pointer_tokens"] < data["skills"]["full_tokens"]


# ─── honesty: no invented cumulative figures ───

def test_report_never_invents_a_cumulative_turn_figure():
    """`build` must not carry a key that would need a turn count it does not have."""
    data = report.build(query="zzz-no-match")

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    found = {k.lower() for k in keys(data)}
    for forbidden in ("turns_saved", "cumulative_turns", "turns"):
        assert forbidden not in found, f"report invented a '{forbidden}' figure"


def test_cumulative_calls_is_the_lifetime_count_not_the_window():
    """A window of 1000 must not cap the cumulative figure (the 2026-09-26 bug)."""
    from mcptoon import usage

    with patch.object(usage, "_load_usage", lambda: {
        "calls": [{"server": "s", "tool": "t", "ok": True, "tokens": 5}] * 1000,
        "total": 4321,
        "result_tokens": 99999,
    }):
        stats = usage.get_usage_stats()
    assert stats["total_calls"] == 4321
    assert stats["window_calls"] == 1000
    assert stats["lifetime_result_tokens"] == 99999


def test_lifetime_result_tokens_falls_back_to_the_window_for_a_legacy_file():
    from mcptoon import usage

    legacy = {"calls": [{"server": "s", "tool": "t", "ok": True, "tokens": 7}] * 3,
              "total": 3}
    with patch.object(usage, "_load_usage", lambda: legacy):
        stats = usage.get_usage_stats()
    assert stats["lifetime_result_tokens"] == 21


def test_lifetime_result_tokens_takes_the_max_while_the_counter_catches_up():
    """The day the counter is added it is smaller than the window beside it."""
    from mcptoon import usage

    fresh_counter = {
        "calls": [{"server": "s", "tool": "t", "ok": True, "tokens": 100}] * 1000,
        "total": 1000,
        "result_tokens": 500,  # only started counting this morning
    }
    with patch.object(usage, "_load_usage", lambda: fresh_counter):
        stats = usage.get_usage_stats()
    assert stats["lifetime_result_tokens"] == 100_000, (
        "a brand-new counter must not shrink a figure the window already proves"
    )


# ─── rendering ───

def test_render_is_plain_text_and_mentions_both_halves():
    data = report.build(query="zzz-no-match")
    text = report.render(data, lng="en")
    assert "MCP tools" in text and "Agent skills" in text
    assert "Cumulative" in text
    # No ANSI escapes — this text gets pasted into a chat.
    assert "\x1b[" not in text


def test_render_has_a_chinese_variant():
    data = report.build(query="zzz-no-match")
    zh = report.render(data, lng="zh")
    assert "MCP 工具" in zh and "累计" in zh


def test_report_json_is_machine_readable():
    buf = StringIO()
    with redirect_stdout(buf):
        report.run(["--query", "zzz-no-match", "--json"], fmt="json")
    data = json.loads(buf.getvalue())
    for key in ("caliber", "tools", "skills", "per_turn", "calls"):
        assert key in data


def test_report_is_footer_silent():
    """`report` prints the whole account; a footer line after it is pure repetition."""
    from mcptoon import cli
    assert "report" in cli._FOOTER_SILENT_COMMANDS


# ─── bench and status must not disagree (the third same-machine-two-numbers) ───

def test_bench_native_row_uses_the_same_caliber_as_status():
    """`bench` used to strip `annotations`, printing 16,641 against status's 21,074."""
    from mcptoon import bench, footer

    facts = footer.facts()
    if not facts.get("tokens_full"):
        return  # nothing cached on this machine; nothing to compare
    from mcptoon.bench import _tokenizer, _tool_rows
    encode, _cal, _exact = _tokenizer()
    rows, _n, _s = _tool_rows(encode)
    native = dict(rows).get("native: every full schema")
    assert native == int(facts["tokens_full"]), (
        f"bench says {native}, status says {facts['tokens_full']} — same machine, two numbers"
    )
    assert bench  # keep the import meaningful


def test_bench_ignores_cache_entries_for_servers_no_longer_configured():
    """A fossil cache entry must not inflate the catalog (557 vs 96, 2026-09-26)."""
    from mcptoon import bench, config

    fake_cache = {
        "still-here": {"tools": [{"name": "a"}, {"name": "b"}]},
        "removed-long-ago": {"tools": [{"name": f"x{i}"} for i in range(50)]},
    }
    with patch.object(config, "list_servers", lambda: ["still-here"]), \
         patch.object(bench.json, "loads", lambda s: fake_cache), \
         patch.object(bench.Path, "exists", lambda self: True), \
         patch.object(bench.Path, "read_text", lambda self, **kw: "{}"):
        tools = bench._load_cached_tools()
    assert list(tools) == ["still-here"], (
        "a server the user removed is not part of their catalog"
    )
    assert len(tools["still-here"]) == 2
