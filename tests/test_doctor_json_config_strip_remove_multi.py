# Copyright 2025-2026 activeing123
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

"""`doctor --json`, config key whitespace, `remove` multiple servers.

Reported 2026-10-18:
- `doctor --json` printed human text; CI could not parse diagnostics.
- `config get/set " footer "` failed because the key was lowercased but not
  stripped (get) / never stripped (set).
- `remove a b` removed only `a` and silently ignored `b`.
"""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import manifest as manifest_mod


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), \
            redirect_stdout(out), redirect_stderr(err):
        try:
            cli.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return out.getvalue(), err.getvalue(), code


# ── doctor --json ────────────────────────────────────────────────────────────

def _doctor_json(tmp_path, tools_by_server):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    servers = {name: {"transport": "stdio"} for name in tools_by_server}
    buf = io.StringIO()
    code = 0
    with patch.object(cfg, "CONFIG_FILE", config_file), \
         patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
         patch.object(cfg, "load_config", return_value=servers), \
         patch.object(cfg, "has_config_file", return_value=True), \
         patch.object(manifest_mod, "get_server_tools",
                      side_effect=lambda name, use_cache=True: tools_by_server[name]), \
         patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}), \
         redirect_stdout(buf):
        try:
            cli._cmd_doctor(["--json"], json_mode=True)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return json.loads(buf.getvalue()), code


def test_doctor_json_healthy(tmp_path):
    data, code = _doctor_json(tmp_path, {"good": [{"name": "a"}]})
    assert data["ok"] is True
    assert data["issues"] == 0
    assert any(c["name"] == "server:good" and c["status"] == "ok" for c in data["checks"])
    assert code == 0


def test_doctor_json_broken(tmp_path):
    data, code = _doctor_json(tmp_path, {"bad": [{"error": "RESPONSE_TIMEOUT: silent"}]})
    assert data["ok"] is False
    assert data["issues"] == 1
    assert data["broken"][0]["server"] == "bad"
    assert code == 1


# ── config key whitespace ────────────────────────────────────────────────────

def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.delenv("MCPTOON_SERVERS", raising=False)


def test_config_get_strips_whitespace(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    out, err, code = _run(["config", "get", "  footer  "])
    assert code == 0
    assert out.strip().endswith(("on", "off"))  # trailing value; a first-run banner may precede it


def test_config_set_strips_whitespace(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    out, err, code = _run(["config", "set", " footer ", "off"])
    assert code == 0
    assert cfg.get_setting("footer") == "off"


def test_config_unset_strips_whitespace(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    _run(["config", "set", "footer", "off"])
    out, err, code = _run(["config", "unset", " footer "])
    assert code == 0
    assert cfg.get_setting("footer") == cfg.SETTING_DEFAULTS["footer"]


# ── remove multiple servers ──────────────────────────────────────────────────

def test_remove_multiple_removes_all(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    cfg.add_server("a", {"transport": "stdio", "command": ["x"], "args": []})
    cfg.add_server("b", {"transport": "stdio", "command": ["y"], "args": []})
    out, err, code = _run(["remove", "a", "b"])
    assert code == 0
    assert "Removed server: a" in out and "Removed server: b" in out
    assert cfg.list_servers() == [] or set(cfg.list_servers()) == set()


def test_remove_missing_among_present_errors_but_removes_present(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    cfg.add_server("c", {"transport": "stdio", "command": ["z"], "args": []})
    out, err, code = _run(["remove", "c", "ghost"])
    assert code == 1
    assert "Removed server: c" in out
    assert "Server not found: ghost" in err
    assert "c" not in cfg.list_servers()
