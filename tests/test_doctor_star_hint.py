# Tests for the doctor star hint (Call-To-Action) — issue-discipline:
# shown at most once per machine, only on fully healthy runs, never in CI.
import contextlib
import io
import json
import os
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon.cli import _cmd_doctor

STAR_URL = "https://github.com/activeing123/mcptoon"


def _run_doctor(tmp_path, extra_env=None):
    """Run _cmd_doctor with an isolated config/cache dir; return stdout."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    env = {"MCPTOON_NO_STAR_HINT": "", "CI": ""}
    env.update(extra_env or {})
    buf = io.StringIO()
    with patch.object(cfg, "CONFIG_FILE", config_file), \
         patch.object(cfg, "CACHE_DIR", cache_dir), \
         patch.dict(os.environ, env), \
         contextlib.redirect_stdout(buf):
        _cmd_doctor([])
    return buf.getvalue()


class TestDoctorStarHint:
    def test_shown_on_healthy_run(self, tmp_path):
        out = _run_doctor(tmp_path)
        assert "All good!" in out
        assert "Found this useful?" in out
        assert STAR_URL in out

    def test_shown_only_once_per_machine(self, tmp_path):
        first = _run_doctor(tmp_path)
        assert "Found this useful?" in first
        second = _run_doctor(tmp_path)
        assert "All good!" in second
        assert "Found this useful?" not in second

    def test_never_in_ci(self, tmp_path):
        out = _run_doctor(tmp_path, extra_env={"CI": "1"})
        assert "All good!" in out
        assert "Found this useful?" not in out

    def test_kill_switch_env(self, tmp_path):
        out = _run_doctor(tmp_path, extra_env={"MCPTOON_NO_STAR_HINT": "1"})
        assert "All good!" in out
        assert "Found this useful?" not in out

    def test_not_shown_when_issues_found(self, tmp_path):
        # No config file → doctor exits with issues before the hint point.
        missing = tmp_path / "missing.json"
        cache_dir = tmp_path / "cache"
        buf = io.StringIO()
        with patch.object(cfg, "CONFIG_FILE", missing), \
             patch.object(cfg, "CACHE_DIR", cache_dir), \
             patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "", "CI": ""}), \
             contextlib.redirect_stdout(buf):
            _cmd_doctor([])
        out = buf.getvalue()
        assert "issue(s)" in out
        assert "Found this useful?" not in out


class TestDoctorReportsAServerThatCannotStart:
    """A server that never answered is an issue, not "may be empty" (2026-10-02).

    `manifest.get_server_tools` used to swallow a failed start into `[]`, the same
    value a genuinely empty server returns, so `doctor` printed
    `! dead  [stdio] 0 tools (server may be empty)`, left the issue count at zero
    and finished with "All good!" on a machine whose server binary did not exist.
    """

    def _config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps({"servers": {"dead": {"transport": "stdio",
                                             "command": "no-such-binary-xyz"}}}),
            encoding="utf-8")
        return config_file

    def test_a_server_that_cannot_start_counts_as_an_issue(self, tmp_path):
        buf = io.StringIO()
        with patch.object(cfg, "CONFIG_FILE", self._config(tmp_path)), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
             patch.object(cli.manifest_mod, "get_server_tools",
                          return_value=[{"error": "[WinError 2] not found"}]), \
             patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1"}), \
             contextlib.redirect_stdout(buf):
            _cmd_doctor([])
        out = buf.getvalue()
        assert "cannot start" in out
        assert "0 tools (server may be empty)" not in out
        assert "1 issue(s)" in out
        assert "All good!" not in out

    def test_a_genuinely_empty_server_is_not_an_issue(self, tmp_path):
        """A server that answered and exposes no tools is not a failure."""
        buf = io.StringIO()
        with patch.object(cfg, "CONFIG_FILE", self._config(tmp_path)), \
             patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
             patch.object(cli.manifest_mod, "get_server_tools", return_value=[]), \
             patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1"}), \
             contextlib.redirect_stdout(buf):
            _cmd_doctor([])
        out = buf.getvalue()
        assert "started but exposes none" in out
        assert "0 issue(s)" in out
