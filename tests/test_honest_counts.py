"""Defect fixes from the 2026-10-02 sweep, before 0.8.8.

Each test here pins a case where mcptoon printed a number or a claim that was
false on a machine it had not been tried on. Most share a single root cause:
**a failed server (or a failed write) was treated as a success**, so counts and
diagnostics read "fine" while something was broken.

Reproduced on a simulated clean box (fresh `USERPROFILE`, no agent installed,
one working server + one whose binary is absent).
"""
import contextlib
import io
import json
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import discover as discover_mod
from mcptoon import manifest as manifest_mod
from mcptoon import sync as sync_mod


# ─── the payoff line must not count a server that never started ───

class TestCelebrationNamesUnreachableServers:
    def _celebration(self, tool_count, servers, unreachable):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._quickstart_celebration(tool_count, servers, unreachable)
        return buf.getvalue()

    def test_a_dead_server_is_not_counted_as_ready(self):
        """The reproduction: 1 working server + 1 dead one said "across 2 servers"."""
        out = self._celebration(11, 2, 1)
        assert "11 tools ready across 1 server (1 could not start)" in out
        assert "across 2 servers" not in out

    def test_no_tail_when_everything_started(self):
        out = self._celebration(37, 5, 0)
        assert "37 tools ready across 5 servers!" in out
        assert "could not start" not in out

    def test_unreachable_count_only_counts_all_error_servers(self):
        assert cli._manifest_unreachable_count(
            {"dead": [{"error": "boom"}], "good": [{"name": "x"}]}) == 1
        # A server that answered with one good and one bad tool is reachable.
        assert cli._manifest_unreachable_count(
            {"partial": [{"name": "x"}, {"error": "one tool blew up"}]}) == 0
        assert cli._manifest_unreachable_count({}) == 0
        assert cli._manifest_unreachable_count(None) == 0
        assert cli._manifest_unreachable_count("x") == 0


# ─── a failed start must not be indistinguishable from an empty server ───

class TestGetServerToolsReportsFailure:
    """`get_server_tools` must return an error entry, not `[]`, on a failed start.

    `[]` means "the server answered and exposes no tools". Returning it for a
    server that never started is what let `doctor` say "0 tools (server may be
    empty)" and then "All good!".
    """

    def test_a_failed_start_returns_an_error_entry(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"servers": {"dead": {"transport": "stdio",
                                             "command": "no-such-binary-xyz"}}}),
            encoding="utf-8")
        with patch.object(cfg, "CONFIG_FILE", config_file), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
             patch.object(manifest_mod, "MCPClientPool") as pool:
            pool.return_value.list_tools.side_effect = RuntimeError("cannot spawn")
            tools = manifest_mod.get_server_tools("dead", use_cache=False)

        assert tools and "error" in tools[0], (
            "a failed start must be reported, not hidden as an empty server")
        assert "cannot spawn" in tools[0]["error"]

    def test_an_unknown_server_is_still_empty(self, tmp_path):
        """A name that is not configured is not a failure — it is simply not there."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"servers": {}}), encoding="utf-8")
        with patch.object(cfg, "CONFIG_FILE", config_file), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"):
            assert manifest_mod.get_server_tools("nope", use_cache=False) == []


# ─── quickstart must not deny servers it manages ───

class TestQuickstartOnAMachineThatAlreadyHasServers:
    def _run(self, tmp_path, configured):
        from mcptoon import discover

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"servers": configured}), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(cfg, "CONFIG_FILE", config_file), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
             patch.object(discover, "auto_discover",
                          return_value=discover.DiscoveryResult()), \
             contextlib.redirect_stdout(buf):
            try:
                cli._cmd_quickstart([], "auto")
            except SystemExit:
                pass
        return buf.getvalue()

    def test_it_says_you_already_have_servers(self, tmp_path):
        """Re-running quickstart used to say "No MCP servers found on this machine"
        while `mcptoon list` printed them — discovery reads other agents' configs,
        never mcptoon's own."""
        out = self._run(tmp_path, {"demo": {"transport": "stdio", "command": "x"}})
        assert "already have 1 server configured" in out
        assert "No MCP servers found on this machine" not in out

    def test_it_still_says_none_when_there_are_none(self, tmp_path):
        out = self._run(tmp_path, {})
        assert "No MCP servers found on this machine" in out


# ─── a config in TOML is still a config ───
#
# `load_config()` reads both `config.toml` and `config.json`, but three callers
# gated on `CONFIG_FILE.exists()` — the JSON path alone. On a machine whose
# servers live in TOML that made `quickstart`/`init --auto` take the "no config
# yet" branch and `save_config()` rewrite the TOML file with *only* the new
# servers (the user's list gone, no `.bak`), and made `doctor` say "No config
# found" on a machine that had one (reproduced 2026-10-02).

