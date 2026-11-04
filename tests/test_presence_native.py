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

"""Presence, round 2: the gateway's OWN tools are now visible too.

Round 1 made *proxied upstream* calls show up in the activity ledger. But the
tools an agent reaches for first are mcptoon's own — and `mcptoon_resolve_skills`
is the exact "mcptoon is distributing your capabilities" moment the presence
channel exists to surface. Those calls are answered in-bridge and never passed
through the router, so before this they were invisible: a session that only ever
distributed skills left the ledger empty. These tests pin:

1. `serve._track_native` records a native call under the reserved server name
   ``mcptoon`` (so `activity`/`status` can tell gateway tools from upstream ones).
2. `serve._maybe_skill_banner` attaches a one-per-session "distributed N skills"
   line to the first resolve that actually surfaced skills — and only then.
3. `quickstart` names which agents it registered mcptoon into.
4. `doctor`, when healthy and the gateway is wired, teaches where to watch it work.
"""

from __future__ import annotations

import io
import threading
from contextlib import redirect_stdout

import pytest

from mcptoon import config, usage
from mcptoon.serve import MCPServerBridge


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "activity.jsonl"
    monkeypatch.setenv("MCPTOON_ACTIVITY_FILE", str(path))
    monkeypatch.setattr(usage, "_HOST", None, raising=False)
    monkeypatch.setattr(usage, "_SESSION_CALLS", 0, raising=False)
    return path


def _bare_bridge():
    """A bridge with just the state `_track_native` / `_maybe_skill_banner` touch."""
    b = MCPServerBridge.__new__(MCPServerBridge)
    b._tool_index = {}
    b._tool_index_lock = threading.RLock()
    b._lock = threading.RLock()
    b._initialized = True
    b._servers = {}
    b._output_format = "auto"
    b._footer_stamped = True  # keep footer out of these assertions
    return b


def _resolve_payload(shortlist):
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {"query": "t", "k": 5, "shortlist": shortlist},
        "isError": False,
        "resultType": "complete",
    }


# ─── 1. native calls are tracked ─────────────────────────────────────────────

def test_track_native_records_under_the_mcptoon_server(ledger):
    b = _bare_bridge()
    usage.set_host("Cursor")
    b._track_native("mcptoon_resolve_skills",
                    {"content": [], "structuredContent": {}, "isError": False})
    entries = usage.read_activity(10)
    assert len(entries) == 1
    assert entries[0]["server"] == "mcptoon"
    assert entries[0]["tool"] == "mcptoon_resolve_skills"
    assert entries[0]["host"] == "Cursor"
    assert entries[0]["ok"] is True


def test_track_native_records_an_error_as_an_error(ledger):
    b = _bare_bridge()
    b._track_native("mcptoon_manifest", {"content": [], "isError": True})
    entry = usage.read_activity(10)[0]
    assert entry["ok"] is False


def test_track_native_returns_the_payload_unchanged(ledger):
    b = _bare_bridge()
    payload = {"content": [{"type": "text", "text": "hi"}], "isError": False}
    assert b._track_native("mcptoon_manifest", payload) is payload


def test_a_real_resolve_call_is_now_in_the_ledger(ledger):
    """The end-to-end path: _handle_call_tool on a native tool writes a line."""
    b = _bare_bridge()
    usage.set_host("Claude Desktop")
    b._handle_call_tool({"name": "mcptoon_resolve_skills",
                         "arguments": {"task": "写一个视频脚本", "k": 3}})
    entries = usage.read_activity(10)
    assert entries and entries[0]["tool"] == "mcptoon_resolve_skills"


# ─── 2. the skill-delivery banner ────────────────────────────────────────────

