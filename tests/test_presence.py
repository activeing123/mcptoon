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
from mcptoon import welcome
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
    """Run cli.main() with argv and return stdout.

    `cli.main()` re-raises the `SystemExit` a command used to leave (that is how it
    reaches every exit path to emit the footer), so a bare `mcptoon` — which exits
    0 after printing help — must be caught here or every such test errors.
    """
    buf = io.StringIO()
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), contextlib.redirect_stdout(buf):
        try:
            cli.main()
        except SystemExit:
            pass
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
            "MCPTOON_SELFHEAL_FILE": str(self.home / ".selfheal"),
            "MCPTOON_FOOTER_STATE_FILE": str(self.home / "footer-state.json"),
            # Pin the language. `resolve_lang()` falls back to the OS UI language,
            # so without this the greeting is Chinese on a Chinese Windows box and
            # English on CI — the same test would assert against different strings
            # on different machines, which is the false-green/red-CI trap this file
            # already warns about for agent config paths.
            "MCPTOON_LANG": "en",
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
        self.assertIn("First run on this machine", out)
        self.assertIn("mcptoon status", out)
        self.assertTrue(cfg.welcome_seen(), "the marker must be written after greeting")

    def test_welcome_prints_only_once(self):
        first = _run_main(["list"])
        second = _run_main(["list"])
        self.assertIn("First run on this machine", first)
        self.assertNotIn("First run on this machine", second)

    def test_welcome_is_silent_for_machine_readable_formats(self):
        """A JSON consumer must get clean JSON — and the run must not consume the marker."""
        out = _run_main(["list", "--json"])
        self.assertNotIn("First run on this machine", out)
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

    def test_welcome_shows_skills_beside_tools(self):
        """The greeting is where "tools + skills" has to be true, not just the README.

        The skills half is worth ~100% of its native token cost (bench measures it),
        and for a long time every presence surface mentioned only tools — so the
        second product claim was invisible exactly where a new user looks first.
        """
        out = _run_main(["list"])
        self.assertIn("skills", out)
        self.assertIn("mcptoon skills list", out)

    def test_welcome_claims_privacy_and_undo(self):
        """A greeting that asks for attention must answer "why is this on my machine".

        Both lines are assertions the user can check, which is the only kind worth
        printing: `uninstall --dry` previews the cleanup, and "no daemon / no
        autostart / no upload" is the trojan fear named and denied.
        """
        out = _run_main(["list"])
        for claim in ("no daemon", "no autostart", "no upload",
                      "mcptoon off", "mcptoon uninstall --dry"):
            self.assertIn(claim, out)

    def test_welcome_uses_the_resolved_language(self):
        """One setting moves every human-facing string, greeting included."""
        with patch.dict(os.environ, {"MCPTOON_LANG": "zh"}):
            out = _run_main(["list"])
        self.assertIn("首次在本机运行", out)
        self.assertIn("无常驻进程", out)

    def test_bare_invocation_greets_then_still_prints_help(self):
        """`mcptoon` with no args is how people open the tool, and it used to open
        the help page with no sign mcptoon was installed at all — the second half
        of "it installed silently". Now the greeting comes first and the help page
        follows, unchanged (this is an addition, not a replacement)."""
        out = _run_main([])
        self.assertIn("First run on this machine", out)
        self.assertIn("mcptoon v", out, "the help page must still follow the greeting")
        self.assertTrue(cfg.welcome_seen())

    def test_bare_invocation_hints_once_the_card_is_spent(self):
        """A returning user does not need the pitch again. A bare `mcptoon` gets a
        one-line hint (present + one next step), never a second full card."""
        _run_main([])  # first run: card + help, marks seen
        out = _run_main([])
        self.assertNotIn("First run on this machine", out)
        self.assertIn("mcptoon status", out, "the hint must name a next step")
        self.assertIn("mcptoon v", out, "the help page still follows")

    def test_bare_invocation_respects_the_off_setting(self):
        cfg.set_setting("welcome", "off")
        out = _run_main([])
        self.assertNotIn("mcptoon is running here", out)
        self.assertIn("mcptoon v", out, "help prints whether or not we greet")

    def test_hint_omits_figures_it_does_not_have(self):
        """A hint on a machine with no cached catalog must not claim "0 tools"."""
        text = welcome.hint(lng="en", stream=io.StringIO())
        self.assertIn("mcptoon is running here", text)
        self.assertNotIn("0 tools", text, "a zero we did not measure is a false claim")


