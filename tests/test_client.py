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

"""Tests for mcptoon client module — MCPClient and MCPClientPool."""
import pytest
from unittest.mock import MagicMock

from mcptoon.client import MCPClient, MCPClientPool, MCPError, _next_id


class TestNextId:
    def test_increments(self):
        id1 = _next_id()
        id2 = _next_id()
        assert id2 > id1

    def test_positive(self):
        assert _next_id() > 0


class TestMCPClientInit:
    def test_stdio_transport(self):
        client = MCPClient(stdio=["npx", "-y", "@mcp/server"])
        assert client._transport == "stdio"

    def test_http_transport(self):
        client = MCPClient(http="http://localhost:3001/mcp")
        assert client._transport == "http"

    def test_both_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            MCPClient(stdio=["cmd"], http="http://localhost")

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="Must pass"):
            MCPClient()

    def test_headers_stored(self):
        client = MCPClient(http="http://localhost", headers={"X-Key": "val"})
        assert client._headers == {"X-Key": "val"}

    def test_env_stored(self):
        client = MCPClient(stdio=["cmd"], env={"FOO": "bar"})
        assert client._env == {"FOO": "bar"}

    def test_default_timeout(self):
        client = MCPClient(http="http://localhost")
        assert client._timeout == 30

    def test_custom_timeout(self):
        client = MCPClient(http="http://localhost", timeout=60)
        assert client._timeout == 60


class TestMCPClientParseJsonLine:
    def test_valid_json(self):
        line = b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n'
        result = MCPClient._parse_json_line(line)
        assert result["jsonrpc"] == "2.0"
        assert result["result"]["tools"] == []

    def test_empty_line(self):
        with pytest.raises(MCPError, match="empty"):
            MCPClient._parse_json_line(b"")

    def test_invalid_json(self):
        with pytest.raises(MCPError, match="Invalid JSON"):
            MCPClient._parse_json_line(b'not json\n')

    def test_whitespace_only(self):
        with pytest.raises(MCPError, match="empty"):
            MCPClient._parse_json_line(b"   \n")


class TestMCPClientParseHttpBody:
    def test_plain_json(self):
        body = '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
        result = MCPClient._parse_http_body(body)
        assert result["result"]["ok"] is True

    def test_sse_format(self):
        body = "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"ok\":true}}\n\n"
        result = MCPClient._parse_http_body(body)
        assert result["result"]["ok"] is True

    def test_sse_with_multiple_lines(self):
        body = "event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}\n\n"
        result = MCPClient._parse_http_body(body)
        assert result["jsonrpc"] == "2.0"

    def test_invalid_body(self):
        with pytest.raises(MCPError, match="Cannot parse"):
            MCPClient._parse_http_body("not json at all")


class TestMCPClientExtractContent:
    def test_text_content_parsed_as_json(self):
        result = {"content": [{"type": "text", "text": '{"key":"value"}'}]}
        extracted = MCPClient._extract_content(result)
        assert extracted == {"key": "value"}

    def test_text_content_plain_text(self):
        result = {"content": [{"type": "text", "text": "Hello world"}]}
        extracted = MCPClient._extract_content(result)
        assert extracted == {"text": "Hello world"}

    def test_error_content(self):
        result = {"isError": True, "content": [{"type": "text", "text": "Something failed"}]}
        extracted = MCPClient._extract_content(result)
        assert extracted["error"] is True
        assert "Something failed" in extracted["message"]

    def test_empty_content(self):
        result = {"content": []}
        extracted = MCPClient._extract_content(result)
        assert extracted == result

    def test_non_dict_result(self):
        assert MCPClient._extract_content("string") == "string"

    def test_multiple_text_contents(self):
        result = {"content": [
            {"type": "text", "text": '{"part":'},
            {"type": "text", "text": '"one"}'},
        ]}
        extracted = MCPClient._extract_content(result)
        assert extracted == {"part": "one"}


class TestMCPClientPool:
    def test_make_client_stdio(self):
        cfg = {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@mcp/server"],
        }
        client = MCPClientPool._make_client(cfg)
        assert client._transport == "stdio"
        assert client._stdio_cmd == ["npx", "-y", "@mcp/server"]

    def test_make_client_http(self):
        cfg = {
            "transport": "http",
            "url": "http://localhost:3001/mcp",
            "headers": {"X-Key": "val"},
        }
        client = MCPClientPool._make_client(cfg)
        assert client._transport == "http"
        assert client._http_url == "http://localhost:3001/mcp"

    def test_make_client_bad_transport(self):
        cfg = {"transport": "websocket"}
        with pytest.raises(MCPError, match="Unknown transport"):
            MCPClientPool._make_client(cfg)

    def test_make_client_default_transport(self):
        # No transport field → defaults to stdio
        cfg = {"command": ["cmd"]}
        client = MCPClientPool._make_client(cfg)
        assert client._transport == "stdio"

    def test_pool_get_unknown_server(self):
        pool = MCPClientPool({})
        with pytest.raises(MCPError, match="not in config"):
            pool._get_client("nonexistent")

    def test_pool_close(self):
        pool = MCPClientPool({"test": {"transport": "http", "url": "http://localhost"}})
        pool._clients = {"test": MagicMock()}
        pool.close()
        assert pool._clients == {}
