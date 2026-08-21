# Copyright 2025-2026 cxh
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

"""
Tests for mcptoon serve mode — performance && scale scenarios.

Tests concurrent access, timeout behavior, parallel manifest loading,
and remote MCP (HTTP) server support.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcptoon.serve import MCPServerBridge, _get_call_timeout
from mcptoon.client import MCPClientPool


# ═══════════════════════════════════════════════════
# Performance: 100+ scenarios
# ═══════════════════════════════════════════════════

class TestParallelManifestLoading:
    """Test that parallel loading works for 100+ server scenarios."""

    def test_index_build_with_100_servers(self):
        """Build tool index from 100 simulated servers (no real MCP servers needed).

        This tests: _build_tool_index with cached entries only (fast path).
        """
        bridge = MCPServerBridge()
        # Manually inject 100 cached servers
        for i in range(100):
            srv = f"server{i:03d}"
            for j in range(3):
                tool_name = f"tool{j}"
                ns = f"{srv}_{tool_name}"
                bridge._tool_index[ns] = {
                    "server": srv,
                    "tool": tool_name,
                    "full_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
                    "full_def": {"name": tool_name, "description": f"Tool {j} on {srv}", "inputSchema": {}},
                }
        bridge._initialized = True

        # tools/list should return 300 tools
        result = bridge._handle_list_tools({})
        tools = result.get("tools", [])
        assert len(tools) == 300
        assert tools[0]["name"].startswith("server")
        assert "_tool" in tools[0]["name"]

    def test_index_build_no_duplicates(self):
        """No duplicate tool names when building from multiple servers."""
        bridge = MCPServerBridge()
        bridge._tool_index = {}
        for i in range(5):
            srv = f"srv{i}"
            ns = f"{srv}_echo"
            bridge._tool_index[ns] = {
                "server": srv,
                "tool": "echo",
                "full_schema": {},
                "full_def": {"name": "echo", "description": "Echo", "inputSchema": {}},
            }
        bridge._initialized = True

        result = bridge._handle_list_tools({})
        tools = result.get("tools", [])
        assert len(tools) == 5
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names))  # All unique
        assert "srv0_echo" in names
        assert "srv4_echo" in names


# ═══════════════════════════════════════════════════
# Concurrency: thread safety
# ═══════════════════════════════════════════════════

class TestConcurrency:
    """Test that the bridge handles concurrent tool calls correctly."""

    def test_tool_index_thread_safe(self):
        """_tool_index is thread-safe under concurrent access."""
        bridge = MCPServerBridge()
        bridge._initialized = True

        # Populate from multiple threads
        def _add_tools(prefix: str, count: int):
            for i in range(count):
                ns = f"{prefix}_tool{i}"
                with bridge._tool_index_lock:
                    bridge._tool_index[ns] = {
                        "server": prefix,
                        "tool": f"tool{i}",
                        "full_schema": {},
                        "full_def": {},
                    }

        threads = []
        for t in range(10):
            th = threading.Thread(target=_add_tools, args=(f"t{t}", 50))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()

        assert len(bridge._tool_index) == 500  # 10 × 50

    def test_tools_list_under_concurrent_read(self):
        """tools/list returns consistent results under concurrent reads."""
        bridge = MCPServerBridge()
        bridge._initialized = True
        for i in range(100):
            ns = f"server{i}_tool"
            bridge._tool_index[ns] = {
                "server": f"server{i}",
                "tool": "tool",
                "full_schema": {},
                "full_def": {"name": "tool", "description": "Test", "inputSchema": {}},
            }

        results = []
        def _read():
            results.append(len(bridge._handle_list_tools({}).get("tools", [])))

        threads = [threading.Thread(target=_read) for _ in range(20)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # All readers should see 100 tools
        assert all(r == 100 for r in results)


# ═══════════════════════════════════════════════════
# Timeout: per-call timeout
# ═══════════════════════════════════════════════════

class TestTimeout:
    """Test that per-call timeout prevents hung servers from blocking the bridge."""

    def test_get_call_timeout_default(self):
        """Default timeout is 30 seconds."""
        # Clear env var
        old = os.environ.pop("MCPTOON_CALL_TIMEOUT", None)
        try:
            assert _get_call_timeout() == 30
        finally:
            if old is not None:
                os.environ["MCPTOON_CALL_TIMEOUT"] = old

    def test_get_call_timeout_env(self):
        """Timeout can be set via environment variable."""
        old = os.environ.get("MCPTOON_CALL_TIMEOUT")
        os.environ["MCPTOON_CALL_TIMEOUT"] = "10"
        try:
            assert _get_call_timeout() == 10
        finally:
            if old is not None:
                os.environ["MCPTOON_CALL_TIMEOUT"] = old
            else:
                os.environ.pop("MCPTOON_CALL_TIMEOUT", None)

    def test_get_call_timeout_invalid_env(self):
        """Invalid env value falls back to default."""
        old = os.environ.get("MCPTOON_CALL_TIMEOUT")
        os.environ["MCPTOON_CALL_TIMEOUT"] = "not-a-number"
        try:
            assert _get_call_timeout() == 30
        finally:
            if old is not None:
                os.environ["MCPTOON_CALL_TIMEOUT"] = old
            else:
                os.environ.pop("MCPTOON_CALL_TIMEOUT", None)


# ═══════════════════════════════════════════════════
# Remote MCP (HTTP) scenarios
# ═══════════════════════════════════════════════════

class TestRemoteMCP:
    """Test that remote MCP servers are supported transparently.

    Note: These tests verify the config parsing and proxy setup.
    Full HTTP integration tests require a running MCP server.
    """

    def test_config_http_transport(self):
        """Config with HTTP transport is parsed correctly."""
        config = {
            "remote": {
                "transport": "http",
                "url": "http://10.0.0.1:3001/mcp",
                "headers": {"Authorization": "Bearer test-token"},
            }
        }
        # Verify config can be loaded and client created
        pool = MCPClientPool(config)
        assert pool._servers == config
        pool.close()

    def test_mixed_transport_config(self):
        """Config with mixed stdio + HTTP servers is supported."""
        config = {
            "local": {
                "transport": "stdio",
                "command": ["npx", "-y", "@modelcontextprotocol/server-fetch"],
            },
            "remote": {
                "transport": "http",
                "url": "http://10.0.0.1:3001/mcp",
            },
        }
        pool = MCPClientPool(config)
        assert len(pool._servers) == 2
        pool.close()


# ═══════════════════════════════════════════════════
# CLI integration
# ═══════════════════════════════════════════════════

class TestServeHelp:
    def test_serve_help_contains_performance_info(self):
        """Help text mentions performance features."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "serve", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert "Parallel manifest loading" in result.stdout
        assert "per-call timeout" in result.stdout.lower()
        assert "MCPTOON_CALL_TIMEOUT" in result.stdout
        assert "MCPTOON_CACHE_TTL" in result.stdout
