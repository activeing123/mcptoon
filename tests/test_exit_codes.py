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


# ─── config set: a bad value must not be stored ───
#
# `welcome` was validated nowhere (the CLI hand-checked footer and lang only), so
# `config set welcome maybe` stored "maybe" and exited 0 — and `welcome_enabled`
# treats anything not in ("off","0","false","no") as *on*, so the user's "off"
# typo left the banner showing. Pin the refusal and the exit code for both
# boolean switches.

@pytest.mark.parametrize("key", ["welcome", "footer"])
@pytest.mark.parametrize("bad", ["maybe", "true", "1", "bogus"])
def test_config_set_rejects_a_non_boolean_value(key, bad, capsys):
    with pytest.raises(SystemExit) as exc:
        cli._cmd_config(["set", key, bad], "auto")
    assert exc.value.code == 1
    assert key in capsys.readouterr().out
    assert cfg.get_setting(key) == cfg.SETTING_DEFAULTS[key], \
        f"a rejected value must not be persisted for {key}"


@pytest.mark.parametrize("key", ["welcome", "footer"])
@pytest.mark.parametrize("good", ["on", "off"])
def test_config_set_accepts_both_boolean_values(key, good):
    cli._cmd_config(["set", key, good], "auto")  # must not raise
    assert cfg.get_setting(key) == good


def test_config_set_unknown_value_message_names_the_choices(capsys):
    with pytest.raises(SystemExit):
        cli._cmd_config(["set", "welcome", "maybe"], "auto")
    assert "not one of" in capsys.readouterr().out


def test_welcome_off_via_cli_actually_disables(capsys):
    """The end-to-end point of the fix: `set welcome off` must make
    `welcome_enabled()` false, so the banner is really suppressed."""
    cli._cmd_config(["set", "welcome", "off"], "auto")
    assert cfg.welcome_enabled() is False


# ─── runners: the uvx opt-out must be a real, validated switch ───

def test_config_set_rejects_an_unknown_runner_mode(capsys):
    with pytest.raises(SystemExit) as exc:
        cli._cmd_config(["set", "runners", "always"], "auto")
    assert exc.value.code == 1
    assert "not one of" in capsys.readouterr().out
    assert cfg.get_setting("runners") == cfg.SETTING_DEFAULTS["runners"]


@pytest.mark.parametrize("mode", ["prefer-installed", "allow-fetch"])
def test_config_set_accepts_both_runner_modes(mode):
    cli._cmd_config(["set", "runners", mode], "auto")
    assert cfg.get_setting("runners") == mode


def test_runners_default_is_prefer_installed():
    assert cfg.get_setting("runners") == "prefer-installed"
    assert cfg.prefer_installed_runners() is True


def test_runners_allow_fetch_flips_the_gate():
    cli._cmd_config(["set", "runners", "allow-fetch"], "auto")
    assert cfg.prefer_installed_runners() is False
