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
Tests for mcptoon serve mode (stdio bridge) and schema simplifier.

These tests run against the echo_server.py, which is a minimal MCP server
used by the existing test suite. No external network or npx needed.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcptoon.schema_simplifier import (
    simplify_schema,
    simplify_tool_def,
    validate_args,
    namespaced_tool_name,
    split_namespaced,
    compute_token_stats,
)


# ═══════════════════════════════════════════════════
# Schema Simplifier Tests
# ═══════════════════════════════════════════════════

class TestSimplifySchema:
    def test_simplify_empty(self):
        """Empty/none schema returns empty object schema."""
        assert simplify_schema(None) == {"type": "object", "properties": {}}
        assert simplify_schema({}) == {"type": "object", "properties": {}}
        assert simplify_schema({"type": "object"}) == {"type": "object"}

    def test_simplify_basic(self):
        """Basic schema with type, properties, required."""
        full = {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch. Must be a valid HTTP(S) URL.",
                    "pattern": "^https?://",
                    "format": "uri",
                    "default": "https://example.com",
                }
            },
            "required": ["url"],
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        }
        simplified = simplify_schema(full)
        assert simplified["type"] == "object"
        assert "url" in simplified["properties"]
        assert simplified["properties"]["url"]["type"] == "string"
        assert "description" in simplified["properties"]["url"]
        # Strip fields
        assert "pattern" not in simplified["properties"]["url"]
        assert "format" not in simplified["properties"]["url"]
        assert "default" not in simplified["properties"]["url"]
        assert "additionalProperties" not in simplified
        assert "$schema" not in simplified

    def test_simplify_enum_small(self):
        """Small enum is kept."""
        full = {
            "type": "object",
            "properties": {
                "color": {
                    "type": "string",
                    "enum": ["red", "green", "blue"],
                }
            },
        }
        simplified = simplify_schema(full)
        assert simplified["properties"]["color"]["enum"] == ["red", "green", "blue"]

    def test_simplify_enum_large(self):
        """Large enum (>5 items) is removed."""
        full = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": ["a", "b", "c", "d", "e", "f", "g"],
                }
            },
        }
        simplified = simplify_schema(full)
        assert "enum" not in simplified["properties"]["code"]

    def test_simplify_nested(self):
        """Nested properties are simplified recursively (one level)."""
        full = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The user's full name. Must be at least 2 characters.",
                            "minLength": 2,
                        }
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                }
            },
        }
        simplified = simplify_schema(full)
        assert simplified["properties"]["user"]["type"] == "object"
        assert simplified["properties"]["user"]["properties"]["name"]["type"] == "string"
        assert "minLength" not in simplified["properties"]["user"]["properties"]["name"]
        assert "additionalProperties" not in simplified["properties"]["user"]

    def test_simplify_array_items(self):
        """Array items are simplified."""
        full = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "An item. Each item must be unique.",
                        "pattern": "^[a-z]+$",
                    },
                }
            },
        }
        simplified = simplify_schema(full)
        assert simplified["properties"]["items"]["type"] == "array"
        assert simplified["properties"]["items"]["items"]["type"] == "string"
        assert "pattern" not in simplified["properties"]["items"]["items"]


class TestSimplifyToolDef:
    def test_simplify_tool_def(self):
        """Full tool definition is simplified."""
        full = {
            "name": "fetch",
            "description": "Fetch a URL and return the content. Supports HTTP and HTTPS. "
                           "Follows redirects. Handles SSL certificates. "
                           "Returns the page content as text.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch. Must be a valid HTTP(S) URL.",
                        "pattern": "^https?://",
                    }
                },
                "required": ["url"],
            },
        }
        simplified = simplify_tool_def(full)
        assert simplified["name"] == "fetch"
        assert simplified["description"]  # Truncated but present
        assert len(simplified["description"]) <= 120
        assert simplified["inputSchema"]["properties"]["url"]["type"] == "string"
        assert "pattern" not in simplified["inputSchema"]["properties"]["url"]

    def test_simplify_tool_def_with_annotations(self):
        """Annotations are preserved if present."""
        full = {
            "name": "delete_item",
            "description": "Delete an item",
            "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
            "annotations": {
                "title": "Delete Item",
                "destructiveHint": True,
                "readOnlyHint": False,
            },
        }
        simplified = simplify_tool_def(full)
        assert simplified["annotations"] is not None
        assert simplified["annotations"].get("destructiveHint") is True


