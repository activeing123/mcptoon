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

"""Reversibility tests — the answer to "how do I get rid of this?".

A tool a user cannot switch off is indistinguishable from one that never asked.
The presence work (see tests/test_presence.py) made mcptoon *visible*; these
tests pin the other half of trust: it must also be *undoable*.

  - `mcptoon off`        removes ONLY the gateway entry, servers left intact
  - `mcptoon uninstall`  prints its plan first, never deletes your servers
  - `status`             quotes the same token caliber as `bench`
"""

from __future__ import annotations

import contextlib
import inspect
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
    gateway_present_in,
    remove_gateway_from_agent,
    remove_gateway_from_all,
    sync_to_all,
)

_SAMPLE_CONFIG = {
    "servers": {
        "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
    }
}


def _run_main(argv):
    buf = io.StringIO()
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), contextlib.redirect_stdout(buf):
        cli.main()
    return buf.getvalue()


class _IsolatedHome(unittest.TestCase):
    """Every config path (and the agent paths) redirected into a temp dir.

    Redirected through the same `MCPTOON_*` env vars the product reads, NOT by
    patching module attributes. That distinction is the whole point: an earlier
    version of this file patched only some attributes, and `_cmd_uninstall` was
    resolving other paths from config.py's import-time constants — so the test that
    exercises the destructive branch deleted the real `~/.mcptoon/config.json` and
    `settings.json` off the developer's machine. `setUp` now asserts every path the
    command can touch lives under the temp dir, so that class of bug fails loudly
    instead of eating someone's config.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.cache = self.home / "cache" / "mcptoon"
        self.cache.mkdir(parents=True)
        self._env = patch.dict(os.environ, {
            "MCPTOON_CONFIG_FILE": str(self.home / "config.json"),
            "MCPTOON_CONFIG_FILE_TOML": str(self.home / "config.toml"),
            "MCPTOON_SETTINGS_FILE": str(self.home / "settings.json"),
            "MCPTOON_WELCOME_FILE": str(self.home / ".welcome"),
            "MCPTOON_SELFHEAL_FILE": str(self.home / ".selfheal"),
            "MCPTOON_FOOTER_STATE_FILE": str(self.home / "footer-state.json"),
            "MCPTOON_TOGGLE_FILE": str(self.home / "toggles.json"),
            "MCPTOON_COMPRESSION_FILE": str(self.home / "compression.json"),
            "MCPTOON_CACHE_DIR": str(self.cache),
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        (self.home / "config.json").write_text(json.dumps(_SAMPLE_CONFIG), encoding="utf-8")
        # Agent configs too, not just mcptoon's own files. `uninstall` calls
        # `remove_gateway_from_all`, which writes every agent config it finds — and
        # on a machine where `sync --self` has really run, "every agent config" is
        # the developer's. A sandbox test that only redirects MCPTOON_* env still
        # deleted the real gateway entries until this was added.
        for patcher in self._isolate_agents():
            patcher.start()
            self.addCleanup(patcher.stop)
        # And the manifest. `status` (and the command preamble) will otherwise load
        # the developer's real catalog, which spawns every configured MCP server —
        # npx, uvx, python — turning this file into a minute-long, network-touching
        # test run whose speed depends on how many servers the machine happens to
        # have. An empty manifest is the honest default here: these tests are about
        # presence, paths and undo, not about token counts.
        manifest_patch = patch.object(cli.manifest_mod, "get_manifest", return_value={})
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)
        self.assert_paths_are_isolated()

    def _isolate_agents(self):
        """Point every agent config path inside the temp home (non-existent)."""
        return [
            patch.object(sync_mod, "_cursor_path", return_value=[self.home / "none-cursor.json"]),
            patch.object(sync_mod, "_claude_desktop_path", return_value=self.home / "none-cd.json"),
            patch.object(sync_mod, "_cline_path", return_value=self.home / "none-cline.json"),
            patch.object(sync_mod, "_windsurf_path", return_value=self.home / "none-ws.json"),
            patch.object(sync_mod, "_vscode_copilot_path", return_value=self.home / "none-vsc.json"),
        ]

    def assert_paths_are_isolated(self):
        """No path `off` / `uninstall` can touch may resolve outside the temp dir."""
        home = self.home.resolve()
        for group, paths in cfg.state_paths().items():
            for p in paths:
                self.assertTrue(
                    Path(p).resolve().is_relative_to(home),
                    f"state_paths()[{group}] escapes the temp home: {p} "
                    f"(this is how a test deletes the real ~/.mcptoon)")

    def _cursor(self, servers: dict) -> Path:
        target = self.home / ".cursor" / "mcp.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
        return target

    def _patch_only_cursor(self, target: Path):
        return [
            patch.object(sync_mod, "_cursor_path", return_value=[target]),
            patch.object(sync_mod, "_claude_desktop_path", return_value=self.home / "nope.json"),
            patch.object(sync_mod, "_cline_path", return_value=self.home / "nope2.json"),
            patch.object(sync_mod, "_windsurf_path", return_value=self.home / "nope3.json"),
            patch.object(sync_mod, "_vscode_copilot_path", return_value=self.home / "nope4.json"),
        ]


# ─── remove_gateway_from_agent: the surgical undo ───

class TestRemoveGateway(_IsolatedHome):
    def test_removes_only_the_gateway_entry(self):
        target = self._cursor({
            "fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]},
            SELF_SERVER_NAME: {"command": "python", "args": ["-m", "mcptoon", "serve"]},
        })
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            result = remove_gateway_from_agent("cursor")
        self.assertTrue(result["removed"])
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn("fetch", written["mcpServers"], "user servers must survive")
        self.assertNotIn(SELF_SERVER_NAME, written["mcpServers"])

    def test_leaves_a_backup_of_the_pre_change_state(self):
        target = self._cursor({SELF_SERVER_NAME: {}, "keep": {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            remove_gateway_from_agent("cursor")
        bak = target.with_suffix(".json.bak")
        self.assertTrue(bak.exists())
        self.assertIn(SELF_SERVER_NAME, bak.read_text(encoding="utf-8"))

    def test_reports_not_removed_when_entry_absent(self):
        target = self._cursor({"fetch": {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            result = remove_gateway_from_agent("cursor")
        self.assertFalse(result["removed"])
        self.assertFalse(result["written"])

    def test_dry_run_reports_but_writes_nothing(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        before = target.read_text(encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            result = remove_gateway_from_agent("cursor", dry_run=True)
        self.assertTrue(result["removed"])
        self.assertFalse(result["written"])
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_handles_vscode_shape(self):
        target = self.home / "settings.json"
        target.write_text(json.dumps(
            {"mcp": {"servers": {SELF_SERVER_NAME: {}, "keep": {}}}}), encoding="utf-8")
        with patch.object(sync_mod, "_vscode_copilot_path", return_value=target):
            result = remove_gateway_from_agent("vscode-copilot")
        self.assertTrue(result["removed"])
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertNotIn(SELF_SERVER_NAME, written["mcp"]["servers"])
        self.assertIn("keep", written["mcp"]["servers"])


class TestGatewayPresence(_IsolatedHome):
    def test_present_and_absent(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            self.assertTrue(gateway_present_in("cursor"))
        target.write_text(json.dumps({"mcpServers": {"fetch": {}}}), encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            self.assertFalse(gateway_present_in("cursor"))


class TestRemoveGatewayAll(_IsolatedHome):
    def test_deduplicates_agents_that_resolve_to_one_file(self):
        """Cursor global and project can be the same file; report it once.

        Deliberately does NOT patch `_agent_config_path`: the dedupe must be judged
        on the resolved file, and patching the path resolver made an earlier version
        of this test pass while the real code compared two differently-spelled paths
        for the same file, processed it twice and reported "6 agents" for five files.
        """
        target = self._cursor({SELF_SERVER_NAME: {}})
        fake_agents = [
            {"id": "cursor", "name": "Cursor (global)", "config_path": str(target), "exists": True},
            # Same file, different spelling — a ./-relative path resolves identically.
            {"id": "cursor", "name": "Cursor (project)",
             "config_path": str(Path(target.parent) / "." / target.name), "exists": True},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents):
            results = remove_gateway_from_all(dry_run=True)
        self.assertEqual(len(results), 1, "one file, one result — not one per agent row")
        self.assertTrue(results[0]["removed"])

    def test_cleans_a_project_level_cursor_config_too(self):
        """Two genuinely different Cursor files must both lose the entry.

        `_agent_config_path("cursor")` only ever names the global file, so before
        the `path` override existed, a project-level `.cursor/mcp.json` kept the
        gateway entry that `mcptoon off` had just reported as removed.
        """
        global_cfg = self.home / "cursor-global.json"
        project_cfg = self.home / "project" / ".cursor" / "mcp.json"
        project_cfg.parent.mkdir(parents=True)
        for path in (global_cfg, project_cfg):
            path.write_text(json.dumps(
                {"mcpServers": {SELF_SERVER_NAME: {}, "mine": {}}}), encoding="utf-8")
        fake_agents = [
            {"id": "cursor", "name": "Cursor (global)", "config_path": str(global_cfg), "exists": True},
            {"id": "cursor", "name": "Cursor (project)", "config_path": str(project_cfg), "exists": True},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents), \
                patch.object(sync_mod, "_agent_config_path", return_value=global_cfg):
            results = remove_gateway_from_all()
        self.assertEqual(len(results), 2, "two distinct files, two results")
        for path in (global_cfg, project_cfg):
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(SELF_SERVER_NAME, written["mcpServers"], f"gateway left in {path}")
            self.assertIn("mine", written["mcpServers"], f"user server lost from {path}")


class TestSyncDoesNotReportPhantomAgents(_IsolatedHome):
    """`sync` must report the files it writes, not the agent rows it was handed.

    The mirror image of the removal bug: Cursor lists a global and a project-level
    config, sync only ever writes the global one, so the project row used to add a
    second "✓ 13 servers" line for the same file and inflate the totals. A count of
    work that did not happen is the same class of dishonesty as a savings figure
    with no measurement behind it.
    """

    def test_a_project_row_that_shares_the_canonical_file_collapses(self):
        target = self.home / "cursor.json"
        fake_agents = [
            {"id": "cursor", "name": "Cursor (global)", "config_path": str(target), "exists": True},
            {"id": "cursor", "name": "Cursor (project)", "config_path": str(target), "exists": True},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents), \
                patch.object(sync_mod, "_cursor_path", return_value=[target, target]), \
                patch.object(sync_mod, "sync_to_agent",
                             return_value={"agent": "cursor", "written": True,
                                           "servers_synced": 3, "error": None}) as fake:
            results = sync_to_all(dry_run=True)
        self.assertEqual(len(results), 1, "one file, one write, one row")
        self.assertEqual(fake.call_count, 1, "the same file must not be written twice")

    def test_a_distinct_project_config_is_not_written_to(self):
        """sync stays off a project-level `.cursor/mcp.json` it would have to create.

        Writing into whatever directory the user is standing in is exactly the kind
        of unasked-for side effect this command should not have, so the project row
        collapses into the global one rather than being synced separately.
        """
        global_cfg = self.home / "cursor-global.json"
        project_cfg = self.home / "proj" / ".cursor" / "mcp.json"
        fake_agents = [
            {"id": "cursor", "name": "Cursor (global)", "config_path": str(global_cfg), "exists": True},
            {"id": "cursor", "name": "Cursor (project)", "config_path": str(project_cfg), "exists": True},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents), \
                patch.object(sync_mod, "_cursor_path", return_value=[global_cfg, project_cfg]), \
                patch.object(sync_mod, "sync_to_agent",
                             return_value={"agent": "cursor", "written": True,
                                           "servers_synced": 3, "error": None}):
            results = sync_to_all(dry_run=True)
        self.assertEqual(len(results), 1)
        self.assertFalse(project_cfg.exists(), "sync created a config in the project dir")


# ─── `mcptoon off` ───

class TestOffCommand(_IsolatedHome):
    def test_dry_run_writes_nothing(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        before = target.read_text(encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            out = _run_main(["off", "--dry"])
        self.assertIn("DRY RUN", out)
        self.assertIn("would remove", out)
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_real_run_removes_gateway_and_keeps_servers(self):
        target = self._cursor({"fetch": {"command": "npx", "args": []}, SELF_SERVER_NAME: {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            out = _run_main(["off"])
        self.assertIn("removed the gateway entry", out)
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn("fetch", written["mcpServers"])
        self.assertNotIn(SELF_SERVER_NAME, written["mcpServers"])

    def test_reports_when_nothing_to_do(self):
        target = self._cursor({"fetch": {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_only_cursor(target):
                stack.enter_context(p)
            out = _run_main(["off"])
        self.assertIn("not registered in any agent", out)


# ─── `mcptoon uninstall` ───

class TestUninstallCommand(_IsolatedHome):
    def _patch_all_agents(self, target: Path):
        return self._patch_only_cursor(target)

    def test_dry_run_changes_nothing_and_names_what_it_keeps(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        before = target.read_text(encoding="utf-8")
        (self.home / "settings.json").write_text("{}", encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._patch_all_agents(target):
                stack.enter_context(p)
            out = _run_main(["uninstall", "--dry"])
        self.assertIn("DRY RUN", out)
        self.assertIn("KEEP config.json", out)
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertTrue((self.home / "settings.json").exists(), "dry run deletes nothing")

    def test_yes_removes_gateway_and_settings_but_keeps_server_config(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        (self.home / "settings.json").write_text("{}", encoding="utf-8")
        with contextlib.ExitStack() as stack:
            for p in self._patch_all_agents(target):
                stack.enter_context(p)
            out = _run_main(["uninstall", "--yes"])
        self.assertIn("Removed the gateway", out)
        # Server definitions survive — deleting them would be the real betrayal.
        self.assertTrue((self.home / "config.json").exists(),
                        "uninstall must not delete the user's server definitions")
        self.assertFalse((self.home / "settings.json").exists())
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertNotIn(SELF_SERVER_NAME, written["mcpServers"])

    def test_refuses_without_confirmation_when_non_interactive(self):
        target = self._cursor({SELF_SERVER_NAME: {}})
        with contextlib.ExitStack() as stack:
            for p in self._patch_all_agents(target):
                stack.enter_context(p)
            with patch.object(cli.sys.stdin, "isatty", return_value=False):
                out = _run_main(["uninstall"])
        self.assertIn("Refusing to delete", out)
        written = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn(SELF_SERVER_NAME, written["mcpServers"], "nothing removed without --yes")


# ─── status: one caliber ───

class TestStatusCaliber(_IsolatedHome):
    _TOOLS = {
        "demo": [
            {"name": "echo", "description": "Echo back a string to the caller.",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string",
                                                     "description": "What to echo."}}}},
        ]
    }

    def test_status_quotes_the_bench_caliber(self):
        """The savings line names the same tokenizer `bench` uses — one caliber."""
        from mcptoon.bench import _tokenizer
        _encode, caliber, exact = _tokenizer()
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            out = _run_main(["status"])
        # The line must quote whatever caliber `bench` is using on this machine —
        # the exact tiktoken name where it is installed, or the explicit chars/4
        # fallback label where it is not (CI has no tiktoken). Either way it is
        # the *same* caliber, and the fallback is labelled, never passed as measured.
        self.assertIn(caliber, out, "status must quote the same caliber as bench")
        if exact:
            self.assertNotIn("chars/4 estimate",
                             out.split("mcptoon — status")[-1].split("Take it back")[0],
                             "with tiktoken present, the old chars/4 caliber must not survive")

    def test_status_json_caliber_matches_bench(self):
        from mcptoon.bench import _tokenizer
        _encode, caliber, _exact = _tokenizer()
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            out = _run_main(["status", "--json"])
        data = json.loads(out)
        self.assertEqual(data["token_caliber"], caliber)

    def test_status_json_reports_both_sides_of_the_saving(self):
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            data = json.loads(_run_main(["status", "--json"]))
        self.assertGreater(data["tokens_full"], 0)
        self.assertGreater(data["tokens_slim"], 0)
        self.assertEqual(data["tokens_saved_est"], data["tokens_full"] - data["tokens_slim"])

    def test_status_shows_the_undo_paths(self):
        out = _run_main(["status"])
        self.assertIn("mcptoon off", out)
        self.assertIn("mcptoon uninstall", out)

    def test_stats_and_status_report_the_same_savings(self):
        """Two commands answering "how much does this save?" must not disagree.

        `stats` divided character counts by 4 while `status` used tiktoken, so the
        two printed different numbers for the same catalog — 20,306/15,292 against
        20,914/15,719 on the real machine. Nobody noticed for as long as it was
        true because `stats` was not advertised in `--help`, so the only way to
        find the discrepancy was to already know both commands existed. This is the
        test that would have caught it.
        """
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            status = json.loads(_run_main(["status", "--json"]))
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            stats = json.loads(_run_main(["stats", "--json"]))
        self.assertEqual(stats["full_tokens_est"], status["tokens_full"],
                         "stats and status disagree about the full-JSON side")
        self.assertEqual(stats["slim_tokens_est"], status["tokens_slim"],
                         "stats and status disagree about the slim side")
        self.assertEqual(stats["tokens_saved"], status["tokens_saved_est"])
        self.assertEqual(stats["token_caliber"], status["token_caliber"])

    def test_stats_never_falls_back_to_chars_over_four(self):
        """The old ruler must not survive anywhere in the savings surface."""
        source = inspect.getsource(cli._cmd_stats)
        self.assertNotIn("// 4", source,
                         "_cmd_stats is estimating tokens by dividing characters again")


class TestDestructiveCommandsCannotEscapeTheSandbox(_IsolatedHome):
    """The regression tests for the incident that cost real user data.

    `_cmd_uninstall` originally resolved its paths from config.py's import-time
    constants. Those constants are computed once at import and therefore ignore the
    `MCPTOON_*_FILE` env overrides, so the test that exercises the destructive
    branch — which redirects env vars, not module attributes — deleted the real
    `~/.mcptoon/config.json` and `settings.json`. Two independent guards now stand
    between a test and that outcome, and both are pinned here.
    """

    def test_state_paths_follow_the_env_overrides(self):
        """The mechanism, directly: every path must be redirected by env alone."""
        self.assert_paths_are_isolated()
        paths = cfg.state_paths()
        self.assertIn(Path(self.home / "config.json").resolve(),
                      [Path(p).resolve() for p in paths["servers"]])
        self.assertIn(self.cache.resolve(),
                      [Path(p).resolve() for p in paths["cache"]])

    def test_module_constants_are_not_what_the_command_uses(self):
        """Pin the actual defect: reading the constants must NOT be enough.

        If this ever starts failing because the constants agree with the env, the
        call sites could go back to the constants — but until then, any code path
        that reaches for `cfg.CONFIG_FILE` is the bug.
        """
        self.assertNotEqual(Path(cfg.CONFIG_FILE).resolve(),
                            Path(self.home / "config.json").resolve(),
                            "cfg.CONFIG_FILE tracked the env override — if the "
                            "constants became lazy, this guard needs rethinking")

    def test_uninstall_yes_does_not_touch_a_config_outside_the_sandbox(self):
        """End to end: run the real destructive branch and prove the blast radius."""
        outside = self.home.parent / "bystander.json"
        outside.write_text('{"servers": {}}', encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        _run_main(["uninstall", "--yes"])
        self.assertTrue(outside.exists(), "uninstall reached outside the sandbox")

    def test_uninstall_keeps_the_config_directory_itself(self):
        """Only files inside it, never the directory: the servers live here."""
        (self.home / "policies.json").write_text("{}", encoding="utf-8")
        _run_main(["uninstall", "--yes"])
        self.assertTrue(self.home.exists())
        self.assertTrue((self.home / "config.json").exists(),
                        "the user's server definitions must survive --yes")

    def test_no_welcome_on_the_way_out(self):
        """`off` / `uninstall` must not print "hi, here's what I configured".

        Both are exempt from the first-run note: greeting someone on the way out is
        the same obliviousness the presence work exists to remove.
        """
        for command in ("off", "uninstall"):
            self.assertIn(command, cli._WELCOME_EXEMPT)

    def test_uninstall_reports_a_refused_directory(self):
        """A cache dir mcptoon does not own is reported, not deleted."""
        outside = self.home / "elsewhere"
        outside.mkdir()
        with patch.object(cfg, "state_paths", return_value={
                "bookkeeping": [], "servers": [], "cache": [outside]}):
            out = _run_main(["uninstall", "--yes"])
        self.assertTrue(outside.exists())
        self.assertIn("Refused to delete", out)


class TestSafeRmtree(unittest.TestCase):
    """`uninstall` refuses to recursively delete a directory it does not own.

    A destructive command should not be one bad constant away from deleting the
    user's home: if `MCPTOON_CACHE_DIR` ever resolved to a parent, an unguarded
    `rmtree` would take everything with it.
    """

    def test_refuses_a_directory_not_named_mcptoon(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "not-ours"
            victim.mkdir()
            (victim / "keep.txt").write_text("x", encoding="utf-8")
            self.assertFalse(cli._safe_rmtree(victim))
            self.assertTrue(victim.exists(), "it deleted a directory it does not own")

    def test_removes_a_directory_it_owns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ours = Path(tmp) / "mcptoon"
            ours.mkdir()
            (ours / "cache.json").write_text("{}", encoding="utf-8")
            self.assertTrue(cli._safe_rmtree(ours))
            self.assertFalse(ours.exists())

    def test_refuses_a_filesystem_root(self):
        for root in (Path("/"), Path("C:/")):
            if root.exists():
                self.assertFalse(cli._safe_rmtree(root),
                                 f"it agreed to delete {root}")


class TestDestructiveCommandsReadPathsLate(unittest.TestCase):
    """Mechanical guard on the code itself, not on its runtime output.

    `assert_paths_are_isolated` in `_IsolatedHome` checks what `state_paths()`
    returns — but the incident was code that never called `state_paths()` and read
    `cfg.CONFIG_FILE` / `cfg.SETTINGS_FILE` instead. Those module constants are
    computed once at import and therefore ignore the `MCPTOON_*_FILE` overrides, so
    a single such reference is exactly how a unit test deleted the real
    `~/.mcptoon/config.json`. Checking the source catches a reintroduction even
    when the caller's environment happens to make the paths look right.
    """

    # Every path constant config.py freezes at import time.
    IMPORT_TIME_PATHS = ("CONFIG_DIR", "CONFIG_FILE", "CONFIG_FILE_TOML", "SETTINGS_FILE",
                         "WELCOME_FILE", "SELFHEAL_FILE", "FOOTER_STATE_FILE", "TOGGLE_FILE",
                         "POLICY_FILE", "CACHE_DIR", "HOME_DIR")

    def _assert_reads_late(self, fn, allow=()):
        src = inspect.getsource(fn)
        for const in self.IMPORT_TIME_PATHS:
            if const in allow:
                continue
            self.assertNotIn(
                f"cfg.{const}", src,
                f"{fn.__name__} reads the import-time constant cfg.{const}; this "
                f"ignores MCPTOON_*_FILE overrides and deletes real user data. "
                f"Use config.state_paths() (call-time, env-aware) instead.")

    def test_uninstall_reads_every_path_at_call_time(self):
        self._assert_reads_late(cli._cmd_uninstall)
        self.assertIn("state_paths", inspect.getsource(cli._cmd_uninstall),
                      "uninstall must resolve its paths through state_paths()")

    def test_off_reads_paths_at_call_time(self):
        self._assert_reads_late(cli._cmd_off)

    def test_status_reads_paths_at_call_time(self):
        self._assert_reads_late(cli._cmd_status)

    def test_safe_rmtree_owns_only_its_own_directory_name(self):
        self.assertIn('"mcptoon"', inspect.getsource(cli._safe_rmtree))


class TestFooterFacts(_IsolatedHome):
    """The per-turn footer must be fast and honest, or it is not usable.

    The agent-side directive (`serve._INSTRUCTIONS`) asks the model to close a
    turn with one line of savings. The obvious way to get that line is
    `mcptoon status`, which refreshes a stale schema cache by spawning every
    configured MCP server — measured at ~23s cold against ~1.9s warm on this
    machine. A footer that sometimes costs 23 seconds is worse than no footer,
    so `footer-facts` reads the cache at whatever age it has and never opens a
    connection. These tests pin both halves: the numbers agree with
    `status`/`stats`, and the command cannot be made to wait on a server.
    """

    _TOOLS = {
        "demo": [
            {"name": "echo", "description": "Echo back a string to the caller.",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string",
                                                     "description": "What to echo."}}}},
            {"name": "shout", "description": "Echo, uppercased.",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string",
                                                     "description": "What to shout."}}}},
        ]
    }

    def _seed_cache(self, age_seconds=0.0):
        """Write the demo catalog into the cache for every configured server.

        Keyed by the *configured* names (`_IsolatedHome` writes a one-server
        config), because `footer-facts` iterates `list_servers()` and ignores
        cache entries for servers that are not configured.
        """
        import time as _time
        data = {name: {"tools": self._TOOLS["demo"],
                       "ts": _time.time() - age_seconds,
                       "fp": "x"}
                for name in cfg.list_servers()}
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "schema_cache.json").write_text(json.dumps(data), encoding="utf-8")

    def test_footer_facts_reports_the_same_numbers_as_status_and_stats(self):
        self._seed_cache()
        footer = json.loads(_run_main(["footer-facts", "--json"]))
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            status = json.loads(_run_main(["status", "--json"]))
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            stats = json.loads(_run_main(["stats", "--json"]))
        self.assertEqual(footer["tokens_full"], status["tokens_full"])
        self.assertEqual(footer["tokens_slim"], status["tokens_slim"])
        self.assertEqual(footer["tokens_saved"], status["tokens_saved_est"])
        self.assertEqual(footer["tokens_full"], stats["full_tokens_est"])
        self.assertEqual(footer["token_caliber"], status["token_caliber"])
        self.assertEqual(footer["tools"], 2)

    def test_footer_facts_never_calls_get_manifest(self):
        """The whole point: it must not be able to spawn a server."""
        self._seed_cache()
        with patch.object(cli.manifest_mod, "get_manifest",
                          side_effect=AssertionError("footer-facts spawned a server")):
            out = _run_main(["footer-facts"])
        self.assertIn("mcptoon:", out)

    def test_footer_facts_serves_a_stale_cache_instead_of_refreshing(self):
        """A stale cache must still answer — fast — and must say it is stale."""
        self._seed_cache(age_seconds=99999)
        data = json.loads(_run_main(["footer-facts", "--json"]))
        self.assertGreater(data["tokens_full"], 0, "stale cache must still yield numbers")
        self.assertIsNotNone(data["note"])
        self.assertIn("old", data["note"])

    def test_footer_facts_says_so_when_nothing_is_cached(self):
        data = json.loads(_run_main(["footer-facts", "--json"]))
        self.assertEqual(data["tools"], 0)
        self.assertIn("not cached", data["note"])

    def test_footer_facts_reports_staleness_even_when_a_server_is_missing(self):
        """Both caveats must surface together, not one instead of the other.

        These numbers get quoted verbatim into a chat turn, so a stale figure
        reported as fresh is the failure that matters. The first version tested
        the two caveats as elif branches; on the author's machine the cache was
        2.1h old against a 5-minute TTL and the note still read as though only
        the tool count were partial — the staleness was silently swallowed.
        """
        (self.home / "config.json").write_text(json.dumps({"servers": {
            "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            "ghost": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/ghost"]},
        }}), encoding="utf-8")
        import time as _time
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "schema_cache.json").write_text(json.dumps(
            {"fetch": {"tools": self._TOOLS["demo"], "ts": _time.time() - 99999, "fp": "x"}}),
            encoding="utf-8")
        note = json.loads(_run_main(["footer-facts", "--json"]))["note"]
        self.assertIn("not cached", note, "the missing server must be named")
        self.assertIn("old", note, "the stale cache must be named too, not masked")

    def test_footer_facts_reads_the_cache_dir_at_call_time(self):
        """`MCPTOON_CACHE_DIR` must actually move this file (it did not, once)."""
        src = inspect.getsource(cli._cmd_footer_facts)
        self.assertNotIn("cfg.CACHE_DIR", src,
                         "footer-facts must not read the import-time cache constant")

    def test_the_cache_module_honours_the_env_var(self):
        """Regression: `_CACHE_FILE` was a constant, so MCPTOON_CACHE_DIR lied."""
        from mcptoon import cache as cache_mod
        with patch.dict(os.environ, {"MCPTOON_CACHE_DIR": str(self.home / "elsewhere")}):
            resolved = cache_mod._cache_file()
        self.assertEqual(resolved.parent, self.home / "elsewhere",
                         "MCPTOON_CACHE_DIR is documented but did not relocate the cache")
        self.assertFalse(hasattr(cache_mod, "_CACHE_FILE"),
                         "_CACHE_FILE is back as a module constant; it ignores the env var")


class TestHelpAdvertisesUndo(unittest.TestCase):
    def test_help_lists_off_and_uninstall(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._print_help()
        text = buf.getvalue()
        self.assertIn("mcptoon off", text)
        self.assertIn("mcptoon uninstall", text)

    def test_help_lists_footer_facts(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._print_help()
        self.assertIn("mcptoon footer-facts", buf.getvalue(),
                      "the per-turn footer command must be discoverable")


def _run_main_streams(argv):
    """stdout and stderr of one in-process `mcptoon <argv>` run.

    `cli.main()` re-raises `SystemExit` on purpose, so the real process exit code
    still works; most commands leave through `sys.exit()`, so the caller absorbs
    it here and inspects the streams instead.
    """
    out, err = io.StringIO(), io.StringIO()
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cli.main()
        except SystemExit:
            pass
    return out.getvalue(), err.getvalue()


class TestTheFooterReachesEverySurface(_IsolatedHome):
    """The line has to arrive on its own, not only when the model remembers it.

    `footer-facts` is a *soft* channel: it works only if an agent reads the
    directive, remembers it, and complies. On a client that speaks no MCP — DSH,
    which is why this round exists — nothing ever appeared, so the tool whose job
    is compressing the context was itself invisible.

    The fix is to stamp the payloads mcptoon already controls, so the tests here
    pin five properties of that:

      - the tail of every CLI command carries the line (reaches any agent with a
        shell), on **stderr**, leaving machine-readable stdout byte-exact
      - the stdio servers (`serve`, `demo-server`) are never stamped, where one
        stray write can desynchronise the JSON-RPC stream
      - `--version` and `footer-facts` stay byte-clean
      - the first tool result of an MCP session is stamped exactly once
      - one setting (`footer`) turns every surface off, and a footer that cannot
        be built never fails the command carrying it
    """

    # Same catalog as `TestFooterFacts`, so the two suites cannot disagree about
    # what a catalogue is.
    _TOOLS = TestFooterFacts._TOOLS

    def _seed_cache(self):
        import time as _time
        data = {name: {"tools": self._TOOLS["demo"], "ts": _time.time(), "fp": "x"}
                for name in cfg.list_servers()}
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / "schema_cache.json").write_text(json.dumps(data), encoding="utf-8")

    def _bridge(self):
        from mcptoon.serve import MCPServerBridge

        b = MCPServerBridge()
        b._servers, b._pool, b._tool_index, b._initialized = {}, None, {}, True
        return b

    @staticmethod
    def _payload(text="upstream said hi"):
        return {"content": [{"type": "text", "text": text}], "isError": False}

    # ─── CLI tail ───

    def test_the_cli_tail_carries_the_line(self):
        self._seed_cache()
        _, err = _run_main_streams(["list"])
        self.assertIn("mcptoon:", err,
                      "a command that prints nothing extra is the invisibility bug")

    def test_the_line_opens_with_the_emoji_mark(self):
        """The whole point is that the line gets noticed; the user asked for an emoji
        (2026-09-22). Pinned so a later edit cannot quietly drop it, and pinned as a
        *prefix* so the `mcptoon:` substring every other test keys on stays intact."""
        from mcptoon import footer as footer_mod

        self.assertTrue(footer_mod.MARK, "the mark must not be empty")
        self.assertTrue(footer_mod.line().startswith(footer_mod.MARK + " mcptoon:"),
                        "the line must open with the emoji mark, then `mcptoon:`")

    def test_the_emoji_mark_does_not_leak_into_json_or_version(self):
        """`--json` and `--version` are machine channels: the mark belongs on the
        human-facing line only, or a parser would choke on a decorated payload."""
        self._seed_cache()
        out, _ = _run_main_streams(["footer-facts", "--json"])
        json.loads(out)  # raises if the emoji leaked into the JSON body
        vout, _ = _run_main_streams(["--version"])
        self.assertRegex(vout.strip(), r"^mcptoon \d")

    def test_the_cli_tail_goes_to_stderr_not_stdout(self):
        """stdout is a data channel: `mcptoon status --json | jq` must keep working."""
        self._seed_cache()
        out, err = _run_main_streams(["list"])
        self.assertNotIn("mcptoon:", out, "the footer must not pollute stdout")
        self.assertIn("mcptoon:", err)

    def test_a_json_command_keeps_a_parseable_stdout(self):
        self._seed_cache()
        with patch.object(cli.manifest_mod, "get_manifest", return_value=self._TOOLS):
            out, err = _run_main_streams(["status", "--json"])
        parsed = json.loads(out)  # raises if the footer leaked into stdout
        self.assertIn("tokens_full", parsed)
        self.assertIn("mcptoon:", err)

    def test_version_stays_byte_clean(self):
        """Scripts and the AGENTS.md install check parse this."""
        out, err = _run_main_streams(["--version"])
        self.assertRegex(out.strip(), r"^mcptoon \d")
        self.assertEqual(err, "", "`--version` must not grow a footer")

    def test_footer_facts_prints_the_block_once(self):
        self._seed_cache()
        out, err = _run_main_streams(["footer-facts"])
        self.assertIn("mcptoon:", out)
        self.assertEqual(err, "", "the command already printed the block on stdout")

    def test_the_stdio_servers_are_never_stamped(self):
        """A stray write can desynchronise the JSON-RPC stream."""
        for command in ("serve", "demo-server"):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                cli._emit_footer(command)
            self.assertEqual(err.getvalue(), "", f"{command} must stay silent")

    def test_footer_off_silences_the_cli_tail(self):
        cfg.set_setting("footer", "off")
        self._seed_cache()
        _, err = _run_main_streams(["list"])
        self.assertEqual(err, "", "the off switch must reach the new surfaces too")

    def test_a_broken_footer_never_fails_the_command(self):
        with patch("mcptoon.footer.facts", side_effect=RuntimeError("boom")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                cli._emit_footer("list")  # must not raise
            self.assertEqual(err.getvalue(), "")

    # ─── MCP payload stamp ───

    def test_the_first_tool_result_is_stamped_exactly_once(self):
        """Once per session, not per call: the block costs ~32 tokens and a full
        catalog saves ~5,200, so stamping every call would break even at ~162."""
        self._seed_cache()
        bridge = self._bridge()
        payload = bridge._stamp_footer(self._payload())
        self.assertEqual(len(payload["content"]), 2)
        self.assertIn("mcptoon:", payload["content"][1]["text"])
        self.assertEqual(payload["content"][0]["text"], "upstream said hi",
                         "the upstream result itself must survive untouched")

        again = bridge._stamp_footer(self._payload())
        self.assertEqual(len(again["content"]), 1, "the second call must not restamp")

    def test_a_gateway_native_tool_is_stamped_too(self):
        """The gateway's own tools return before the proxy path, so they need their
        own stamp: an agent that only ever calls `mcptoon_manifest` would otherwise
        never see the line. Exercised through `_handle_call_tool` rather than
        `_stamp_footer`, because the wiring is exactly what is being pinned."""
        self._seed_cache()
        bridge = self._bridge()
        with patch.object(bridge, "_ensure_initialized", lambda: None):
            first = bridge._handle_call_tool({"name": "mcptoon_manifest", "arguments": {}})
            second = bridge._handle_call_tool({"name": "mcptoon_manifest", "arguments": {}})
        self.assertFalse(first["isError"])
        self.assertEqual(len(first["content"]), 2, "the native result must carry the line")
        self.assertIn("mcptoon:", first["content"][-1]["text"])
        self.assertEqual(len(second["content"]), 1, "still once per session")

    def test_an_error_result_is_not_stamped(self):
        """The model already has a failure to react to; a savings line is noise."""
        self._seed_cache()
        bridge = self._bridge()
        payload = {"content": [{"type": "text", "text": "boom"}], "isError": True}
        self.assertEqual(len(bridge._stamp_footer(payload)["content"]), 1)
        self.assertFalse(getattr(bridge, "_footer_stamped", False),
                         "an error must not burn the once-per-session stamp")

    def test_the_mcp_stamp_is_off_with_the_setting(self):
        cfg.set_setting("footer", "off")
        self._seed_cache()
        bridge = self._bridge()
        self.assertEqual(len(bridge._stamp_footer(self._payload())["content"]), 1)

    def test_the_mcp_stamp_survives_a_broken_footer(self):
        self._seed_cache()
        bridge = self._bridge()
        with patch("mcptoon.footer.block", side_effect=RuntimeError("boom")):
            self.assertEqual(len(bridge._stamp_footer(self._payload())["content"]), 1)

    def test_the_mcp_stamp_tolerates_a_payload_it_does_not_understand(self):
        """Never raise on an upstream shape we did not anticipate."""
        self._seed_cache()
        bridge = self._bridge()
        for payload in ({}, {"content": "not-a-list"}, {"content": None}):
            self.assertIs(bridge._stamp_footer(payload), payload)

    def test_every_surface_quotes_the_same_line(self):
        """One implementation behind four surfaces, so they cannot drift."""
        from mcptoon import footer as footer_mod

        self._seed_cache()
        # The first real command on a machine also introduces mcptoon once
        # (`_maybe_welcome`), so spend that on a throwaway run — otherwise stdout
        # carries the banner and this comparison is about the banner, not the line.
        _run_main_streams(["list"])
        reference = footer_mod.block()
        state = self.home / "footer-state.json"

        # `footer-facts` always prints: it is the explicit ask, not the ambient tail.
        out, _ = _run_main_streams(["footer-facts"])
        self.assertEqual(out.strip(), reference)

        # The two ambient surfaces suppress a repeat, so clear the memory first —
        # this test is about the *string* they print, not the change-gate (that has
        # its own tests below).
        state.unlink(missing_ok=True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cli._emit_footer("list")
        self.assertEqual(err.getvalue().strip(), reference)

        state.unlink(missing_ok=True)
        payload = self._bridge()._stamp_footer(self._payload())
        self.assertEqual(payload["content"][-1]["text"], reference)

    def test_a_repeated_line_is_suppressed(self):
        """The 2026-09-24 complaint: the same line every turn is not read, so the
        ambient tail must not recite it. Two identical calls, one line."""
        self._seed_cache()
        first = io.StringIO()
        with contextlib.redirect_stderr(first):
            cli._emit_footer("list")
        self.assertIn("mcptoon:", first.getvalue(), "the first line must appear")
        second = io.StringIO()
        with contextlib.redirect_stderr(second):
            cli._emit_footer("list")
        self.assertEqual(second.getvalue(), "", "an unchanged line must not repeat")

    def test_changed_compares_against_what_was_remembered(self):
        from mcptoon import footer as footer_mod

        self.assertTrue(footer_mod.changed("line A"), "the first ever line must show")
        footer_mod.remember("line A")
        self.assertFalse(footer_mod.changed("line A"))
        self.assertTrue(footer_mod.changed("line B"))

    def test_a_note_that_only_ticks_does_not_resurrect_the_line(self):
        """The `note:` carries a "catalog is N min old" age that ticks every minute.
        Comparing the whole block would resurface the same line every minute, so the
        change-gate judges the figures (the first line) only."""
        from mcptoon import footer as footer_mod

        footer_mod.remember("LINE\nnote: catalog is 1 min old (cache TTL 5 min)")
        self.assertFalse(footer_mod.changed(
            "LINE\nnote: catalog is 2 min old (cache TTL 5 min)"))


if __name__ == "__main__":
    unittest.main()