class TestFirstRunSelfHeal(_IsolatedHome):
    """Channel A′: the first real command finishes what `pip install` could not.

    `pip` runs no code, so it lands the package only: the agent-visible skill
    stays in site-packages and no skill index exists. Before this, only
    `quickstart` closed that gap, so a user who ran anything else ended up
    half-installed while the docs promised "pip install, then just use it". These
    tests pin that the very first command self-heals — once, additively, and only
    when a human is watching.
    """

    def _run(self, argv):
        """Run a command with self-heal forced on and every touched path sandboxed."""
        views = self.home / "views"
        roots = self.home / "skills"
        env = {
            "MCPTOON_FORCE_SELF_HEAL": "1",
            "MCPTOON_SKILLS_VIEWS": str(views),
            "MCPTOON_SKILLS_ROOTS": str(roots),
            "MCPTOON_SKILLS_INDEX": str(self.home / "index.json"),
            "MCPTOON_SKILLS_USAGE": str(self.home / "usage.json"),
        }
        with patch.dict(os.environ, env):
            return _run_main(argv)

    def test_first_command_installs_the_skill_and_builds_the_index(self):
        roots = self.home / "skills" / "demo"
        roots.mkdir(parents=True)
        (roots / "SKILL.md").write_text(
            "---\nname: demo\ndescription: a demo skill\n---\n\nbody\n", encoding="utf-8")

        out = self._run(["list"])

        installed = self.home / "views" / "mcptoon" / "SKILL.md"
        self.assertTrue(installed.is_file(), "the agent-visible skill was not written")
        self.assertIn("mcptoon skill installed", out)
        self.assertIn("Skill catalog indexed", out)
        self.assertTrue(cfg.selfheal_done())

    def test_it_runs_once_per_machine(self):
        self._run(["list"])
        second = self._run(["list"])
        self.assertNotIn("mcptoon skill installed", second,
                         "the self-heal must not repeat on every command")

    def test_it_never_overwrites_a_view_another_manager_owns(self):
        existing = self.home / "views" / "mcptoon"
        existing.mkdir(parents=True)
        marker = existing / "SKILL.md"
        marker.write_text("someone else's skill\n", encoding="utf-8")

        self._run(["list"])

        self.assertEqual(marker.read_text(encoding="utf-8"), "someone else's skill\n",
                         "an existing view must be left alone")

    def test_it_skips_machine_readable_formats(self):
        """A JSON consumer must get clean JSON, and the marker must survive."""
        out = self._run(["list", "--json"])
        self.assertNotIn("mcptoon skill installed", out)
        self.assertFalse(cfg.selfheal_done(), "a suppressed self-heal must not burn the marker")

    def test_it_skips_the_commands_that_are_leaving_or_speaking_stdio(self):
        for command in ("serve", "off", "uninstall", "demo", "demo-server", "completion", "help"):
            self.assertIn(command, cli._SELF_HEAL_EXEMPT)

    def test_it_is_off_under_pytest_unless_forced(self):
        """The default test process must not write into real skill folders.

        A test that runs a command in-process has no sandbox for the view roots,
        so the guard is what keeps the suite from touching the developer's own
        `~/.claude/skills`. The tests above opt back in explicitly.
        """
        with patch.dict(os.environ, {"MCPTOON_SKILLS_VIEWS": str(self.home / "views")}):
            _run_main(["list"])  # no MCPTOON_FORCE_SELF_HEAL
        self.assertFalse(cfg.selfheal_done())
        self.assertFalse((self.home / "views").exists())

    def test_a_read_only_home_does_not_crash(self):
        with patch.object(cfg, "_selfheal_file", side_effect=OSError("read-only")):
            cfg.mark_selfheal_done()  # must swallow the OSError, not raise


