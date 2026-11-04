# Copyright 2025-2026 activeing123
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

"""Delivery-mode honesty across surfaces (direct/cli/serve) + mode-recommend entry.

Pins five things the 2026-10-20 pass fixed:
  1. direct mode must NOT claim the CLI "0 resident / saves 99%" story (it saves
     nothing); statusline and status say so, and statusline drops the fake ≈saved.
  2. `mode recommend` is discoverable: in `help` and in bash/zsh/fish completion.
  3. `doctor` reports the delivery mode and warns on direct with one action.
  4. `bench` shows the CLI "0 resident" caliber row on a CLI machine only.
  5. `footer-facts --json` and `status --json` both carry the unified
     cli_credit={mode,resident_avoided,per_call,caliber}.

Rule throughout: a CLI/direct figure is never a relabel of the gateway figure,
and off the CLI path the CLI credit is absent (None / zero).
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import pytest

from mcptoon import bench, cli, config as cfg, footer as footer_mod
from mcptoon import manifest as manifest_mod, mode as mode_mod, usage as usage_mod


_FACTS = {
    "servers": 7, "tools": 209, "tokens_full": 640606, "tokens_slim": 56504,
    "name_index_tokens": 906, "tokens_saved": 584102, "savings_pct": 91.2,
    "gateway_tokens": 2499, "gateway_pct": 99.6, "gateway_saved": 638107,
    "token_caliber": "tiktoken cl100k_base", "calls_recorded": 2928,
    "cache_age_seconds": 10.0, "servers_uncached": 0, "cache_ttl_seconds": 300,
    "skills": 472, "skills_tokens_full": 1528934, "skills_pointer_tokens": 39,
    "note": None,
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("MCPTOON_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MCPTOON_FOOTER_STATE_FILE", str(tmp_path / "footer-state.json"))
    monkeypatch.setenv("MCPTOON_CLI_AHA_FILE", str(tmp_path / "cli-aha"))
    monkeypatch.setenv("MCPTOON_ACTIVITY_FILE", str(tmp_path / "activity.jsonl"))
    monkeypatch.setenv("MCPTOON_LANG", "en")
    return tmp_path


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), \
            redirect_stdout(out), redirect_stderr(err):
        try:
            cli.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return out.getvalue(), err.getvalue(), code


# ── 1. direct mode: statusline + status ─────────────────────────────────────

def _statusline(mode_name, lng):
    with patch.object(mode_mod, "detect", return_value={"mode": mode_name, "calls": 2928}), \
            patch.object(mode_mod, "_figures", return_value=_FACTS), \
            patch.object(mode_mod, "_exposed", return_value=9):
        return mode_mod.statusline(lng=lng)


def test_statusline_direct_never_claims_gateway_saving():
    en = _statusline("direct", "en")
    zh = _statusline("direct", "zh")
    # No fake "99% less" / "省 99%" and no fake ≈saved on a machine that saves 0.
    assert "99%" not in en and "省 99%" not in zh
    assert "saved" not in en and "≈省" not in zh
    assert "not wired" in en and "未接线" in zh


def test_statusline_cli_still_shows_zero_resident():
    en = _statusline("cli", "en")
    assert "0 resident" in en and "640,606" in en.replace(",", ",")


def test_status_direct_says_nothing_saved(isolated):
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(cli, "_gateway_wired_in", return_value=False), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _err, _code = _run(["status"])
    assert "nothing is saved" in out
    assert "0 resident" not in out          # must not borrow the CLI line


def test_status_json_direct_resident_avoided_is_zero(isolated):
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(cli, "_gateway_wired_in", return_value=False), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _err, _code = _run(["status", "--json"])
    data = json.loads(out)
    assert data["resident_avoided"] == 0
    assert data["delivery_mode"] == "direct"
    assert data["cli_credit"] is None


# ── 2. mode recommend is discoverable ───────────────────────────────────────

def test_help_lists_mode_recommend(isolated):
    out, _err, _code = _run(["help"])
    assert "mode recommend" in out


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_offers_recommend(isolated, shell):
    out, _err, _code = _run(["completion", shell])
    assert "recommend" in out


# ── 3. doctor reports the delivery mode ─────────────────────────────────────

def _run_doctor(tmp_path, mode_name):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    buf = io.StringIO()
    code = 0
    with patch.object(cfg, "CONFIG_FILE", config_file), \
            patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
            patch.object(cfg, "load_config", return_value={"good": {"transport": "stdio"}}), \
            patch.object(cfg, "has_config_file", return_value=True), \
            patch.object(manifest_mod, "get_server_tools",
                         side_effect=lambda name, use_cache=True: [{"name": "a"}]), \
            patch.object(mode_mod, "statusline_status",
                         return_value={"wired": True, "path": "p", "file_exists": True}), \
            patch.object(footer_mod, "current_mode", return_value=mode_name), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}), \
            redirect_stdout(buf):
        try:
            cli._cmd_doctor([], json_mode=False)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return buf.getvalue(), code


def test_doctor_warns_on_direct_with_action(tmp_path):
    out, code = _run_doctor(tmp_path, "direct")
    assert "Mode: direct" in out
    assert "mcptoon sync --self" in out
    assert code == 0        # a not-wired install is a choice, not a fault


def test_doctor_reports_cli_zero_resident(tmp_path):
    out, code = _run_doctor(tmp_path, "cli")
    assert "Mode: cli" in out
    assert code == 0


def test_doctor_warns_on_alongside_with_takeover(tmp_path):
    with patch.object(mode_mod, "detect", return_value={
            "mode": "serve-alongside", "gateway_registered": True,
            "alongside": True, "direct_entries": 48, "servers": 7,
            "calls": 0, "routed": 0, "native": 0, "by_host": {}}):
        out, code = _run_doctor(tmp_path, "serve-alongside")
    assert "Mode: serve-alongside" in out
    assert "sync --takeover" in out
    assert "48 direct" in out
    assert code == 0        # wired-but-not-taken-over is a choice, not a fault


# ── 4. bench shows the CLI caliber row (CLI only) ───────────────────────────

_TOOL_ROWS = [
    ("native: every full schema", 640606),
    ("manifest (name index)", 906),
    ("manifest --slim", 56504),
]


def test_bench_shows_cli_row_on_cli():
    with patch.object(footer_mod, "current_mode", return_value="cli"):
        out = bench._render("tiktoken", True, _TOOL_ROWS, 209,
                            [], 0, 0, "", "q", [])
    assert "CLI: 0 resident" in out
    assert "640,606" in out


def test_bench_off_cli_has_no_cli_row():
    with patch.object(footer_mod, "current_mode", return_value="serve"):
        out = bench._render("tiktoken", True, _TOOL_ROWS, 209,
                            [], 0, 0, "", "q", [])
    assert "CLI: 0 resident" not in out


# ── 5. footer-facts --json + status --json carry unified cli_credit ─────────

def test_footer_facts_json_has_cli_credit_on_cli(isolated):
    with patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(footer_mod, "current_mode", return_value="cli"):
        out, _err, _code = _run(["footer-facts", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["cli_credit"] == {
        "mode": "cli", "resident_avoided": 640606,
        "per_call": 906, "caliber": "tiktoken cl100k_base"}


def test_footer_facts_json_cli_credit_none_off_cli(isolated):
    with patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(footer_mod, "current_mode", return_value="serve"):
        out, _err, _code = _run(["footer-facts", "--json"])
    data = json.loads(out)
    assert data["cli_credit"] is None
    assert data["delivery_mode"] == "serve"


def test_status_json_cli_credit_shape_on_cli(isolated):
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(cli, "_gateway_wired_in", return_value=False), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _err, _code = _run(["status", "--json"])
    data = json.loads(out)
    # resident_avoided is status's own catalog sum (here one fake tool = 23);
    # cli_credit carries the same shape from footer.facts. Both present, both CLI.
    assert data["resident_avoided"] > 0
    assert set(data["cli_credit"]) == {"mode", "resident_avoided", "per_call", "caliber"}
    assert data["cli_credit"]["resident_avoided"] == 640606


def test_status_json_alongside_carries_direct_entries(isolated):
    """A script reading `status --json` on a serve-alongside machine gets the mode
    AND the count of direct entries takeover would remove — not just a mode name."""
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="serve-alongside"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "detect", return_value={
                "mode": "serve-alongside", "gateway_registered": True,
                "alongside": True, "direct_entries": 48, "calls": 0,
                "routed": 0, "native": 0, "servers": 1, "by_host": {}}), \
            patch.object(cli, "_gateway_wired_in", return_value=True), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _err, _code = _run(["status", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "serve-alongside"
    assert data["direct_entries"] == 48


# ── Phase 2 ─────────────────────────────────────────────────────────────────

# 6. footer.line: direct must not broadcast the gateway rate / cumulative saving.

def _footer_line(mode_name, lng):
    with patch.object(mode_mod, "detect", return_value={"mode": mode_name, "calls": 2965}):
        return footer_mod.line(dict(_FACTS), lng=lng)


def test_footer_line_direct_says_no_saving():
    en = _footer_line("direct", "en")
    zh = _footer_line("direct", "zh")
    assert "no saving" in en and "未接线·未省" in zh
    assert "saves" not in en and "≈省" not in zh   # no gateway rate/cumulative
    assert "99%" not in en and "省 99%" not in zh


def test_footer_line_alongside_says_not_taken_over_not_99():
    """serve-alongside (gateway wired, entries not taken over) must not broadcast
    the gateway 99% either — it is not saving yet. Same honesty rule as direct."""
    en = _footer_line("serve-alongside", "en")
    zh = _footer_line("serve-alongside", "zh")
    assert "not taken over·no saving" in en
    assert "未接管·未省" in zh
    assert "saves" not in en and "≈省" not in zh
    assert "99%" not in en and "省 99%" not in zh
    assert "640,606" in en   # the full catalog still loads — name it


def test_footer_line_cli_keeps_gateway_headline():
    # Off the direct path the line is unchanged (serve/cli keep the gateway story).
    en = _footer_line("cli", "en")
    assert "saves" in en


# 7. mode explain names the host recommendation at the top.

def test_mode_explain_shows_host_recommendation():
    with patch.object(mode_mod, "detect", return_value={"mode": "direct", "calls": 0}), \
            patch.object(mode_mod, "_figures", return_value=_FACTS), \
            patch.object(mode_mod, "_exposed", return_value=9), \
            patch.object(mode_mod, "recommend", return_value={
                "current": "direct", "recommended": "serve",
                "reason": "GUI host", "one_action": "run `mcptoon sync --self`"}):
        out = mode_mod.explain(lng="en")
    assert "For this host: serve" in out
    assert "mcptoon sync --self" in out


# 8. inspect <server> (list form) reports the set's token total on CLI.

def test_inspect_server_list_reports_total_on_cli(isolated):
    tools = [{"name": "a", "inputSchema": {"type": "object"}},
             {"name": "b", "inputSchema": {"type": "object"}}]
    with patch.object(manifest_mod, "get_server_tools", return_value=tools), \
            patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        out, err, _code = _run(["inspect", "srv"])
    assert "schemas" in err and "CLI call" in err
    assert "schemas" not in out       # stdout stays pure data


def test_inspect_server_list_silent_off_cli(isolated):
    tools = [{"name": "a", "inputSchema": {"type": "object"}}]
    with patch.object(manifest_mod, "get_server_tools", return_value=tools), \
            patch.object(footer_mod, "current_mode", return_value="serve"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        _out, err, _code = _run(["inspect", "srv"])
    assert "schemas" not in err


# 9. manifest names its own name-index token count on CLI.

def test_manifest_reports_name_index_on_cli(isolated):
    manifest = {"srv": [{"name": "a"}, {"name": "b"}]}
    with patch.object(manifest_mod, "get_manifest", return_value=manifest), \
            patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        out, err, _code = _run(["manifest"])
    assert "name index" in err and "906" in err
    assert "name index" not in out


def test_manifest_no_index_note_off_cli(isolated):
    manifest = {"srv": [{"name": "a"}]}
    with patch.object(manifest_mod, "get_manifest", return_value=manifest), \
            patch.object(footer_mod, "current_mode", return_value="serve"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        _out, err, _code = _run(["manifest"])
    assert "name index" not in err


# 10. bench on direct says "you save 0", not a bare 99%.

def test_bench_direct_warns_no_saving():
    with patch.object(footer_mod, "current_mode", return_value="direct"):
        out = bench._render("tiktoken", True, _TOOL_ROWS, 209, [], 0, 0, "", "q", [])
    assert "direct:" in out and "right now you save 0" in out
    assert "sync --self" in out


def test_bench_alongside_warns_no_saving():
    with patch.object(footer_mod, "current_mode", return_value="serve-alongside"):
        out = bench._render("tiktoken", True, _TOOL_ROWS, 209, [], 0, 0, "", "q", [])
    assert "serve-alongside" in out and "right now you save 0" in out
    assert "sync --takeover" in out


# ── Phase 4 ─────────────────────────────────────────────────────────────────

# 11. savings: direct machine warns "you save 0" instead of a bare milestone list.

def test_savings_direct_warns_no_saving():
    from mcptoon import savings
    data = {"caliber": "tiktoken", "total_tokens": 1_900_000_000, "calls": 2966,
            "milestones_hit": [], "next": None, "cli_credit": None,
            "delivery_mode": "direct"}
    out = savings.render(data, lng="en")
    assert "save 0" in out and "sync --self" in out


def test_savings_alongside_warns_no_saving():
    from mcptoon import savings
    data = {"caliber": "tiktoken", "total_tokens": 1_900_000_000, "calls": 2966,
            "milestones_hit": [], "next": None, "cli_credit": None,
            "delivery_mode": "serve-alongside"}
    out = savings.render(data, lng="en")
    assert "save 0" in out and "sync --takeover" in out


def test_savings_cli_does_not_show_direct_warning():
    from mcptoon import savings
    data = {"caliber": "tiktoken", "total_tokens": 1_900_000_000, "calls": 2966,
            "milestones_hit": [], "next": None,
            "cli_credit": {"resident_avoided": 640606}, "delivery_mode": "cli"}
    out = savings.render(data, lng="en")
    assert "save 0" not in out
    assert "On CLI" in out


# 12. JSON parity: usage / bench / activity --summary all carry cli_credit.

def test_usage_json_has_cli_credit(isolated):
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        out, _e, _c = _run(["usage", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["cli_credit"]["resident_avoided"] == 640606


def test_activity_summary_json_has_cli_credit(isolated):
    ledger = isolated / "activity.jsonl"
    ledger.write_text(json.dumps({"ts": 1_700_000_000.0, "host": "CLI",
                                  "server": "s", "tool": "t", "ok": True,
                                  "tokens": 1}) + "\n", encoding="utf-8")
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS):
        out, _e, _c = _run(["activity", "--summary", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["cli_credit"]["resident_avoided"] == 640606


def test_bench_json_has_cli_credit(isolated):
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(bench, "_tool_rows",
                         return_value=(_TOOL_ROWS, 209, 7)), \
            patch.object(bench, "_skill_rows", return_value=([], 0, 0, "")):
        out, _e, _c = _run(["bench", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["cli_credit"]["resident_avoided"] == 640606


# 13. doctor --json promotes delivery_mode + recommended to the top level.

def test_doctor_json_has_top_level_mode_and_recommendation(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    buf = io.StringIO()
    with patch.object(cfg, "CONFIG_FILE", config_file), \
            patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
            patch.object(cfg, "load_config", return_value={"good": {"transport": "stdio"}}), \
            patch.object(cfg, "has_config_file", return_value=True), \
            patch.object(manifest_mod, "get_server_tools",
                         side_effect=lambda name, use_cache=True: [{"name": "a"}]), \
            patch.object(mode_mod, "statusline_status",
                         return_value={"wired": True, "path": "p", "file_exists": True}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "current": "direct", "recommended": "serve",
                "one_action": "run `mcptoon sync --self`"}), \
            patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}), \
            redirect_stdout(buf):
        try:
            cli._cmd_doctor([], json_mode=True)
        except SystemExit:
            pass
    data = json.loads(buf.getvalue())
    assert data["delivery_mode"] == "direct"
    assert data["recommended"] == "serve"
    assert "sync --self" in data["recommended_action"]


# 14. `mcptoon credit`: the single-screen entry, human + json.

def test_credit_human_names_mode_and_action(isolated):
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "cli", "one_action": "mcptoon statusline"}):
        out, _e, _c = _run(["credit"])
    assert "CLI" in out and "640,606" in out
    assert "mcptoon statusline" in out


def test_credit_direct_says_saves_zero(isolated):
    with patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}):
        out, _e, _c = _run(["credit"])
    assert "saves 0" in out and "sync --self" in out


def test_credit_alongside_says_saves_zero_and_takeover(isolated):
    with patch.object(footer_mod, "current_mode", return_value="serve-alongside"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "mcptoon sync --takeover"}):
        out, _e, _c = _run(["credit"])
    assert "saves 0" in out and "sync --takeover" in out
    assert "99%" not in out   # must not credit the gateway saving it is not living


def test_credit_json_contract(isolated):
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "cli", "one_action": "x", "reason": "cheapest"}):
        out, _e, _c = _run(["credit", "--json"])
    data = json.loads(out)
    for k in ("mode", "cli_credit", "resident_avoided", "recommended", "one_action"):
        assert k in data


def test_credit_is_in_help_and_completion(isolated):
    out, _e, _c = _run(["help"])
    assert "mcptoon credit" in out
    comp, _e2, _c2 = _run(["completion", "bash"])
    assert "credit" in comp


# 15. status shows a top-level recommendation line.

def test_status_shows_recommended_line(isolated):
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(cli, "_gateway_wired_in", return_value=False), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _e, _c = _run(["status"])
    assert "Recommended" in out and "serve" in out


# ── Phase 5 ─────────────────────────────────────────────────────────────────

# 16. mode --json + statusline --json carry cli_credit + recommended.

def test_mode_json_has_cli_credit_and_recommended(isolated):
    with patch.object(mode_mod, "detect",
                      return_value={"mode": "cli", "gateway_registered": False,
                                    "servers": 1, "calls": 0, "routed": 0, "native": 0,
                                    "by_host": {}}), \
            patch.object(mode_mod, "_figures", return_value=_FACTS), \
            patch.object(mode_mod, "recommend",
                         return_value={"recommended": "cli", "one_action": "x"}):
        out, _e, _c = _run(["mode", "--json"])
    data = json.loads(out)
    assert data["cli_credit"]["resident_avoided"] == 640606
    assert data["recommended"] == "cli"


def test_statusline_json_has_cli_credit(isolated):
    with patch.object(mode_mod, "detect",
                      return_value={"mode": "cli", "gateway_registered": False,
                                    "servers": 1, "calls": 0, "routed": 0, "native": 0,
                                    "by_host": {}}), \
            patch.object(mode_mod, "_figures", return_value=_FACTS), \
            patch.object(mode_mod, "_exposed", return_value=9):
        out, _e, _c = _run(["statusline", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["cli_credit"]["resident_avoided"] == 640606


def test_mode_json_cli_credit_none_off_cli(isolated):
    with patch.object(mode_mod, "detect",
                      return_value={"mode": "serve", "gateway_registered": True,
                                    "servers": 1, "calls": 0, "routed": 0, "native": 0,
                                    "by_host": {}}), \
            patch.object(mode_mod, "_figures", return_value=_FACTS), \
            patch.object(mode_mod, "recommend",
                         return_value={"recommended": "serve", "one_action": "x"}):
        out, _e, _c = _run(["mode", "--json"])
    data = json.loads(out)
    assert data["cli_credit"] is None


# 17. report: direct gets a top-of-report warning + --json exposes the fix.

def test_report_direct_warns_at_top():
    from mcptoon import report
    data = {"caliber": "tiktoken", "mode": {"current": "direct", "cheapest": "cli",
                                            "gateway_registered": False},
            "tools": {"count": 1, "servers": 1, "full_tokens": 100, "slim_tokens": 50,
                      "gateway_tokens": 0}, "tools_exposed": 0,
            "skills": {"count": 0, "full_tokens": 0, "pointer_tokens": 0,
                       "resolve_tokens": 0, "resolve_note": ""},
            "cli_credit": None, "cumulative": {"calls": 0, "gateway_equiv": 0},
            "per_turn": {"native_tokens": 100, "after_tokens": 50,
                         "saved_tokens": 50, "saved_pct": 50.0},
            "calls": {"total": 0, "window": 0, "success_rate": "",
                      "result_tokens_lifetime": 0, "first_call_ts": None}}
    out = report.render(data, lng="en")
    assert "you save 0 right now" in out
    # And the warning is above section ①.
    assert out.index("save 0") < out.index("① MCP tools")


def test_report_alongside_warns_at_top_and_names_takeover():
    from mcptoon import report
    data = {"caliber": "tiktoken",
            "mode": {"current": "serve-alongside", "cheapest": "cli",
                     "gateway_registered": True},
            "tools": {"count": 1, "servers": 1, "full_tokens": 100, "slim_tokens": 50,
                      "gateway_tokens": 0}, "tools_exposed": 0,
            "skills": {"count": 0, "full_tokens": 0, "pointer_tokens": 0,
                       "resolve_tokens": 0, "resolve_note": ""},
            "cli_credit": None, "cumulative": {"calls": 0, "gateway_equiv": 0},
            "per_turn": {"native_tokens": 100, "after_tokens": 50,
                         "saved_tokens": 50, "saved_pct": 50.0},
            "calls": {"total": 0, "window": 0, "success_rate": "",
                      "result_tokens_lifetime": 0, "first_call_ts": None}}
    out = report.render(data, lng="en")
    assert "you save 0 right now" in out
    assert "sync --takeover" in out
    assert out.index("save 0") < out.index("① MCP tools")


def test_report_json_mode_section_has_recommended():
    from mcptoon import report
    with patch.object(mode_mod, "detect",
                      return_value={"mode": "direct", "gateway_registered": False}), \
            patch.object(mode_mod, "recommend",
                         return_value={"recommended": "serve",
                                       "one_action": "run `mcptoon sync --self`"}):
        sec = report._mode_section()
    assert sec["recommended"] == "serve"
    assert "sync --self" in sec["one_action"]


# 18. SKILL.md documents `credit` and the "direct saves 0" fact.

def test_skill_documents_credit_and_direct_zero():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    md = (root / "src/mcptoon/skill/SKILL.md").read_text(encoding="utf-8")
    assert "mcptoon credit" in md
    assert "direct` mode saves nothing" in md or "saves nothing" in md


# ── Phase 6 ─────────────────────────────────────────────────────────────────

# 19. report --json top-level delivery_mode.

def test_report_json_top_level_delivery_mode():
    from mcptoon import report
    with patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(footer_mod, "note", return_value=""), \
            patch.object(report, "_native_tool_count", return_value=9), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "window_calls": 0, "success_rate": "",
                "lifetime_result_tokens": 0, "first_call_ts": None}):
        data = report.build()
    assert data["delivery_mode"] == "direct"


# 20. savings --json carries delivery_mode + recommended + one_action.

def test_savings_build_has_mode_and_recommendation():
    from mcptoon import savings
    with patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(footer_mod, "cli_credit", return_value=None), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "first_call_ts": None}), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}):
        data = savings.build()
    assert data["delivery_mode"] == "direct"
    assert data["recommended"] == "serve"
    assert "sync --self" in data["one_action"]


# 21. status --json carries recommended + one_action.

def test_status_json_has_recommended(isolated):
    tool = {"name": "t1", "description": "d", "inputSchema": {"type": "object"}}
    with patch.object(manifest_mod, "get_manifest", return_value={"srv": [tool]}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(cli, "_gateway_wired_in", return_value=False), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}), \
            patch.object(usage_mod, "get_usage_stats", return_value={
                "total_calls": 0, "success_rate": "", "by_server": {},
                "top_tools": {}, "routed_calls": 0, "native_calls": 0}):
        out, _e, _c = _run(["status", "--json"])
    data = json.loads(out)
    assert data["recommended"] == "serve"
    assert "sync --self" in data["one_action"]


# 22. quickstart ends by naming the mode / whether it saves.

def test_quickstart_tail_reports_mode(capsys):
    with patch.object(footer_mod, "current_mode", return_value="direct"):
        cli._post_onboard_mode_hint("auto")
    out = capsys.readouterr().out
    assert "Mode: direct" in out and "not saving yet" in out


def test_quickstart_tail_silent_for_machine(capsys):
    with patch.object(footer_mod, "current_mode", return_value="direct"):
        cli._post_onboard_mode_hint("json")
    assert capsys.readouterr().out == ""


# 23. install ends by naming the mode / one action (direct).

def test_post_install_mode_hint_direct(capsys):
    with patch.object(footer_mod, "current_mode", return_value="direct"):
        cli._post_install_mode_hint("human")
    err = capsys.readouterr().err
    assert "Mode: direct" in err and "sync --self" in err


def test_post_install_mode_hint_silent_for_machine(capsys):
    with patch.object(footer_mod, "current_mode", return_value="direct"):
        cli._post_install_mode_hint("json")
    assert capsys.readouterr().err == ""


# ── Phase 7 ─────────────────────────────────────────────────────────────────

# 24. credit --json carries delivery_mode (unified with the other surfaces).

def test_credit_json_has_delivery_mode(isolated):
    with patch.object(footer_mod, "current_mode", return_value="cli"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "cli", "one_action": "x", "reason": "cheapest"}):
        out, _e, _c = _run(["credit", "--json"])
    data = json.loads(out)
    assert data["delivery_mode"] == "cli"
    assert data["delivery_mode"] == data["mode"]


# 25. doctor --json carries one_action (+ back-compat recommended_action).

def test_doctor_json_has_one_action_alias(tmp_path):
    with patch.object(cfg, "CONFIG_FILE", tmp_path / "config.json"), \
            patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
            patch.object(cfg, "load_config", return_value={"good": {"transport": "stdio"}}), \
            patch.object(cfg, "has_config_file", return_value=True), \
            patch.object(manifest_mod, "get_server_tools",
                         side_effect=lambda name, use_cache=True: [{"name": "a"}]), \
            patch.object(mode_mod, "statusline_status",
                         return_value={"wired": False, "path": "p", "file_exists": False}), \
            patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}), \
            patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}):
        out, _e, _c = _run(["doctor", "--json"])
    data = json.loads(out)
    assert data["one_action"] == data["recommended_action"]
    assert "sync --self" in data["one_action"]


# 26. statusline direct tag names the fix (→sync), not a bare warning.

def test_statusline_direct_tag_names_sync():
    en = _statusline("direct", "en")
    zh = _statusline("direct", "zh")
    assert "direct→sync" in en
    assert "直连→sync" in zh


# 27. bench --json on direct carries recommended + one_action; off-direct null.

def test_bench_json_direct_has_recommendation():
    with patch.object(footer_mod, "current_mode", return_value="direct"), \
            patch.object(footer_mod, "facts", return_value=_FACTS), \
            patch.object(mode_mod, "recommend", return_value={
                "recommended": "serve", "one_action": "run `mcptoon sync --self`"}):
        from mcptoon import bench as bench_mod
        with patch.object(bench_mod, "_tool_rows", return_value=(_TOOL_ROWS, 209, 7)), \
                patch.object(bench_mod, "_skill_rows", return_value=([], 0, 0, "")), \
                patch.object(bench_mod, "_tokenizer", return_value=(None, "tiktoken", True)), \
                patch.object(bench_mod, "_roots_from", return_value=[]):
            out, _e, _c = _run(["bench", "--json"])
    data = json.loads(out)
    assert data["recommended"] == "serve"
    assert "sync --self" in data["one_action"]


# 28. doctor's direct next-step names `mcptoon credit`.

def test_doctor_direct_next_step_mentions_credit(tmp_path):
    out, code = _run_doctor(tmp_path, "direct")
    assert "mcptoon credit" in out


# 29. CHANGELOG records the delivery-mode pass + the 0.8.25 capabilities.

def test_changelog_records_delivery_mode_and_new_capabilities():
    """The CHANGELOG permanently records the delivery-mode pass and 0.8.25 features.

    Deliberately asserted over the whole file, NOT over a literal `## [Unreleased]`
    heading. `bump.py` renames that heading to the released version + date, so a
    test that pinned the literal string turned every CI matrix job (10 jobs, every
    OS/Python) red the moment 0.8.25 shipped — reproduced 2026-10-21, run
    39535840633. Released sections are immutable, so a whole-file check keeps
    meaning the same thing across every future bump.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    md = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "mcptoon credit" in md
    assert "exec <lang>" in md
    assert "mcptoon kb" in md
    assert "delivery" in md.lower()
