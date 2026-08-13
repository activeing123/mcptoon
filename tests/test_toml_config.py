# -*- coding: utf-8 -*-
"""Tests for TOML config support."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcptoon.config import (
    _parse_toml,
    _toml_lite_parse,
    _dump_toml,
    _toml_array,
    _toml_parse_value,
    _split_array_items,
    load_config,
    save_config,
    CONFIG_FILE_TOML,
    CONFIG_FILE,
)


# ─── TOML parsing tests ───

class TestTomlParse:
    def test_simple_table(self):
        text = """
[servers.fetch]
transport = "stdio"
command = ["npx", "-y"]
args = ["@modelcontextprotocol/server-fetch"]
"""
        data = _parse_toml(text)
        assert "servers" in data
        assert "fetch" in data["servers"]
        assert data["servers"]["fetch"]["transport"] == "stdio"
        assert data["servers"]["fetch"]["command"] == ["npx", "-y"]
        assert data["servers"]["fetch"]["args"] == ["@modelcontextprotocol/server-fetch"]

    def test_nested_table(self):
        text = """
[servers.exa]
transport = "stdio"
command = ["npx", "-y"]
args = ["exa-mcp-server"]

[servers.exa.env]
EXA_API_KEY = "test-key"
"""
        data = _parse_toml(text)
        assert data["servers"]["exa"]["env"]["EXA_API_KEY"] == "test-key"

    def test_boolean_value(self):
        text = """
[servers.myserver]
transport = "stdio"
command = ["npx"]
enabled = true
cached = false
"""
        data = _parse_toml(text)
        assert data["servers"]["myserver"]["enabled"] is True
        assert data["servers"]["myserver"]["cached"] is False

    def test_empty_array(self):
        text = """
[servers.myserver]
transport = "stdio"
command = ["npx"]
args = []
"""
        data = _parse_toml(text)
        assert data["servers"]["myserver"]["args"] == []

    def test_comments_ignored(self):
        text = """
# This is a comment
[servers.fetch]  # inline comment
transport = "stdio"  # stdio transport
command = ["npx", "-y"]
"""
        data = _parse_toml(text)
        assert data["servers"]["fetch"]["transport"] == "stdio"

    def test_multiple_servers(self):
        text = """
[servers.fetch]
transport = "stdio"
command = ["npx", "-y"]
args = ["@modelcontextprotocol/server-fetch"]

[servers.github]
transport = "stdio"
command = ["npx", "-y"]
args = ["@modelcontextprotocol/server-github"]
"""
        data = _parse_toml(text)
        assert "fetch" in data["servers"]
        assert "github" in data["servers"]

    def test_http_server(self):
        text = """
[servers.http-endpoint]
transport = "http"
url = "http://localhost:8080/mcp"
"""
        data = _parse_toml(text)
        assert data["servers"]["http-endpoint"]["transport"] == "http"
        assert data["servers"]["http-endpoint"]["url"] == "http://localhost:8080/mcp"


# ─── TOML serialization tests ───

class TestTomlDump:
    def test_dump_stdio_server(self):
        servers = {
            "fetch": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-fetch"],
            }
        }
        text = _dump_toml(servers)
        assert "[servers.fetch]" in text
        assert 'transport = "stdio"' in text
        assert '["npx", "-y"]' in text

    def test_dump_http_server(self):
        servers = {
            "http-endpoint": {
                "transport": "http",
                "url": "http://localhost:8080/mcp",
            }
        }
        text = _dump_toml(servers)
        assert "[servers.http-endpoint]" in text
        assert 'url = "http://localhost:8080/mcp"' in text

    def test_dump_with_env(self):
        servers = {
            "exa": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["exa-mcp-server"],
                "env": {"EXA_API_KEY": "test-key"},
            }
        }
        text = _dump_toml(servers)
        assert "[servers.exa.env]" in text
        assert 'EXA_API_KEY = "test-key"' in text

    def test_dump_multiple_servers(self):
        servers = {
            "fetch": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-fetch"],
            },
            "github": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-github"],
            },
        }
        text = _dump_toml(servers)
        assert "[servers.fetch]" in text
        assert "[servers.github]" in text

    def test_round_trip(self):
        """Dump then parse should preserve data."""
        original = {
            "fetch": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-fetch"],
            },
            "http-endpoint": {
                "transport": "http",
                "url": "http://localhost:8080/mcp",
            },
        }
        text = _dump_toml(original)
        parsed = _parse_toml(text)
        assert parsed["servers"]["fetch"]["transport"] == "stdio"
        assert parsed["servers"]["fetch"]["command"] == ["npx", "-y"]
        assert parsed["servers"]["fetch"]["args"] == ["@modelcontextprotocol/server-fetch"]
        assert parsed["servers"]["http-endpoint"]["transport"] == "http"
        assert parsed["servers"]["http-endpoint"]["url"] == "http://localhost:8080/mcp"


# ─── TOML helper tests ───

class TestTomlHelpers:
    def test_toml_array_strings(self):
        result = _toml_array(["npx", "-y"])
        assert result == '["npx", "-y"]'

    def test_toml_array_empty(self):
        result = _toml_array([])
        assert result == "[]"

    def test_toml_array_mixed(self):
        result = _toml_array(["npx", 42, True])
        assert "npx" in result
        assert "42" in result
        assert "true" in result

    def test_split_array_simple(self):
        parts = _split_array_items('"a", "b", "c"')
        assert len(parts) == 3

    def test_split_array_with_comma_in_string(self):
        parts = _split_array_items('"a,b", "c"')
        assert len(parts) == 2

    def test_parse_value_string(self):
        assert _toml_parse_value('"hello"') == "hello"

    def test_parse_value_bool(self):
        assert _toml_parse_value("true") is True
        assert _toml_parse_value("false") is False

    def test_parse_value_int(self):
        assert _toml_parse_value("42") == 42

    def test_parse_value_array(self):
        result = _toml_parse_value('["a", "b"]')
        assert result == ["a", "b"]

    def test_parse_value_empty_array(self):
        assert _toml_parse_value("[]") == []


# ─── Integration: load_config with TOML ───

class TestLoadConfigTOML:
    def test_load_toml_config(self, tmp_path):
        """load_config should read TOML config files."""
        toml_content = """