class TestWelcomeRendering(unittest.TestCase):
    """`welcome.render()` — the layout, and the two traps a pretty card creates."""

    _FACTS = {"servers": 3, "tools": 40, "tokens_full": 900, "tokens_slim": 300,
              "tokens_saved": 600, "savings_pct": 66.7}

    def test_every_card_line_is_the_same_display_width(self):
        """A right border that does not line up is the one thing a card cannot do.

        `len()` is the wrong ruler here: the Chinese subtitle is 14 characters but 22
        terminal columns wide, so counting characters would draw the border short on
        every CJK row — the exact bug this test exists to catch.
        """
        text = welcome.render(self._FACTS, skills=376, lng="zh", stream=io.StringIO())
        card = [ln for ln in text.splitlines() if ln and ln[0] in "┌│└"]
        self.assertEqual(len(card), 3, "expected a three-line card")
        widths = {welcome.display_width(ln) for ln in card}
        self.assertEqual(len(widths), 1, f"card borders disagree: {widths}")

    def test_a_pipe_gets_no_escape_codes(self):
        """The greeted agent reads this through a pipe; ANSI there is noise."""
        stream = io.StringIO()          # StringIO.isatty() is False
        text = welcome.render(self._FACTS, skills=376, lng="en", stream=stream)
        self.assertNotIn("\x1b[", text)

    def test_force_color_paints_and_no_color_strips_it(self):
        """Both switches are pinned here because this box exports `NO_COLOR=1`.

        `NO_COLOR` is the cross-tool convention and it wins over `MCPTOON_FORCE_COLOR`
        — so a test that only sets FORCE_COLOR paints nothing on this machine and
        everything on a box without NO_COLOR. Pinning the whole pair is what makes
        the assertion mean the same thing on both.
        """
        with patch.dict(os.environ, {"MCPTOON_FORCE_COLOR": "1",
                                     "NO_COLOR": "", "MCPTOON_NO_COLOR": ""}):
            painted = welcome.render(self._FACTS, skills=376, lng="en", stream=io.StringIO())
            self.assertIn("\x1b[", painted)
            self.assertIn("mcptoon status", painted.replace("\x1b[0m", "")
                          .replace("\x1b[2m", "").replace("\x1b[1;36m", "")
                          .replace("\x1b[1m", ""))
        with patch.dict(os.environ, {"NO_COLOR": "1", "MCPTOON_FORCE_COLOR": ""}):
            plain = welcome.render(self._FACTS, skills=376, lng="en", stream=io.StringIO())
            self.assertNotIn("\x1b[", plain)

    def test_an_unknown_skill_count_is_dropped_not_printed_as_zero(self):
        """`0 skills` would be a claim, and a false one when the index was never built."""
        text = welcome.render(self._FACTS, skills=None, lng="en", stream=io.StringIO())
        self.assertNotIn("0 skills", text)
        self.assertIn("40 tools", text)

    def test_a_console_that_cannot_encode_the_glyphs_gets_ascii(self):
        """A cp936 console redirected to a file raises on `🎉`/`┌` — the greeting must
        degrade to ASCII instead of crashing the first command a user ever runs."""

        class _Ascii(io.StringIO):
            encoding = "ascii"

        text = welcome.render(self._FACTS, skills=376, lng="en", stream=_Ascii())
        # The whole greeting must survive the write, not just the glyphs this
        # test happens to list: an earlier cut of this module routed the box
        # characters through the glyph table but left a hardcoded `·` in the
        # subtitle and an `—` in the closing note, so the fallback still raised.
        text.encode("ascii")
        for glyph in ("┌", "│", "└", "👋", "·", "→", "…", "—"):
            self.assertNotIn(glyph, text, f"{glyph!r} cannot be encoded by this stream")
        self.assertIn("mcptoon", text)

    def test_no_row_is_wider_than_the_terminal(self):
        """Long values must be clipped, never wrapped — a wrapped row breaks the card."""
        facts = dict(self._FACTS, servers=9999, tools=99999, tokens_full=99_999_999,
                     tokens_slim=1, tokens_saved=99_999_998, savings_pct=99.9)
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((60, 24))):
            text = welcome.render(facts, skills=99999, lng="en", stream=io.StringIO())
        for ln in text.splitlines():
            self.assertLessEqual(welcome.display_width(ln), 60, f"too wide: {ln!r}")


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


