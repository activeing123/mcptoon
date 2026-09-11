# Tests for the doctor star hint (Call-To-Action) — issue-discipline:
# shown at most once per machine, only on fully healthy runs, never in CI.
import contextlib
import io
import os
from unittest.mock import patch

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