[servers.fetch]
transport = "stdio"
command = ["npx", "-y"]
args = ["@modelcontextprotocol/server-fetch"]
"""
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content, encoding="utf-8")

        with patch("mcptoon.config.CONFIG_FILE_TOML", toml_file):
            with patch("mcptoon.config.CONFIG_FILE", tmp_path / "nonexistent.json"):
                servers = load_config()
                assert "fetch" in servers
                assert servers["fetch"]["transport"] == "stdio"
                assert servers["fetch"]["command"] == ["npx", "-y"]

    def test_toml_overrides_json(self, tmp_path):
        """TOML config should be loaded alongside JSON."""
        json_content = json.dumps({
            "servers": {
                "fetch": {
                    "transport": "stdio",
                    "command": ["npx", "-y"],
                    "args": ["old-package"],
                }
            }
        })
        toml_content = """
[servers.github]
transport = "stdio"
command = ["npx", "-y"]
args = ["@modelcontextprotocol/server-github"]
"""
        json_file = tmp_path / "config.json"
        json_file.write_text(json_content, encoding="utf-8")
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(toml_content, encoding="utf-8")

        with patch("mcptoon.config.CONFIG_FILE_TOML", toml_file):
            with patch("mcptoon.config.CONFIG_FILE", json_file):
                servers = load_config()
                # Both should be present
                assert "fetch" in servers
                assert "github" in servers


# ─── Integration: save_config with TOML ───

class TestSaveConfigTOML:
    def test_save_as_toml(self, tmp_path):
        """save_config with fmt='toml' should write TOML format."""
        toml_file = tmp_path / "config.toml"
        servers = {
            "fetch": {
                "transport": "stdio",
                "command": ["npx", "-y"],
                "args": ["@modelcontextprotocol/server-fetch"],
            }
        }
        with patch("mcptoon.config.CONFIG_FILE_TOML", toml_file):
            with patch("mcptoon.config.CONFIG_FILE", tmp_path / "nonexistent.json"):
                save_config(servers, fmt="toml")
                assert toml_file.exists()
                content = toml_file.read_text(encoding="utf-8")
                assert "[servers.fetch]" in content
                assert 'transport = "stdio"' in content

    def test_save_as_json_default(self, tmp_path):
        """save_config without fmt should default to JSON."""
        json_file = tmp_path / "config.json"
        servers = {"fetch": {"transport": "stdio", "command": ["npx"]}}
        with patch("mcptoon.config.CONFIG_FILE", json_file):
            with patch("mcptoon.config.CONFIG_FILE_TOML", tmp_path / "nonexistent.toml"):
                save_config(servers)
                assert json_file.exists()
                data = json.loads(json_file.read_text(encoding="utf-8"))
                assert "fetch" in data["servers"]
