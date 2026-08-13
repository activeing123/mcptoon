# -*- coding: utf-8 -*-
"""Tests for mcptoon discover — auto-discovery module."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mcptoon.discover import (
    DiscoveryResult,
    auto_discover,
    _scan_claude_desktop,
    _scan_cursor,
    _detect_from_env,
    _detect_local_tools,
    _probe_http_mcp,
    _probe_endpoint,
    _match_profiles,
    _normalize_imported_config,
    _which,
    probe_http_endpoint,
    make_http_config,
)


# ═══════════════════════════════════════════════════════════════
# DiscoveryResult tests
# ═══════════════════════════════════════════════════════════════

class TestDiscoveryResult:
    def test_empty_result(self):
        r = DiscoveryResult()
        assert r.count == 0
        assert "Discovered 0" in r.summary()

    def test_with_servers(self):
        r = DiscoveryResult()
        r.servers = {"github": {"transport": "stdio"}}
        r.sources = {"github": ["env"]}
        r.reasons = {"github": "Found GITHUB_TOKEN"}
        assert r.count == 1
        assert "github" in r.summary()

    def test_skipped_in_summary(self):
        r = DiscoveryResult()
        r.skipped = ["slack"]
        assert "Skipped" in r.summary()
        assert "slack" in r.summary()


# ═══════════════════════════════════════════════════════════════
# Config normalization tests
# ═══════════════════════════════════════════════════════════════

class TestNormalizeConfig:
    def test_stdio_string_command(self):
        """Claude Desktop format: command is a string."""
        cfg = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-fetch"]}
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "stdio"
        assert "npx" in result["command"]

    def test_stdio_list_command(self):
        """mcptoon format: command is a list."""
        cfg = {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-fetch"],
        }
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "stdio"

    def test_http_config(self):
        cfg = {"transport": "http", "url": "http://localhost:8080/mcp"}
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "http"
        assert result["url"] == "http://localhost:8080/mcp"

    def test_empty_config(self):
        assert _normalize_imported_config({}) is None

    def test_none_config(self):
        assert _normalize_imported_config(None) is None

    def test_with_env(self):
        cfg = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"},
        }
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert "env" in result
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in result["env"]


# ═══════════════════════════════════════════════════════════════
# Environment variable detection tests
# ═══════════════════════════════════════════════════════════════

class TestEnvDetection:
    def test_github_token(self):
        with patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "github" in names

    def test_brave_api_key(self):
        with patch.dict(os.environ, {"BRAVE_API_KEY": "BSA_test123"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "brave-search" in names

    def test_no_env_vars(self):
        # Clear all known env vars
        env_vars_to_clear = [
            "GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN",
            "BRAVE_API_KEY", "EXA_API_KEY", "TAVILY_API_KEY",
            "FIRECRAWL_API_KEY", "SLACK_BOT_TOKEN", "SLACK_TOKEN",
            "NOTION_API_KEY", "NOTION_TOKEN", "DATABASE_URL",
        ]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_clear}
        with patch.dict(os.environ, clean_env, clear=True):
            results = _detect_from_env()
            assert len(results) == 0

    def test_placeholder_ignored(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "<your-token>"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "github" not in names

    def test_env_config_has_env_key(self):
        with patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"}):
            results = _detect_from_env()
            github = [r for r in results if r["name"] == "github"][0]
            assert "env" in github["config"]
            assert "GITHUB_PERSONAL_ACCESS_TOKEN" in github["config"]["env"]


# ═══════════════════════════════════════════════════════════════
# Local tool detection tests
# ═══════════════════════════════════════════════════════════════

class TestLocalDetection:
    def test_npx_available(self):
        # npx is likely available in test env
        results = _detect_local_tools()
        # If npx is available, should find zero-config servers
        if _which("npx"):
            names = [r["name"] for r in results]
            assert "fetch" in names
            assert "memory" in names
            assert "sequential-thinking" in names

    def test_git_repo_detection(self):
        # Create a temp dir with .git
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            original = Path.cwd()
            try:
                os.chdir(tmpdir)
                results = _detect_local_tools()
                git_results = [r for r in results if r["name"] == "git"]
                assert len(git_results) >= 1
                # git appears from both zero-config and git-repo detection
                assert "git" in git_results[0]["reason"].lower() or "Zero-config" in git_results[0]["reason"]
            finally:
                os.chdir(original)


# ═══════════════════════════════════════════════════════════════
# Config scanning tests
# ═══════════════════════════════════════════════════════════════

class TestConfigScanning:
    def test_scan_claude_desktop_mock(self):
        """Test scanning Claude Desktop config with a mock file."""
        mock_config = {
            "mcpServers": {
                "fetch": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-fetch"],
                },
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"},
                },
            }
        }

        with patch("mcptoon.discover._home") as mock_home:
            mock_home.return_value = Path("/fake/home")
            with patch("mcptoon.discover.sys.platform", "darwin"):
                config_path = Path("/fake/home/Library/Application Support/Claude/claude_desktop_config.json")
                with patch.object(Path, "exists", lambda self: str(self) == str(config_path)):
                    with patch.object(Path, "read_text", lambda self, encoding=None: json.dumps(mock_config)):
                        results = _scan_claude_desktop()
                        assert len(results) == 2
                        names = [r["name"] for r in results]
                        assert "fetch" in names
                        assert "github" in names

    def test_scan_cursor_mock(self):
        mock_config = {
            "mcpServers": {
                "exa": {
                    "command": "npx",
                    "args": ["-y", "exa-mcp-server"],
                },
            }
        }

        with patch.object(Path, "exists", lambda self: ".cursor" in str(self) and "mcp.json" in str(self)):
            with patch.object(Path, "read_text", lambda self, encoding=None: json.dumps(mock_config)):
                results = _scan_cursor()
                assert len(results) >= 1
                assert results[0]["name"] == "exa"


# ═══════════════════════════════════════════════════════════════
# Network probe tests
# ═══════════════════════════════════════════════════════════════

class TestNetworkProbe:
    def test_probe_dead_endpoint(self):
        """Probing a port that's definitely not running should return False."""
        result = _probe_endpoint("http://127.0.0.1:59999/mcp", timeout=0.1)
        assert result is False

    def test_probe_http_endpoint_dead(self):
        """probe_http_endpoint on dead URL returns None."""
        result = probe_http_endpoint("http://127.0.0.1:59999/mcp", timeout=0.1)
        assert result is None

    def test_make_http_config_normalizes_url(self):
        cfg = make_http_config("localhost:8080")
        assert cfg["transport"] == "http"
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_make_http_config_already_has_http(self):
        cfg = make_http_config("http://localhost:8080/mcp")
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_make_http_config_with_trailing_slash(self):
        cfg = make_http_config("http://localhost:8080/")
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_http_probe_no_network(self):
        """With no MCP_HTTP_URL env var set, _probe_http_mcp should return empty list."""
        # Clear all HTTP MCP env vars
        env_vars_to_clear = ["MCP_HTTP_URL", "MCP_SERVER_URL"]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_clear}
        with patch.dict(os.environ, clean_env, clear=True):
            results = _probe_http_mcp()
            assert isinstance(results, list)
            assert len(results) == 0  # No env vars set → no results

    def test_http_probe_with_env_var(self):
        """When MCP_HTTP_URL is set, _probe_http_mcp should try to probe it."""
        # Use a dead port — should get empty results (probe fails)
        with patch.dict(os.environ, {"MCP_HTTP_URL": "http://127.0.0.1:59999/mcp"}):
            results = _probe_http_mcp()
            assert isinstance(results, list)
            assert len(results) == 0  # Probe failed → not included


