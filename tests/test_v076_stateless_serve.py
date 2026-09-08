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

"""Tests for the stateless-first serve bridge + SEP-2549 CacheableResult.

MCP 2026-07-28 GA server-side surface:
- the initialize handshake no longer exists in the protocol: a modern client
  may call tools/list without ever sending initialize; the bridge serves it.
- server/discover RPC advertises protocolVersions/capabilities/serverInfo.
- self-describing requests: _meta io.modelcontextprotocol/* keys are accepted;
  an unsupported version there is rejected with -32022.
- every ordinary result carries resultType: "complete".
- tools/list | prompts/list | resources/list | resources/read carry
  ttlMs + cacheScope (SEP-2549 CacheableResult; env-tunable, invalid env
  values fall back to safe defaults).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcptoon.client import (  # noqa: E402
    ERR_UNSUPPORTED_PROTOCOL_VERSION,
    LATEST_PROTOCOL_VERSION,
)
from mcptoon.serve import MCPServerBridge  # noqa: E402

_META_PROTOCOL = "io.modelcontextprotocol/protocolVersion"
_DEFAULT_TTL_MS = 300_000

_SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}}


def _rpc(method, params=None, _id=1, meta=None):
    params = dict(params or {})
    if meta is not None:
        params["_meta"] = meta
    return {"jsonrpc": "2.0", "id": _id, "method": method, "params": params}


@pytest.fixture()
def bridge():
    """A bridge with a seeded tool index.

    Protocol-surface tests only: no subprocess, no user config is touched.
    """
    b = MCPServerBridge(output_format="compact")
    b._servers = {"echo": {"command": "unused"}}
    b._tool_index = {
        "echo_ping": {
            "server": "echo", "tool": "ping", "full_schema": _SCHEMA,
            "full_def": {"name": "ping", "description": "ping back",
                         "inputSchema": _SCHEMA},
        },
        "echo_hello": {
            "server": "echo", "tool": "hello", "full_schema": _SCHEMA,
            "full_def": {"name": "hello", "description": "say hello",
                         "inputSchema": _SCHEMA},
        },
    }
    b._prompts_index = {
        "greet": {"description": "say hi", "path": "missing.md",
                  "body": "# greet"},
    }
    b._initialized = True
    yield b
    b.close()


def _result(bridge, request):
    resp = bridge.handle_request(request)
    assert resp is not None, "expected a response"
    assert "error" not in resp, f"unexpected error: {resp.get('error')}"
    return resp["result"]


# ═══════════════════════════════════════════════════
# 1. Stateless-first (GA removed the initialize handshake)
# ═══════════════════════════════════════════════════

class TestStatelessFirst:
    def test_tools_list_without_initialize(self, bridge):
        """A modern client skips initialize entirely."""
        result = _result(bridge, _rpc("tools/list", _id=11))
        names = [t["name"] for t in result["tools"]]
        assert "echo_ping" in names and "echo_hello" in names

    def test_handshake_path_returns_same_tools(self, bridge):
        """Legacy clients get identical tool listings."""
        a = _result(bridge, _rpc("tools/list", _id=21))
        _result(bridge, _rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "old", "version": "1"},
        }, _id=22))
        b = _result(bridge, _rpc("tools/list", _id=23))
        assert [t["name"] for t in a["tools"]] == [t["name"] for t in b["tools"]]

    def test_server_discover(self, bridge):
        """server/discover advertises versions, capabilities, identity."""
        result = _result(bridge, _rpc("server/discover", _id=31))
        assert LATEST_PROTOCOL_VERSION in result["protocolVersions"]
        assert result["serverInfo"]["name"] == "mcptoon"
        assert "tools" in result["capabilities"]

    def test_meta_self_describing_accepted(self, bridge):
        """_meta io.modelcontextprotocol/* keys ride along on any request."""
        meta = {
            _META_PROTOCOL: "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "0"},
        }
        result = _result(bridge, _rpc("tools/list", _id=41, meta=meta))
        assert result["tools"]

    def test_meta_legacy_draft_key_accepted(self, bridge):
        """Pre-GA drafts used a bare _meta.protocolVersion — also accepted."""
        result = _result(bridge, _rpc(
            "tools/list", _id=42, meta={_META_PROTOCOL: "2026-07-28"}))
        result = _result(bridge, _rpc(
            "tools/list", _id=43, meta={"protocolVersion": "2026-07-28"}))
        assert result["tools"]

    def test_meta_unsupported_version_rejected(self, bridge):
        resp = bridge.handle_request(_rpc(
            "tools/list", _id=44, meta={_META_PROTOCOL: "1999-01-01"}))
        assert resp["error"]["code"] == ERR_UNSUPPORTED_PROTOCOL_VERSION
        assert "1999-01-01" in resp["error"]["message"]


# ═══════════════════════════════════════════════════
# 2. CacheableResult (SEP-2549) on list/read results
# ═══════════════════════════════════════════════════

class TestCacheableResult:
    def test_tools_list_fields(self, bridge):
        result = _result(bridge, _rpc("tools/list", _id=51))
        assert isinstance(result["ttlMs"], int) and result["ttlMs"] >= 1
        assert result["cacheScope"] in ("public", "private")
        assert result["resultType"] == "complete"

    def test_prompts_list_fields(self, bridge):
        result = _result(bridge, _rpc("prompts/list", _id=52))
        assert result["ttlMs"] >= 1
        assert result["cacheScope"] in ("public", "private")
        assert result["resultType"] == "complete"

    def test_resources_list_fields(self, bridge):
        result = _result(bridge, _rpc("resources/list", _id=53))
        assert result["resources"] == []
        assert result["ttlMs"] >= 1
        assert result["cacheScope"] in ("public", "private")
        assert result["resultType"] == "complete"

    def test_resources_read_fields(self, bridge):
        result = _result(bridge, _rpc(
            "resources/read", {"uri": "file:///nonexistent"}, _id=54))
        assert result["ttlMs"] >= 1
        assert result["cacheScope"] in ("public", "private")

    def test_env_ttl_override(self, bridge, monkeypatch):
        monkeypatch.setenv("MCPTOON_LIST_TTL_MS", "60000")
        result = _result(bridge, _rpc("tools/list", _id=61))
        assert result["ttlMs"] == 60000

    def test_env_ttl_invalid_falls_back(self, bridge, monkeypatch):
        monkeypatch.setenv("MCPTOON_LIST_TTL_MS", "banana")
        result = _result(bridge, _rpc("tools/list", _id=62))
        assert result["ttlMs"] == _DEFAULT_TTL_MS

    def test_env_ttl_zero_falls_back(self, bridge, monkeypatch):
        monkeypatch.setenv("MCPTOON_LIST_TTL_MS", "0")
        result = _result(bridge, _rpc("tools/list", _id=63))
        assert result["ttlMs"] == _DEFAULT_TTL_MS

    def test_env_scope_invalid_falls_back(self, bridge, monkeypatch):
        monkeypatch.setenv("MCPTOON_LIST_CACHE_SCOPE", "banana")
        result = _result(bridge, _rpc("tools/list", _id=64))
        assert result["cacheScope"] == "public"


# ═══════════════════════════════════════════════════
# 3. resultType on every ordinary result
# ═══════════════════════════════════════════════════

class TestResultTypeEverywhere:
    def test_ping(self, bridge):
        result = _result(bridge, _rpc("ping", _id=71))
        assert result["resultType"] == "complete"

    def test_initialize(self, bridge):
        result = _result(bridge, _rpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "c", "version": "1"},
        }, _id=72))
        assert result["resultType"] == "complete"
        assert result["protocolVersion"] == "2024-11-05"  # legacy contract kept

    def test_initialize_modern_version_echoed(self, bridge):
        result = _result(bridge, _rpc("initialize", {
            "protocolVersion": "2026-07-28", "capabilities": {},
            "clientInfo": {"name": "c", "version": "1"},
        }, _id=73))
        assert result["protocolVersion"] == "2026-07-28"

    def test_health(self, bridge):
        result = _result(bridge, _rpc("health", _id=74))
        assert result["resultType"] == "complete"

    def test_tool_error_result(self, bridge):
        resp = bridge.handle_request(_rpc(
            "tools/call", {"name": "nope_tool", "arguments": {}}, _id=81))
        assert resp["result"].get("isError") is True
        assert resp["result"]["resultType"] == "complete"
