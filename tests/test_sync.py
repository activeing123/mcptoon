# Tests for mcptoon sync — config sync to AI agent formats
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mcptoon.sync import (
    _mcptoon_to_agent_format,
    _build_mcp_servers_dict,
    sync_to_agent,
    sync_to_all,
    detect_installed_agents,
    format_sync_report,
)


# ─── Config conversion tests ───

class TestConfigConversion:
    def test_stdio_server(self):
        """stdio server converts to agent format correctly."""
        cfg = {
            "transport": "stdio",
            "command": ["npx"],
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
            "env": {"API_KEY": "xxx"},
        }
        result = _mcptoon_to_agent_format("fetch", cfg)
        assert result["command"] == "npx"
        assert result["args"] == ["-y", "@modelcontextprotocol/server-fetch"]
        assert result["env"]["API_KEY"] == "xxx"

    def test_http_server(self):
        """HTTP server converts to agent format correctly."""
        cfg = {
            "transport": "http",
            "url": "http://localhost:8080/mcp",
            "headers": {"Authorization": "Bearer xxx"},
        }
        result = _mcptoon_to_agent_format("remote", cfg)
        assert result["url"] == "http://localhost:8080/mcp"
        assert result["headers"]["Authorization"] == "Bearer xxx"

    def test_stdio_multi_command(self):
        """stdio with multi-element command splits correctly."""
        cfg = {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@mcp/server-fetch"],
        }
        result = _mcptoon_to_agent_format("fetch", cfg)
        assert result["command"] == "npx"
        assert "-y" in result["args"]
        assert "@mcp/server-fetch" in result["args"]

    def test_empty_config(self):
        """Empty config returns empty dict."""
        result = _mcptoon_to_agent_format("empty", {})
        assert result == {} or len(result) == 0


class TestBuildMcpServersDict:
    def test_from_servers_key(self):
        """Config with 'servers' key parsed correctly."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = _build_mcp_servers_dict(config)
        assert "fetch" in result
        assert result["fetch"]["command"] == "npx"

    def test_empty_config(self):
        """Empty config produces empty dict."""
        result = _build_mcp_servers_dict({})
        assert result == {}


# ─── Sync to agent tests ───

class TestSyncToAgent:
    def test_sync_no_config(self):
        """No servers in config returns error."""
        result = sync_to_agent("cursor", dry_run=True, config={"servers": {}})
        assert result["servers_synced"] == 0
        assert result["error"] is not None

    def test_sync_unknown_agent(self):
        """Unknown agent ID returns error."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("nonexistent", dry_run=True, config=config)
        assert result["error"] == "Unknown agent: nonexistent"

    def test_sync_dry_run_cursor(self):
        """Dry run to cursor returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("cursor", dry_run=True, config=config)
        assert result["servers_synced"] == 1
        assert result["written"] is False
        assert result["error"] is None

    def test_sync_dry_run_claude_desktop(self):
        """Dry run to Claude Desktop returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("claude-desktop", dry_run=True, config=config)
        assert result["servers_synced"] == 1
        assert result["written"] is False

    def test_sync_dry_run_vscode_copilot(self):
        """Dry run to VS Code Copilot returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("vscode-copilot", dry_run=True, config=config)
        assert result["servers_synced"] == 1

    def test_sync_dry_run_codex(self):
        """Dry run to Codex returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("codex", dry_run=True, config=config)
        assert result["servers_synced"] == 1

    def test_sync_actual_write(self, tmp_path):
        """Test actual write to a temp file."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        with patch("mcptoon.sync._cursor_path", return_value=[tmp_path / "cursor.json"]):
            result = sync_to_agent("cursor", dry_run=False, config=config)
            assert result["written"] is True
            assert result["servers_synced"] == 1
            written = json.loads((tmp_path / "cursor.json").read_text())
            assert "mcpServers" in written
            assert "fetch" in written["mcpServers"]

    def test_sync_merge_existing(self, tmp_path):
        """Sync preserves existing servers not in mcptoon."""
        config_path = tmp_path / "cursor.json"
        existing = {"mcpServers": {"old-server": {"command": "echo", "args": ["hi"]}}}
        config_path.write_text(json.dumps(existing))
        config_path.parent.mkdir(exist_ok=True)

        config = {
            "servers": {
                "new-server": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/new"]},
            }
        }
        with patch("mcptoon.sync._cursor_path", return_value=[config_path]):
            result = sync_to_agent("cursor", dry_run=False, config=config)
            assert result["written"] is True
            written = json.loads(config_path.read_text())
            assert "old-server" in written["mcpServers"]
            assert "new-server" in written["mcpServers"]


class TestSyncToAll:
    def test_sync_all_dry_run(self):
        """Sync to all agents in dry-run mode."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        results = sync_to_all(dry_run=True, config=config)
        assert len(results) > 0
        for r in results:
            assert r["servers_synced"] == 1


class TestFormatReport:
    def test_report_format(self):
        """Report contains key info."""
        results = [
            {"agent": "cursor", "agent_name": "Cursor (global)", "path": "/tmp/x", "servers_synced": 2, "written": True, "error": None, "config_exists": True},
            {"agent": "claude-desktop", "agent_name": "Claude Desktop", "path": "/tmp/y", "servers_synced": 0, "written": False, "error": "not installed", "config_exists": False},
        ]
        report = format_sync_report(results, dry_run=False)
        assert "SYNC COMPLETE" in report
        assert "Cursor" in report
        assert "2" in report
