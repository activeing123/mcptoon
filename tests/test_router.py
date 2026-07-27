# -*- coding: utf-8 -*-
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

"""Tests for mcptoon router module."""
import pytest
from unittest.mock import patch, MagicMock

from mcptoon.router import call_tool, register, _check_dangerous
from mcptoon.errors import is_error, get_error_message


class TestCheckDangerous:
    def test_safe_tool(self):
        assert _check_dangerous("db", "query", {"sql": "SELECT 1"}) is None

    def test_delete_tool(self):
        result = _check_dangerous("db", "delete_record", {})
        assert result is not None
        assert "delete" in result

    def test_remove_tool(self):
        result = _check_dangerous("fs", "remove_file", {})
        assert result is not None

    def test_drop_tool(self):
        result = _check_dangerous("db", "drop_table", {})
        assert result is not None

    def test_force_flag(self):
        result = _check_dangerous("api", "restart", {"force": True})
        assert result is not None
        assert "force" in result

    def test_confirm_flag(self):
        result = _check_dangerous("api", "restart", {"confirm": True})
        assert result is not None

    def test_force_false_is_safe(self):
        result = _check_dangerous("api", "restart", {"force": False})
        assert result is None

    def test_empty_tool(self):
        assert _check_dangerous("srv", "", None) is None


class TestCallTool:
    def test_unknown_server(self):
        with patch("mcptoon.router.load_config", return_value={}):
            result = call_tool("nonexistent", "test", {})
        assert is_error(result)
        assert "UNKNOWN_SERVER" in str(result)

    def test_dangerous_blocked(self):
        result = call_tool("db", "delete_table", {"name": "users"})
        assert is_error(result)
        assert "CONFIRMATION" in str(result)

    def test_dangerous_with_flag(self):
        with patch("mcptoon.router.load_config", return_value={}):
            result = call_tool("db", "delete_table", {"name": "users"}, is_destructive=True)
        # Will fail because server doesn't exist, but not with CONFIRMATION
        assert "CONFIRMATION" not in str(result)

    def test_custom_handler(self):
        @register("test-handler-srv")
        def handler(tool, args):
            if tool == "greet":
                return {"message": f"Hello {args.get('name', 'World')}!"}
            return None

        result = call_tool("test-handler-srv", "greet", {"name": "Alice"})
        assert result == {"message": "Hello Alice!"}

    def test_custom_handler_fallthrough(self):
        @register("test-fallthrough-srv")
        def handler(tool, args):
            return None  # Always fall through

        with patch("mcptoon.router.load_config", return_value={}):
            result = call_tool("test-fallthrough-srv", "test", {})
        # Should fall through to MCP and fail with UNKNOWN_SERVER
        assert is_error(result)


class TestErrors:
    def test_is_error_with_error_envelope(self):
        from mcptoon.errors import make_error
        err = make_error("TEST", "test message")
        assert is_error(err) is True

    def test_is_error_with_normal_dict(self):
        assert is_error({"ok": True}) is False

    def test_is_error_with_string(self):
        assert is_error("hello") is False

    def test_get_error_message_from_envelope(self):
        from mcptoon.errors import make_error
        err = make_error("CODE", "my message")
        assert get_error_message(err) == "my message"

    def test_get_error_message_from_dict_error(self):
        d = {"error": {"message": "nested error"}}
        assert get_error_message(d) == "nested error"

    def test_get_error_message_from_string(self):
        assert "hello" in get_error_message("hello")