def test_skill_banner_attaches_on_first_resolve_with_skills(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    b = _bare_bridge()
    payload = b._maybe_skill_banner(_resolve_payload([{"slug": "a"}, {"slug": "b"}]))
    texts = [c["text"] for c in payload["content"]]
    assert any("distributed 2 skills" in t for t in texts)
    assert b._skill_banner_done is True


def test_skill_banner_is_once_per_session(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    b = _bare_bridge()
    b._maybe_skill_banner(_resolve_payload([{"slug": "a"}]))
    second = b._maybe_skill_banner(_resolve_payload([{"slug": "a"}]))
    assert len(second["content"]) == 1, "the banner must not repeat"


def test_skill_banner_singular_wording(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    b = _bare_bridge()
    payload = b._maybe_skill_banner(_resolve_payload([{"slug": "only"}]))
    texts = " ".join(c["text"] for c in payload["content"])
    assert "distributed 1 skill " in texts  # singular, not "1 skills"


def test_skill_banner_skips_an_empty_shortlist(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    b = _bare_bridge()
    payload = b._maybe_skill_banner(_resolve_payload([]))
    assert len(payload["content"]) == 1, "no skills delivered → no banner"


def test_skill_banner_respects_presence_off(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: False)
    b = _bare_bridge()
    payload = b._maybe_skill_banner(_resolve_payload([{"slug": "a"}]))
    assert len(payload["content"]) == 1


def test_skill_banner_never_raises_on_a_malformed_payload(ledger, monkeypatch):
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    b = _bare_bridge()
    # No structuredContent, no content list — must return quietly, not crash.
    assert b._maybe_skill_banner({"isError": False}) == {"isError": False}


# ─── 3. quickstart names the hosts ───────────────────────────────────────────

def test_quickstart_names_the_agents_it_registered(monkeypatch, capsys):
    """The install summary must say *which* apps now carry mcptoon."""
    from mcptoon import cli

    # Drive only the sync-summary branch by faking sync_to_all's result.
    class _R:
        def __init__(self):
            self.servers = {"github": {}}
            self.sources = {}
            self.reasons = {}
            self.count = 1

        def summary(self):
            return "  summary line"

    fake = _R()

    import mcptoon.discover as disc
    monkeypatch.setattr(disc, "auto_discover", lambda: fake)
    monkeypatch.setattr(cli.cfg, "has_config_file", lambda: True)
    monkeypatch.setattr(cli.cfg, "merge_servers", lambda *a, **k: (0, 0, 0))

    import mcptoon.sync as sync_mod
    monkeypatch.setattr(sync_mod, "sync_to_all", lambda **k: [
        {"agent": "cursor", "agent_name": "Cursor", "written": True},
        {"agent": "claude", "agent_name": "Claude Desktop", "written": True},
    ])
    monkeypatch.setattr(sync_mod, "format_sync_report", lambda r, dry_run: "")

    from mcptoon import skills as skills_mod
    monkeypatch.setattr(skills_mod, "ensure_index", lambda: False)
    monkeypatch.setattr(cli, "_maybe_offer_takeover", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_quickstart_celebration", lambda *a, **k: None)
    import mcptoon.manifest as manifest_mod
    monkeypatch.setattr(manifest_mod, "get_manifest", lambda use_cache=False: {})

    cli._cmd_quickstart([], "auto")
    out = capsys.readouterr().out
    assert "Cursor" in out and "Claude Desktop" in out
    assert "mcptoon activity" in out


# ─── 4. doctor teaches where to watch it work ────────────────────────────────

def _run_doctor_healthy(monkeypatch):
    from mcptoon import cli
    monkeypatch.setattr(cli, "_gateway_wired_in", lambda: True)
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    # A clean machine: python ok, config present, cache present, no servers.
    monkeypatch.setattr(cli.cfg, "has_config_file", lambda: True)
    monkeypatch.setattr(cli.cfg, "load_config", lambda: {})
    monkeypatch.setattr(cli, "_should_show_star_hint", lambda: False)
    monkeypatch.setattr(cli, "_doctor_smart_tips", lambda servers: None)
    out = io.StringIO()
    with redirect_stdout(out):
        cli._cmd_doctor([], json_mode=False)
    return out.getvalue()


def test_doctor_healthy_run_teaches_how_to_verify(monkeypatch):
    out = _run_doctor_healthy(monkeypatch)
    assert "All good" in out
    assert "mcptoon activity" in out


def test_doctor_verification_line_is_gated_on_gateway_wiring(monkeypatch):
    from mcptoon import cli
    monkeypatch.setattr(cli, "_gateway_wired_in", lambda: False)
    monkeypatch.setattr(config, "presence_enabled", lambda: True)
    monkeypatch.setattr(cli.cfg, "has_config_file", lambda: True)
    monkeypatch.setattr(cli.cfg, "load_config", lambda: {})
    monkeypatch.setattr(cli, "_should_show_star_hint", lambda: False)
    monkeypatch.setattr(cli, "_doctor_smart_tips", lambda servers: None)
    out = io.StringIO()
    with redirect_stdout(out):
        cli._cmd_doctor([], json_mode=False)
    text = out.getvalue()
    assert "All good" in text
    assert "See it working" not in text, "no gateway wired → no 'let an agent use it' advice"
