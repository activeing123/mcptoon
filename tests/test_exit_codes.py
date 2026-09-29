"""Exit codes for "the target does not exist" must be non-zero.

A miss that exits 0 is worse than a crash for a script: `mcptoon remove foo &&
echo removed` prints "removed" when nothing was removed, and a CI step that pins
a setting on a mistyped key goes green while doing nothing. The suite already
pins this for `skills remove` (tests/test_skills.py) and `config set`; this file
covers the two paths that were still returning 0.

`policy set <unknown-server>` is deliberately NOT pinned here: mcptoon accepts
policies for servers it has not configured yet (see
tests/test_policy_overrides.py::TestPolicyCLI::test_set_list_clear_flow, which
sets a policy with no config at all), so a miss there is by design, not an error.
"""
from __future__ import annotations

import pytest

from mcptoon import cli, config as cfg


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Point every config file at the tmp dir so nothing touches ~/.mcptoon."""
    monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("MCPTOON_COMPRESSION_FILE", str(tmp_path / "compression.json"))


# ─── remove ───

def test_remove_unknown_server_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli._cmd_remove(["ghost"])
    assert exc.value.code == 1
    assert "Server not found: ghost" in capsys.readouterr().out


def test_remove_without_a_name_still_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        cli._cmd_remove([])
    assert exc.value.code == 1


def test_remove_known_server_succeeds_without_exiting(capsys):
    cfg.add_server("exa", {"transport": "http", "url": "https://example.com/mcp"})
    cli._cmd_remove(["exa"])  # must not raise
    assert "Removed server: exa" in capsys.readouterr().out


# ─── config get ───

def test_config_get_unknown_key_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli._cmd_config(["get", "nosuchkey"], "auto")
    assert exc.value.code == 1
    assert "Unknown setting: nosuchkey" in capsys.readouterr().out


def test_config_get_without_a_key_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        cli._cmd_config(["get"], "auto")
    assert exc.value.code == 1


def test_config_get_known_key_prints_and_does_not_exit(capsys):
    cli._cmd_config(["get", "footer"], "auto")  # must not raise
    assert capsys.readouterr().out.strip(), "a known key must print its value"