# ═══════════════════════════════════════════════════════════════
# Profile matching tests
# ═══════════════════════════════════════════════════════════════

class TestProfileMatching:
    def test_load_profiles(self):
        """Test that bundled profiles can be loaded."""
        profiles = _match_profiles()
        assert isinstance(profiles, list)
        # Profiles may or may not match depending on env — just check structure
        for p in profiles:
            assert "config" in p
            assert "transport" in p["config"]
            assert "name" in p

    def test_profile_has_config(self):
        profiles = _match_profiles()
        for p in profiles:
            assert "config" in p
            assert "transport" in p["config"]


# ═══════════════════════════════════════════════════════════════
# auto_discover integration tests
# ═══════════════════════════════════════════════════════════════

class TestAutoDiscover:
    def test_auto_discover_returns_result(self):
        """auto_discover should return a DiscoveryResult."""
        result = auto_discover(probe_network=False)
        assert isinstance(result, DiscoveryResult)
        assert isinstance(result.servers, dict)
        assert isinstance(result.sources, dict)

    def test_auto_discover_no_network(self):
        """With network probing disabled, should still find local/env servers."""
        result = auto_discover(probe_network=False)
        # If npx is available, should find at least fetch
        if _which("npx"):
            assert "fetch" in result.servers

    def test_auto_discover_dedup(self):
        """Same server from multiple sources should be deduplicated."""
        result = auto_discover(probe_network=False)
        # Check no duplicate names
        for name, sources in result.sources.items():
            # A server can have multiple sources but only one config entry
            assert name in result.servers

    def test_auto_discover_selective(self):
        """Test disabling specific layers."""
        result = auto_discover(
            scan_configs=False,
            detect_env=False,
            detect_local=False,
            probe_network=False,
            match_profiles=False,
        )
        assert result.count == 0

    def test_auto_discover_env_only(self):
        """Test with only env detection."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}):
            result = auto_discover(
                scan_configs=False,
                detect_env=True,
                detect_local=False,
                probe_network=False,
                match_profiles=False,
            )
            assert "github" in result.servers


# ═══════════════════════════════════════════════════════════════
# _which utility test
# ═══════════════════════════════════════════════════════════════

class TestWhich:
    def test_which_python(self):
        """python/python3 should be in PATH."""
        py = _which("python") or _which("python3")
        assert py is not None

    def test_which_nonexistent(self):
        assert _which("definitely_not_a_real_command_xyz") is None