class TestATomlConfigIsStillAConfig:
    def _patch(self, tmp_path, toml_text):
        json_file = tmp_path / "config.json"
        toml_file = tmp_path / "config.toml"
        if toml_text is not None:
            toml_file.write_text(toml_text, encoding="utf-8")
        return (
            patch.object(cfg, "CONFIG_FILE", json_file),
            patch.object(cfg, "CONFIG_FILE_TOML", toml_file),
            patch.object(cfg, "CACHE_DIR", tmp_path / "cache"),
            json_file,
            toml_file,
        )

    def test_has_config_file_sees_a_toml_config(self, tmp_path):
        p_json, p_toml, p_cache, _, toml_file = self._patch(
            tmp_path, '[servers.mine]\ntransport = "stdio"\ncommand = ["my-server"]\n')
        with p_json, p_toml, p_cache:
            assert cfg.has_config_file() is True

    def test_has_config_file_is_false_with_neither(self, tmp_path):
        p_json, p_toml, p_cache, _, _ = self._patch(tmp_path, None)
        with p_json, p_toml, p_cache:
            assert cfg.has_config_file() is False

    def test_quickstart_does_not_delete_a_toml_config(self, tmp_path):
        """The reproduction: a TOML-only config must not be rewritten to hold only
        the discovered servers."""
        p_json, p_toml, p_cache, _, toml_file = self._patch(
            tmp_path, '[servers.mine]\ntransport = "stdio"\ncommand = ["my-server"]\n')
        buf = io.StringIO()
        with p_json, p_toml, p_cache, \
             patch.object(discover_mod, "auto_discover",
                          return_value=discover_mod.DiscoveryResult()), \
             contextlib.redirect_stdout(buf):
            try:
                cli._cmd_quickstart([], "auto")
            except SystemExit:
                pass
        assert "mine" in toml_file.read_text(encoding="utf-8"), (
            "quickstart wiped a server that lived in config.toml")

    def test_doctor_sees_a_toml_config(self, tmp_path):
        p_json, p_toml, p_cache, _, _ = self._patch(
            tmp_path, '[servers.mine]\ntransport = "stdio"\ncommand = ["my-server"]\n')
        buf = io.StringIO()
        with p_json, p_toml, p_cache, \
             patch.object(cli.manifest_mod, "get_server_tools", return_value=[]), \
             patch.dict(__import__("os").environ, {"MCPTOON_NO_STAR_HINT": "1"}), \
             contextlib.redirect_stdout(buf):
            cli._cmd_doctor([])
        out = buf.getvalue()
        assert "No config found" not in out
        assert "1 servers" in out or "(1 servers)" in out


# ─── a failed write must not be reported as a removal ───

class TestOffDoesNotClaimAFailedWrite:
    """`removed` means "the gateway entry was found", not "it is gone"."""

    _FAKE = [{"agent": "cursor", "agent_name": "Cursor", "path": "C:\\c.json",
              "removed": True, "written": False, "error": "Write failed"}]

    def _run(self, fmt):
        buf = io.StringIO()
        with patch.object(sync_mod, "remove_gateway_from_all", return_value=self._FAKE), \
             contextlib.redirect_stdout(buf):
            cli._cmd_off([], fmt)
        return buf.getvalue()

    def test_text_names_the_agent_that_still_has_the_entry(self):
        out = self._run("auto")
        assert "STILL there" in out
        assert "0 agent(s) no longer see mcptoon" in out
        assert "1 agent(s) no longer see mcptoon." not in out

    def test_json_counts_it_as_failed_not_removed(self):
        data = json.loads(self._run("json"))
        assert data["count"] == 0
        assert data["removed_from"] == []
        assert data["failed"][0]["agent"] == "cursor"


class TestRestoreCountsAgreeBetweenFormats:
    """`--json` counted `restored`; the text form counted `restored and written`.
    A host with restored=True, written=False got two different answers."""

    _FAKE = [{"agent": "cursor", "agent_name": "Cursor", "path": "C:\\c.json",
              "restored": True, "written": False,
              "error": "config unreadable; left unchanged"}]

    def test_json_matches_the_text_form(self):
        buf = io.StringIO()
        with patch.object(sync_mod, "restore_all_from_backup", return_value=self._FAKE), \
             patch.object(sync_mod, "restore_plan",
                          return_value=[{"agent_name": "Cursor", "path": "x"}]), \
             contextlib.redirect_stdout(buf):
            cli._cmd_restore(["--yes"], "json")
        data = json.loads(buf.getvalue())
        assert data["count"] == 0, "a host that was not written must not count as restored"
        assert data["failed"][0]["agent"] == "cursor"


# ─── an unreachable endpoint is not a discovered server ───

class TestDiscoverHttpDoesNotCountADeadEndpoint:
    def test_a_dead_url_is_not_counted(self, capsys, tmp_path):
        with patch.object(cfg, "CONFIG_FILE", tmp_path / "config.json"), \
             patch.object(cfg, "CONFIG_FILE_TOML", tmp_path / "config.toml"), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
             patch.object(discover_mod, "probe_http_endpoint", return_value=None), \
             patch.object(discover_mod, "auto_discover",
                          return_value=discover_mod.DiscoveryResult()):
            cli._cmd_auto_discover(["--http", "http://127.0.0.1:9",
                                    "--no-configs", "--no-env", "--no-local"], "auto")
        out = capsys.readouterr().out
        assert "did not answer an MCP initialize" in out
        assert "http-endpoint:" not in out


# ─── a reachable endpoint whose tool list failed is not "0 tools" ───

class TestProbeHttpReportsUnreadableToolList:
    def test_tools_count_is_none_when_the_list_cannot_be_read(self):
        """`alive: True, tools_count: 0` used to mean both "zero tools" and "the
        tool list failed"; the second is now explicit."""
        import mcptoon.discover as d
        with patch.object(d, "_probe_endpoint", return_value=True), \
             patch.object(d.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = RuntimeError("TLS error")
            info = d.probe_http_endpoint("http://example.invalid/mcp", timeout=0.1)
        assert info is not None and info["alive"] is True
        assert info["tools_count"] is None
        assert info["tools_known"] is False
