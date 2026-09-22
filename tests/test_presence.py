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

"""Presence tests — the answer to "it installed and nothing happened".

A `pip install` cannot print anything, so before this change mcptoon landed on a
machine silently: no greeting, no status command, and — worst of all — its own
`serve` gateway was never written into any agent's config, so the MCP
`instructions` field it uses to announce itself to the model never fired once.

These tests pin the three channels that fix that:
  A. human   — a one-time first-run welcome (`_maybe_welcome`)
  B. agent   — `sync --self` registers `mcptoon serve` in every agent
  C. effect  — `mcptoon status` reports what's here and what it saves
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import sync as sync_mod
from mcptoon.sync import (
    SELF_SERVER_NAME,
    _build_mcp_servers_dict,
    _merge_self_entry,
    _self_serve_entry,
    _write_json_safe,
    sync_to_agent,
)

_SAMPLE_CONFIG = {
    "servers": {
        "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
    }
}


def _run_main(argv):
    """Run cli.main() with argv and return stdout."""
    buf = io.StringIO()
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), contextlib.redirect_stdout(buf):
        cli.main()
    return buf.getvalue()


class _IsolatedHome(unittest.TestCase):
    """Redirect every config path into a temp dir so the real ~/.mcptoon is untouched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self._env = patch.dict(os.environ, {
            "MCPTOON_CONFIG_FILE": str(self.home / "config.json"),
            "MCPTOON_SETTINGS_FILE": str(self.home / "settings.json"),
            "MCPTOON_WELCOME_FILE": str(self.home / ".welcome"),
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        (self.home / "config.json").write_text(json.dumps(_SAMPLE_CONFIG), encoding="utf-8")

    def _isolate_agents(self):
        """Point every agent config path at a non-existent file inside the temp home.

        `_gateway_wired_in()` scans ALL agents, so a test that patches only Cursor
        still sees the developer's real Cursor/Claude/Cline configs. On a machine
        where `mcptoon sync --self` has actually run, that makes these assertions
        pass or fail depending on who ran the suite — a false green locally and a
        red CI, or the reverse. Isolate all five paths, always.
        """
        return [
            patch.object(sync_mod, "_cursor_path", return_value=[]),
            patch.object(sync_mod, "_claude_desktop_path", return_value=self.home / "none-cd.json"),
            patch.object(sync_mod, "_cline_path", return_value=self.home / "none-cline.json"),
            patch.object(sync_mod, "_windsurf_path", return_value=self.home / "none-ws.json"),
            patch.object(sync_mod, "_vscode_copilot_path", return_value=self.home / "none-vsc.json"),
        ]


# ─── Channel A: the one-time welcome ───

class TestFirstRunWelcome(_IsolatedHome):
    def test_welcome_prints_on_first_run_and_marks_seen(self):
        out = _run_main(["list"])
        self.assertIn("first run on this machine", out)
        self.assertIn("mcptoon status", out)
        self.assertTrue(cfg.welcome_seen(), "the marker must be written after greeting")

    def test_welcome_prints_only_once(self):
        first = _run_main(["list"])
        second = _run_main(["list"])
        self.assertIn("first run on this machine", first)
        self.assertNotIn("first run on this machine", second)

    def test_welcome_is_silent_for_machine_readable_formats(self):
        """A JSON consumer must get clean JSON — and the run must not consume the marker."""
        out = _run_main(["list", "--json"])
        self.assertNotIn("first run on this machine", out)
        self.assertFalse(cfg.welcome_seen(), "a suppressed welcome must not burn the marker")

    def test_welcome_respects_the_off_setting(self):
        cfg.set_setting("welcome", "off")
        out = _run_main(["list"])
        self.assertNotIn("first run on this machine", out)

    def test_welcome_is_silent_when_stdout_is_a_help_page(self):
        out = _run_main(["--help"])
        self.assertNotIn("first run on this machine", out)

    def test_welcome_skips_commands_that_speak_for_themselves(self):
        """serve/demo already print their own output; the welcome would only pollute it."""
        for command in ("demo", "demo-server", "serve", "completion", "help", "--help"):
            self.assertIn(command, cli._WELCOME_EXEMPT)

    def test_welcome_survives_a_read_only_home(self):
        """A failed marker write must not turn a normal command into a crash."""
        with patch.object(cfg, "_welcome_file", side_effect=OSError("read-only")):
            cfg.mark_welcome_seen()  # must swallow the OSError, not raise


# ─── Channel B: registering the gateway itself ───

class TestSelfServeEntry(unittest.TestCase):
    def test_entry_invokes_serve_via_the_running_interpreter(self):
        entry = _self_serve_entry()
        self.assertEqual(entry["command"], cli.sys.executable)
        self.assertEqual(entry["args"], ["-m", "mcptoon", "serve"])

    def test_merge_self_entry_adds_without_clobbering(self):
        base = {"fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]}}
        merged = _merge_self_entry(base)
        self.assertIn("fetch", merged)
        self.assertIn(SELF_SERVER_NAME, merged)

    def test_merge_self_entry_never_overwrites_a_user_server_named_mcptoon(self):
        base = {SELF_SERVER_NAME: {"command": "custom", "args": []}}
        merged = _merge_self_entry(base)
        self.assertEqual(merged[SELF_SERVER_NAME]["command"], "custom")


class TestSyncIncludeSelf(_IsolatedHome):
    def test_dry_run_without_self_does_not_count_it(self):
        result = sync_to_agent("cursor", dry_run=True, config=_SAMPLE_CONFIG)
        self.assertEqual(result["servers_synced"], 1)

    def test_dry_run_with_self_counts_it(self):
        result = sync_to_agent("cursor", dry_run=True, config=_SAMPLE_CONFIG,
                               include_self=True)
        self.assertEqual(result["servers_synced"], 2)

    def test_real_write_lands_the_serve_entry(self):
        target = self.home / ".cursor" / "mcp.json"
        with patch.object(sync_mod, "_cursor_path", return_value=[target]):
            result = sync_to_agent("cursor", dry_run=False, config=_SAMPLE_CONFIG,
                                   include_self=True)
        self.assertTrue(result["written"])
        written = json.loads(target.read_text(encoding="utf-8"))
        entry = written["mcpServers"][SELF_SERVER_NAME]
        self.assertEqual(entry["args"], ["-m", "mcptoon", "serve"])

    def test_build_servers_dict_does_not_add_self(self):
        """The self entry is opt-in at the sync layer, not baked into the base builder."""
        self.assertNotIn(SELF_SERVER_NAME, _build_mcp_servers_dict(_SAMPLE_CONFIG))

    def test_sync_defaults_to_servers_only_and_self_opts_in(self):
        """`sync` is routine, so it must not inject a new entry unless asked (D1)."""
        with patch.object(sync_mod, "sync_to_all", return_value=[]) as fake:
            with contextlib.redirect_stdout(io.StringIO()):
                cli._cmd_sync([], "auto")
            self.assertFalse(fake.call_args.kwargs.get("include_self"))
        with patch.object(sync_mod, "sync_to_all", return_value=[]) as fake:
            with contextlib.redirect_stdout(io.StringIO()):
                cli._cmd_sync(["--self"], "auto")
            self.assertTrue(fake.call_args.kwargs.get("include_self"))

    def test_write_takes_a_backup_before_changing_a_config(self):
        """Writing into an agent config is destructive; the pre-change state is kept."""
        target = self.home / "mcp.json"
        target.write_text('{"mcpServers": {"old": {}}}', encoding="utf-8")
        self.assertTrue(_write_json_safe(target, {"mcpServers": {"new": {}}}))
        bak = target.with_suffix(".json.bak")
        self.assertTrue(bak.exists(), "a changed config must leave a .bak")
        self.assertIn('"old"', bak.read_text(encoding="utf-8"))

    def test_write_takes_no_backup_when_nothing_changes(self):
        target = self.home / "mcp.json"
        payload = {"mcpServers": {"same": {}}}
        _write_json_safe(target, payload)
        target.with_suffix(".json.bak").unlink(missing_ok=True)
        _write_json_safe(target, payload)
        self.assertFalse(target.with_suffix(".json.bak").exists(),
                         "an unchanged write must not litter a backup")

    def test_backup_never_clobbers_an_earlier_one(self):
        target = self.home / "mcp.json"
        target.write_text('{"mcpServers": {"first": {}}}', encoding="utf-8")
        _write_json_safe(target, {"mcpServers": {"second": {}}})
        _write_json_safe(target, {"mcpServers": {"third": {}}})
        bak = target.with_suffix(".json.bak")
        self.assertIn('"first"', bak.read_text(encoding="utf-8"),
                      "the backup must stay the original pre-mcptoon state")


# ─── Channel C: status ───

class TestStatusCommand(_IsolatedHome):
    def test_status_runs_and_reports_gateway_state(self):
        with contextlib.ExitStack() as stack:
            for p in self._isolate_agents():
                stack.enter_context(p)
            out = _run_main(["status"])
        self.assertIn("mcptoon — status", out)
        self.assertIn("Gateway in agents", out)
        self.assertIn("no — run `mcptoon sync --self`", out)

    def test_status_json_shape(self):
        out = _run_main(["status", "--json"])
        data = json.loads(out)
        for key in ("servers", "tools", "tokens_saved_est", "gateway_registered",
                    "footer_enabled"):
            self.assertIn(key, data)

    def test_status_detects_a_wired_gateway(self):
        target = self.home / ".cursor" / "mcp.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"mcpServers": {SELF_SERVER_NAME: {}}}), encoding="utf-8")
        with patch.object(sync_mod, "_cursor_path", return_value=[target]):
            self.assertTrue(cli._gateway_wired_in())

    def test_status_detects_vscode_shape(self):
        target = self.home / "settings.json"
        target.write_text(json.dumps({"mcp": {"servers": {SELF_SERVER_NAME: {}}}}),
                          encoding="utf-8")
        with patch.object(sync_mod, "_vscode_copilot_path", return_value=target), \
             patch.object(sync_mod, "_cursor_path", return_value=[]), \
             patch.object(sync_mod, "_claude_desktop_path", return_value=self.home / "nope.json"), \
             patch.object(sync_mod, "_cline_path", return_value=self.home / "nope2.json"), \
             patch.object(sync_mod, "_windsurf_path", return_value=self.home / "nope3.json"):
            self.assertTrue(cli._gateway_wired_in())

    def test_status_detects_cursor_shape(self):
        target = self.home / ".cursor" / "mcp.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"mcpServers": {SELF_SERVER_NAME: {}}}), encoding="utf-8")
        with patch.object(sync_mod, "_cursor_path", return_value=[target]), \
             patch.object(sync_mod, "_claude_desktop_path", return_value=self.home / "nope.json"), \
             patch.object(sync_mod, "_cline_path", return_value=self.home / "nope2.json"), \
             patch.object(sync_mod, "_windsurf_path", return_value=self.home / "nope3.json"), \
             patch.object(sync_mod, "_vscode_copilot_path", return_value=self.home / "nope4.json"):
            self.assertTrue(cli._gateway_wired_in())

    def test_status_tolerates_a_corrupt_agent_config(self):
        target = self.home / ".cursor" / "mcp.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{ not json", encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._isolate_agents():
                stack.enter_context(p)
            stack.enter_context(patch.object(sync_mod, "_cursor_path", return_value=[target]))
            self.assertFalse(cli._gateway_wired_in(),
                             "a malformed config must read as 'not wired', not crash")


class TestWelcomeSettingRegistered(unittest.TestCase):
    def test_welcome_is_a_known_setting(self):
        self.assertIn("welcome", cfg.SETTING_DEFAULTS)

    def test_welcome_enabled_defaults_true_and_off_disables(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"MCPTOON_SETTINGS_FILE": str(Path(tmp) / "s.json")}):
                self.assertTrue(cfg.welcome_enabled())
                cfg.set_setting("welcome", "off")
                self.assertFalse(cfg.welcome_enabled())


# ─── Channel C: the numbers are real ───

class TestTokenAccounting(unittest.TestCase):
    """`mcptoon usage` said `Tokens (est): 0` on every machine before this change,
    because no caller ever passed a token count. A tool whose whole pitch is token
    savings must be able to show one."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # _USAGE_FILE is bound at import time, so redirect the module attribute
        # rather than the environment — otherwise these tests would write to the
        # developer's real ~/.cache/mcptoon/usage.json.
        from mcptoon import usage
        self._usage = usage
        self._patch = patch.object(usage, "_USAGE_FILE", Path(self._tmp.name) / "usage.json")
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_count_tokens_is_nonzero_for_real_payloads(self):
        from mcptoon import usage
        self.assertGreater(usage.count_tokens({"message": "hello world"}), 0)
        self.assertGreater(usage.count_tokens("a longer string of words"), 0)

    def test_count_tokens_handles_none_and_empty(self):
        from mcptoon import usage
        self.assertEqual(usage.count_tokens(None), 0)
        self.assertEqual(usage.count_tokens(""), 0)

    def test_count_tokens_never_raises_on_unserialisable(self):
        from mcptoon import usage
        self.assertEqual(usage.count_tokens(object()), 0)

    def test_count_tokens_uses_the_bench_caliber(self):
        """One caliber only: whatever `bench` would count, `usage` counts."""
        from mcptoon import usage
        from mcptoon.bench import _tokenizer
        encode, _name, _exact = _tokenizer()
        payload = {"result": "x" * 50}
        self.assertEqual(usage.count_tokens(payload),
                         max(1, int(encode(json.dumps(payload, ensure_ascii=False)))))

    def test_track_call_records_the_payload_size(self):
        from mcptoon import usage
        usage.reset_usage()
        usage.track_call("echo", "echo", ok=True, payload={"message": "hello mcptoon"})
        stats = usage.get_usage_stats()
        self.assertEqual(stats["total_calls"], 1)
        self.assertGreater(stats["total_tokens_est"], 0,
                           "a recorded call must carry its token cost, not 0")

    def test_track_call_without_payload_records_zero(self):
        from mcptoon import usage
        usage.reset_usage()
        usage.track_call("echo", "echo", ok=False)
        self.assertEqual(usage.get_usage_stats()["total_tokens_est"], 0)


if __name__ == "__main__":
    unittest.main()