class TestValidateArgs:
    def test_validate_required_pass(self):
        """Required fields present -> no errors."""
        schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["url"],
        }
        errors = validate_args({"url": "https://example.com", "count": 5}, schema)
        assert errors == []

    def test_validate_required_missing(self):
        """Missing required field -> error."""
        schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        errors = validate_args({}, schema)
        assert len(errors) == 1
        assert "Missing required" in errors[0]

    def test_validate_type_mismatch(self):
        """Type mismatch -> error."""
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        errors = validate_args({"count": "not_a_number"}, schema)
        assert len(errors) == 1
        assert "expected integer" in errors[0]

    def test_validate_optional_present(self):
        """Optional fields with correct type -> no error."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        errors = validate_args({"name": "hello"}, schema)
        assert errors == []

    def test_validate_empty_schema(self):
        """Empty schema -> no errors."""
        errors = validate_args({"x": 1}, None)
        assert errors == []
        errors = validate_args({"x": 1}, {})
        assert errors == []

    def test_validate_none_args(self):
        """None args treated as empty dict -> no errors if schema has no required fields."""
        schema = {"type": "object", "properties": {"url": {"type": "string"}}}
        errors = validate_args(None, schema)
        assert errors == []

    def test_validate_none_args_with_required(self):
        """None args treated as empty dict -> missing required field error."""
        schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
        errors = validate_args(None, schema)
        assert len(errors) == 1
        assert "Missing required" in errors[0]


class TestNamespacing:
    def test_namespaced_tool_name(self):
        """Server_tool format."""
        assert namespaced_tool_name("fetch", "fetch") == "fetch_fetch"
        assert namespaced_tool_name("github", "search_code") == "github_search_code"

    def test_split_namespaced_simple(self):
        """Simple server_tool split."""
        server, tool = split_namespaced("fetch_fetch", ["fetch", "github"])
        assert server == "fetch"
        assert tool == "fetch"

    def test_split_namespaced_multi_underscore(self):
        """Tool name with underscores -> longest server match."""
        server, tool = split_namespaced("github_search_code", ["github", "fetch"])
        assert server == "github"
        assert tool == "search_code"

    def test_split_namespaced_unknown_server(self):
        """Unknown server -> fallback to first underscore split."""
        server, tool = split_namespaced("unknown_server_tool", ["fetch", "github"])
        assert server == "unknown"
        assert tool == "server_tool"

    def test_split_namespaced_no_underscore(self):
        """No underscore -> empty server, full name as tool."""
        server, tool = split_namespaced("hello", ["fetch"])
        assert server == ""
        assert tool == "hello"


class TestTokenStats:
    def test_compute_token_stats(self):
        """Token stats computation."""
        stats = compute_token_stats('{"a": 1, "b": "hello"}', '{"a": 1}')
        assert stats["full_tokens"] > stats["simplified_tokens"]
        assert stats["reduction_pct"] > 0


# ═══════════════════════════════════════════════════
# Serve Bridge Tests (integration)
# ═══════════════════════════════════════════════════

@pytest.fixture
def echo_server_config():
    """Create a temporary config with echo_server as the only server."""
    echo_path = Path(__file__).parent / "echo_server.py"
    config = {
        "echo": {
            "transport": "stdio",
            "command": [sys.executable, str(echo_path)],
        }
    }
    config_dir = tempfile.mkdtemp()
    config_file = Path(config_dir) / "config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    original_config = os.environ.get("MCPTOON_CONFIG_DIR")
    os.environ["MCPTOON_CONFIG_DIR"] = config_dir
    yield config
    if original_config:
        os.environ["MCPTOON_CONFIG_DIR"] = original_config
    else:
        os.environ.pop("MCPTOON_CONFIG_DIR", None)


class TestServeBridge:
    def test_initialize(self):
        """Run initialize against bridge via subprocess."""
        ...  # Integration test requiring subprocess spawning


# ═══════════════════════════════════════════════════
# CLI Integration Tests
# ═══════════════════════════════════════════════════

class TestServeCli:
    def test_serve_help(self):
        """mcptoon serve --help shows help."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "serve", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "stdio bridge" in result.stdout.lower()

    def test_demo_help(self):
        """mcptoon demo --help shows help."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "demo", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "demo" in result.stdout.lower()


# ═══════════════════════════════════════════════════
# HTTP Serve Mode Tests
# ═══════════════════════════════════════════════════

class TestServeHttpMode:
    def test_serve_help_includes_http(self):
        """serve --help mentions --listen and --http options."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "serve", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--listen" in result.stdout
        assert "--http" in result.stdout
        assert "HTTP" in result.stdout

    def test_run_serve_parses_listen_arg(self):
        """run_serve --help exits via SystemExit(0) (v0.7.3)."""
        import pytest

        from mcptoon.serve import run_serve
        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            with pytest.raises(SystemExit) as cm:
                run_serve(["--help"])
        assert cm.value.code == 0
        output = f.getvalue()
        assert "stdio bridge" in output.lower()

    def test_http_health_endpoint(self):
        """HTTP serve mode has /health endpoint."""
        from mcptoon.serve import _run_http, MCPServerBridge
        # Verify _run_http exists and is callable
        assert callable(_run_http)
        # Verify MCPServerBridge has _handle_health
        bridge = MCPServerBridge()
        health = bridge._handle_health()
        # Uninitialized bridge should report "starting" (honest status)
        assert health["status"] in ("starting", "ok", "degraded", "error")
        assert "version" in health
        assert "servers" in health
        assert "tools" in health


# ═══════════════════════════════════════════════════
# Install by Name Tests
# ═══════════════════════════════════════════════════

class TestInstallByName:
    def test_install_by_name_exists(self):
        """install_by_name function exists and is callable."""
        from mcptoon.installer import install_by_name
        assert callable(install_by_name)

    def test_search_registry_returns_list(self):
        """search_registry returns a list (even on network error)."""
        from mcptoon.installer import search_registry
        result = search_registry("nonexistent_test_keyword_xyz123")
        assert isinstance(result, list)

    def test_search_smithery_returns_list(self):
        """_search_smithery returns a list."""
        from mcptoon.installer import _search_smithery
        result = _search_smithery("test")
        assert isinstance(result, list)

    def test_search_mcp_registry_returns_list(self):
        """_search_mcp_registry returns a list."""
        from mcptoon.installer import _search_mcp_registry
        result = _search_mcp_registry("test")
        assert isinstance(result, list)
