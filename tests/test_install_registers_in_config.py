"""Issue #36 — `mcptoon install` must make the server reachable, not just record it.

Reported: `install` answered ``{"status": "installed", …}``, but the server did not
appear in `mcptoon list` and `mcptoon call <server> …` answered UNKNOWN_SERVER. The
command wrote only a generated handler module into the state dir plus a record in
``~/.mcp-cli/pro_installed.json``. Nothing ever imported the module — the package
contains no loader — so ``router._HANDLERS`` stayed empty, and the **config**, which
is the only store `list`/`call` read, was never touched.

These drive the real install path against a stubbed MCP handshake and assert on the
config file itself, plus the properties that follow from it: `install --remove` takes
the config entry back out, a stdio install never writes env values to disk, and no
Python module is generated any more.
"""
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mcptoon import cli, config as cfg, installer


class _FakeClient:
    """Stands in for the MCP handshake; records how it was constructed."""

    last_kwargs = None

    def __init__(self, **kw):
        _FakeClient.last_kwargs = kw
        self.kw = kw

    def initialize(self):
        return {"serverInfo": {"name": "fake"}}

    def list_tools(self):
        return [{"name": "ping", "description": "p",
                 "inputSchema": {"type": "object", "properties": {}}}]

    def close(self):
        pass


class _Sandbox:
    """A temp dir wired into every path these tests touch."""

    def __init__(self, tmp_path):
        self.tmp = Path(tmp_path)
        self.config_file = self.tmp / "config.json"
        self.installed_file = self.tmp / "pro_installed.json"
        self.handlers = self.tmp / "handlers"

    def env(self):
        return {
            "MCPTOON_CONFIG_FILE": str(self.config_file),
            "MCPTOON_CONFIG_FILE_TOML": str(self.tmp / "config.toml"),
            "MCPTOON_HANDLERS_DIR": str(self.handlers),
        }

    def servers(self):
        raw = self.config_file.read_text(encoding="utf-8")
        return json.loads(raw)["servers"]


def _install_http(box, name="svc", url="https://example.com/mcp", headers=None):
    with patch.dict(os.environ, box.env()), \
            patch.object(installer, "_INSTALLED_FILE", str(box.installed_file)), \
            patch.object(installer, "MCPClient", _FakeClient):
        return installer.install_http(url, name, headers=headers or {})


def _install_stdio(box, name="svc", env=None, command="npx", args=("-y", "pkg")):
    with patch.dict(os.environ, box.env()), \
            patch.object(installer, "_INSTALLED_FILE", str(box.installed_file)), \
            patch.object(installer, "MCPClient", _FakeClient):
        return installer.install_custom(name, command, list(args), env or {})


# ── the fix: the server reaches the config ──

def test_http_install_registers_the_server_in_config(tmp_path):
    box = _Sandbox(tmp_path)
    result = _install_http(box)
    assert result["status"] == "installed"
    assert box.servers()["svc"] == {"transport": "http",
                                    "url": "https://example.com/mcp"}


def test_stdio_install_registers_the_server_in_config(tmp_path):
    box = _Sandbox(tmp_path)
    result = _install_stdio(box)
    assert result["status"] == "installed"
    assert box.servers()["svc"] == {"transport": "stdio",
                                    "command": ["npx"],
                                    "args": ["-y", "pkg"]}


def test_the_registered_transport_is_one_the_reader_accepts(tmp_path):
    """`install_http` defaults to transport="auto", but the config reader knows only
    "stdio" and "http" and raises BAD_CONFIG otherwise, so writing "auto" through
    would have produced a server that lists and then refuses to start."""
    box = _Sandbox(tmp_path)
    _install_http(box)
    with patch.dict(os.environ, box.env()):
        server_cfg = cfg.get_server_config("svc")
        # This is the reader's own code path, not a string comparison.
        from mcptoon.client import MCPClientPool
        pool = MCPClientPool.__new__(MCPClientPool)
        client = pool._make_client(server_cfg)
    client.close()


def test_install_headers_are_persisted_as_templates(tmp_path):
    box = _Sandbox(tmp_path)
    _install_http(box, headers={"Authorization": "Bearer ${TOK}"})
    assert box.servers()["svc"]["headers"] == {"Authorization": "Bearer ${TOK}"}


def test_reinstalling_the_same_name_reports_that_it_replaced_one(tmp_path):
    box = _Sandbox(tmp_path)
    assert _install_http(box)["replaced_existing"] is False
    assert _install_http(box)["replaced_existing"] is True


# ── the properties that follow ──

def test_the_installed_server_now_appears_in_mcptoon_list(tmp_path):
    box = _Sandbox(tmp_path)
    _install_http(box, name="exa")
    out, err = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, box.env()), \
            patch.object(sys, "argv", ["mcptoon", "list"]):
        try:
            with redirect_stdout(out), redirect_stderr(err):
                cli.main()
        except SystemExit:
            pass
    assert "exa" in out.getvalue(), (
        f"list did not show it:\n{out.getvalue()}\n{err.getvalue()}")


def test_remove_takes_the_config_entry_back_out(tmp_path):
    box = _Sandbox(tmp_path)
    _install_http(box)
    with patch.dict(os.environ, box.env()), \
            patch.object(installer, "_INSTALLED_FILE", str(box.installed_file)):
        result = installer.remove_installed("svc")
    assert result["status"] == "removed"
    assert result["config_removed"] is True
    assert "svc" not in box.servers()


def test_a_stdio_install_never_writes_env_values_to_disk(tmp_path):
    """The child inherits this process's environment, which is where the generated
    handler used to read values from too — so nothing needs to be persisted, and a
    registry-supplied credential must not land in the config."""
    box = _Sandbox(tmp_path)
    _install_stdio(box, env={"API_KEY": "sekret-value"})
    raw = box.config_file.read_text(encoding="utf-8")
    assert "sekret-value" not in raw
    assert "env" not in box.servers()["svc"]


def test_install_no_longer_generates_a_python_module(tmp_path):
    """The dead half of the old design: a module nothing imported."""
    box = _Sandbox(tmp_path)
    _install_http(box)
    _install_stdio(box, name="other")
    assert list(box.handlers.glob("*.py")) == []
    assert not box.handlers.exists()