class TestCatalogCountConsistency(unittest.TestCase):
    """One catalog, one number — on every surface that prints a skill count.

    The failure this pins (found 2026-09-23): `bench` walked the catalog one level
    deep and said **376**, while `skills list` and the welcome card read the
    recursive index and said **406** — two commands, two confident answers about
    the same machine. That is the fastest way for a tool to lose the argument that
    *any* of its numbers are real, so every surface now walks recursively and reads
    the same index. The fixture is deliberately nested: a one-level walk sees fewer
    skills than the recursive one, so if a future edit reintroduces the shallow
    walk, this test goes red instead of shipping a second number.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root = base / "catalog"

        def _skill(d: Path, slug: str) -> None:
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {slug}\ndescription: does {slug} things. 触发词：{slug}\n---\n\nbody\n",
                encoding="utf-8")

        # One top-level skill, then two more nested two levels below it, so the
        # recursive catalog (3) and a one-level walk (1) genuinely disagree.
        _skill(self.root / "top", "top")
        nest = self.root / "skills" / "video-seedance" / "skills"
        _skill(nest / "seedance-audio", "seedance-audio")
        _skill(nest / "seedance-audio" / "skills" / "seedance-vfx", "seedance-vfx")

        self.index_path = base / "index.json"
        self.env = {
            "MCPTOON_SKILLS_INDEX": str(self.index_path),
            "MCPTOON_SKILLS_ROOTS": str(self.root),
            "MCPTOON_SKILLS_USAGE": str(base / "usage.json"),
            "MCPTOON_WELCOME_FILE": str(base / ".welcome"),
            "MCPTOON_SELFHEAL_FILE": str(base / ".selfheal"),
            "MCPTOON_FOOTER_STATE_FILE": str(base / "footer-state.json"),
            "MCPTOON_LANG": "en",
        }

    def _run(self, argv):
        with patch.dict(os.environ, self.env):
            return _run_main(argv)

    def test_every_surface_reports_the_same_skill_count(self):
        # Build the sandbox index exactly the way a user would.
        self._run(["skills", "index", str(self.root)])
        indexed = json.loads(self.index_path.read_text(encoding="utf-8"))
        n = len(indexed["skills"])
        self.assertIn("seedance-vfx", {s["slug"] for s in indexed["skills"]},
                      "fixture must nest a skill below another, or the shallow-walk "
                      "regression this test guards cannot be detected")

        bench = json.loads(self._run(["bench", "--json"]))
        self.assertEqual(bench["skills"]["count"], n,
                         "bench must count the same catalog the index serves")

        status = json.loads(self._run(["status", "--json"]))
        self.assertEqual(status["skills"], n,
                         "status must report the same catalog count as the index")

        listed = json.loads(self._run(["skills", "list", "--all", "--json"]))
        self.assertEqual(len(listed), n,
                         "skills list --all must report the same catalog count")


if __name__ == "__main__":
    unittest.main()
