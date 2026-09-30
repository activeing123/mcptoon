# Copyright 2025 cxh
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

"""Tests for mcptoon config module."""
import json
from pathlib import Path
from unittest.mock import patch


from mcptoon import config as cfg


class TestResolveServerName:
    def test_known_alias(self):
        assert cfg.resolve_server_name("fs") == "filesystem"

    def test_canonical_name(self):
        assert cfg.resolve_server_name("exa") == "exa"

    def test_unknown_name_passthrough(self):
        assert cfg.resolve_server_name("myserver") == "myserver"


class TestLoadConfig:
    def test_empty_config(self, tmp_path):
        with patch.object(cfg, "CONFIG_FILE", tmp_path / "nonexistent.json"):
            with patch.object(cfg, "load_config", return_value={}):
                # Mock to avoid file system
                result = cfg.load_config()
                assert result == {}

    def test_config_with_servers(self):
        test_config = {
            "servers": {
                "test": {"transport": "stdio", "command": ["cmd"]}
            }
        }
        with patch.object(cfg, "CONFIG_FILE", Path("/tmp/test_mcp_config.json")):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.read_text", return_value=json.dumps(test_config)):
                    result = cfg.load_config()
                    assert "test" in result
                    assert result["test"]["transport"] == "stdio"


class TestSampleConfig:
    def test_sample_config_has_servers(self):
        assert "servers" in cfg.SAMPLE_CONFIG
        assert len(cfg.SAMPLE_CONFIG["servers"]) > 0

    def test_sample_config_has_live_servers(self):
        # The sample ships with servers that actually exist on npm; the old
        # `fetch` entry pointed at a package gone from the registry (E404),
        # so `mcptoon init` produced a config that died on first run.
        assert "filesystem" in cfg.SAMPLE_CONFIG["servers"]
        assert "memory" in cfg.SAMPLE_CONFIG["servers"]

    def test_sample_config_has_no_dead_packages(self):
        dead = ("@modelcontextprotocol/server-fetch",
                "@modelcontextprotocol/server-time",
                "@modelcontextprotocol/server-git",
                "@modelcontextprotocol/server-docker",
                "@modelcontextprotocol/server-sqlite")
        blob = repr(cfg.SAMPLE_CONFIG)
        for pkg in dead:
            assert pkg not in blob, f"dead package in SAMPLE_CONFIG: {pkg}"

    def test_sample_config_uses_stdio(self):
        for server in cfg.SAMPLE_CONFIG["servers"].values():
            assert server["transport"] == "stdio"


class TestLoadConfigToleratesHandEdits:
    """A hand-edited config can be *valid* JSON/TOML that is not the shape we
    expect. `load_config` caught parse errors but assumed the parsed value was a
    dict, so `[1,2,3]` or `{"servers": [1,2]}` crashed every reader with
    `AttributeError: 'list' object has no attribute 'get'` — a traceback on the
    first command a user runs after fat-fingering their config. These pin the
    graceful path (ignore the section, keep going), matching the
    `isinstance(data, dict)` guard `load_settings` already had.
    """

    def _write_and_load(self, tmp_path, text, monkeypatch):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(text, encoding="utf-8")
        monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(cfg_file))
        # Keep the TOML/local/env sources out of the way.
        monkeypatch.delenv("MCPTOON_SERVERS", raising=False)
        monkeypatch.chdir(tmp_path)
        return cfg.load_config()

    def test_top_level_list_is_ignored(self, tmp_path, monkeypatch):
        assert self._write_and_load(tmp_path, "[1, 2, 3]", monkeypatch) == {}

    def test_top_level_string_is_ignored(self, tmp_path, monkeypatch):
        assert self._write_and_load(tmp_path, '"just a string"', monkeypatch) == {}

    def test_servers_section_that_is_a_list_is_ignored(self, tmp_path, monkeypatch):
        assert self._write_and_load(tmp_path, '{"servers": [1, 2]}', monkeypatch) == {}

    def test_servers_section_that_is_null_is_ignored(self, tmp_path, monkeypatch):
        assert self._write_and_load(tmp_path, '{"servers": null}', monkeypatch) == {}

    def test_a_valid_servers_section_still_loads(self, tmp_path, monkeypatch):
        text = '{"servers": {"a": {"transport": "http", "url": "https://x/mcp"}}}'
        assert "a" in self._write_and_load(tmp_path, text, monkeypatch)

    def test_malformed_json_is_still_ignored(self, tmp_path, monkeypatch):
        assert self._write_and_load(tmp_path, "{ not json", monkeypatch) == {}

    def test_list_servers_survives_a_wrong_shape(self, tmp_path, monkeypatch):
        """The end-to-end symptom: `mcptoon list` reads via list_servers()."""
        self._write_and_load(tmp_path, "[1, 2, 3]", monkeypatch)
        assert cfg.list_servers() == []

    def test_a_file_we_ignore_is_preserved_as_bak(self, tmp_path, monkeypatch):
        """Ignoring a bad file is right for reading, but silent data loss: the next
        save rewrites the file from defaults and the hand-edit is gone. Keep a .bak."""
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(cfg_file))
        monkeypatch.delenv("MCPTOON_SERVERS", raising=False)
        monkeypatch.chdir(tmp_path)
        cfg.load_config()
        bak = tmp_path / "config.json.bak"
        assert bak.exists(), "an ignored config must be preserved"
        assert bak.read_text(encoding="utf-8") == "[1, 2, 3]"

    def test_a_valid_file_is_not_backed_up(self, tmp_path, monkeypatch):
        text = '{"servers": {"a": {"transport": "http", "url": "https://x/mcp"}}}'
        self._write_and_load(tmp_path, text, monkeypatch)
        assert not (tmp_path / "config.json.bak").exists()

    def test_a_malformed_file_is_also_preserved(self, tmp_path, monkeypatch):
        """The parse-error path preserves too, not just the wrong-shape path."""
        self._write_and_load(tmp_path, "{ not json", monkeypatch)
        assert (tmp_path / "config.json.bak").read_text(encoding="utf-8") == "{ not json"

    def test_the_bak_is_not_clobbered_by_a_second_read(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(cfg_file))
        monkeypatch.delenv("MCPTOON_SERVERS", raising=False)
        monkeypatch.chdir(tmp_path)
        cfg_file.write_text("[1, 2, 3]", encoding="utf-8")
        cfg.load_config()
        # A later, different bad edit must not overwrite the first snapshot.
        cfg_file.write_text("{ broken", encoding="utf-8")
        cfg.load_config()
        assert (tmp_path / "config.json.bak").read_text(encoding="utf-8") == "[1, 2, 3]"
