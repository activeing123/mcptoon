"""`mcptoon add --http` must reject a value that cannot be an MCP endpoint.

It used to accept any string — `javascript:alert(1)`, `ftp://x`, `not a url`, or a
host-less `http://` — and write it to config, so the mistake surfaced later as a
confusing connection error instead of at the keyboard. The check is deliberately
narrow (wrong scheme / no host only): a typo in the path, or an unusual-but-real
host, still passes, because rejecting those would block a command that would work.
"""
from __future__ import annotations

import pytest

from mcptoon import cli, config as cfg


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))


@pytest.mark.parametrize("url", [
    "not a url", "javascript:alert(1)", "ftp://x", "file:///etc/passwd",
    "http://", "https://", "", "  ",
])
def test_add_http_rejects_an_unusable_url(url, capsys):
    with pytest.raises(SystemExit) as exc:
        cli._cmd_add(["s1", "--http", url])
    assert exc.value.code == 1
    assert "--http" in capsys.readouterr().out
    assert "s1" not in cfg.list_servers(), "a rejected URL must not be written"


@pytest.mark.parametrize("url", [
    "https://ok.example/mcp", "http://localhost:3000/mcp",
    "https://api.example.com/mcp/v1", "https://127.0.0.1:8080",
])
def test_add_http_accepts_a_usable_url(url, capsys):
    cli._cmd_add(["s1", "--http", url])  # must not raise
    assert cfg.list_servers() == ["s1"]
    assert cfg.load_config()["s1"]["url"] == url


def test_the_reason_names_the_scheme():
    assert "javascript" in cli._http_url_problem("javascript:alert(1)")
    assert "host" in cli._http_url_problem("http://")
    assert cli._http_url_problem("https://ok.example/mcp") == ""


def test_add_stdio_is_unaffected(capsys):
    cli._cmd_add(["s2", "--stdio", "npx", "-y", "some-server"])
    assert cfg.load_config()["s2"]["transport"] == "stdio"
