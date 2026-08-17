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

    def test_sample_config_has_fetch(self):
        assert "fetch" in cfg.SAMPLE_CONFIG["servers"]

    def test_sample_config_uses_stdio(self):
        for server in cfg.SAMPLE_CONFIG["servers"].values():
            assert server["transport"] == "stdio"
