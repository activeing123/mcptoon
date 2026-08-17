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

"""Tests for mcptoon output module — Standard TOON, legacy mcptoon, and rendering."""
import json
import pytest

from mcptoon.output import (
    # Standard TOON
    toon_encode, toon_decode,
    # Legacy mcptoon
    mcptoon_encode, mcptoon_decode,
    _mcptoon_escape, _mcptoon_unescape, _mcptoon_value, _mcptoon_scalar,
    _split_unescaped, _find_unescaped, toon, _toon_value, _toon_scalar,
    # Slim
    slim_toon,
    # Compact
    compact,
    # Render
    render, head, _truncate,
)


# ═══════════════════════════════════════════════════════════════
# Standard TOON Encoder Tests
# ═══════════════════════════════════════════════════════════════

class TestToonEncodeScalar:
    def test_string(self):
        result = toon_encode({"name": "search"})
        assert "search" in result

    def test_int(self):
        result = toon_encode({"count": 42})
        assert "42" in result

    def test_float(self):
        result = toon_encode({"pi": 3.14})
        assert "3.14" in result

    def test_bool_true(self):
        result = toon_encode({"ok": True})
        assert "true" in result

    def test_bool_false(self):
        result = toon_encode({"ok": False})
        assert "false" in result

    def test_null(self):
        result = toon_encode({"err": None})
        assert "null" in result

    def test_string_with_comma_quoted(self):
        result = toon_encode({"desc": "hello, world"})
        assert '"hello, world"' in result

    def test_string_with_quote_escaped(self):
        result = toon_encode({"desc": 'say "hi"'})
        assert '""hi""' in result


class TestToonEncodeDict:
    def test_empty_dict(self):
        assert toon_encode({}) == "{}"

    def test_simple_dict(self):
        result = toon_encode({"name": "search", "count": 3})
        assert "name: search" in result
        assert "count: 3" in result

    def test_nested_dict(self):
        result = toon_encode({"config": {"host": "localhost", "port": 8080}})
        assert "config:" in result
        assert "host: localhost" in result
        assert "port: 8080" in result

    def test_dict_with_bool_and_null(self):
        result = toon_encode({"ok": True, "err": None})
        assert "ok: true" in result
        assert "err: null" in result


class TestToonEncodeList:
    def test_empty_list(self):
        assert toon_encode([]) == "[]"

    def test_scalar_list(self):
        result = toon_encode({"tags": ["ai", "ml", "nlp"]})
        assert "tags[3]:" in result
        assert "ai" in result
        assert "ml" in result
        assert "nlp" in result

    def test_uniform_object_array(self):
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = toon_encode(data)
        assert "[2]{id,name}:" in result
        assert "1,Alice" in result
        assert "2,Bob" in result

    def test_top_level_uniform_array(self):
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = toon_encode(data)
        assert "[2]{id,name}:" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_mixed_type_array(self):
        data = {"items": [1, "hello", True]}
        result = toon_encode(data)
        assert "items[3]:" in result


class TestToonEncodeUrl:
    """Critical: URLs must not be mangled (was the bug in legacy format)."""

    def test_url_preserved(self):
        result = toon_encode({"url": "https://example.com"})
        assert "https://example.com" in result

    def test_url_with_path(self):
        result = toon_encode({"url": "https://api.example.com/v1/search?q=AI"})
        assert "https://api.example.com/v1/search?q=AI" in result

    def test_time_preserved(self):
        result = toon_encode({"time": "12:30:00"})
        assert "12:30:00" in result


# ═══════════════════════════════════════════════════════════════
# Standard TOON Decoder Tests
# ═══════════════════════════════════════════════════════════════

class TestToonDecode:
    def test_simple_dict(self):
        result = toon_decode("name: search\ncount: 3")
        assert result["name"] == "search"
        assert result["count"] == 3

    def test_bool_and_null(self):
        result = toon_decode("ok: true\nerr: null")
        assert result["ok"] is True
        assert result["err"] is None

    def test_nested_dict(self):
        result = toon_decode("config:\n  host: localhost\n  port: 8080")
        assert result["config"]["host"] == "localhost"
        assert result["config"]["port"] == 8080

    def test_uniform_object_array(self):
        result = toon_decode("[2]{id,name}:\n  1,Alice\n  2,Bob")
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[1]["id"] == 2
        assert result[1]["name"] == "Bob"

    def test_empty_string(self):
        assert toon_decode("") is None

    def test_none_input(self):
        assert toon_decode(None) is None

    def test_quoted_value_with_comma(self):
        result = toon_decode('desc: "hello, world"')
        assert result["desc"] == "hello, world"


class TestToonRoundTrip:
    """Round-trip: decode(encode(x)) == x"""

    def test_simple_dict(self):
        original = {"name": "search", "count": 3}
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original

    def test_dict_with_bool_null(self):
        original = {"ok": True, "err": None}
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original

    def test_dict_with_url(self):
        original = {"url": "https://example.com"}
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original

    def test_uniform_object_array(self):
        original = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original

    def test_nested_dict(self):
        original = {"config": {"host": "localhost", "port": 8080}}
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original


# ═══════════════════════════════════════════════════════════════
# Legacy mcptoon Format Tests
# ═══════════════════════════════════════════════════════════════

class TestMcptoonEscape:
    def test_escape_colon(self):
        assert _mcptoon_escape("https://example.com") == "https\\c//example.com"

    def test_escape_pipe(self):
        assert _mcptoon_escape("a|b") == "a\\pb"

    def test_escape_backslash(self):
        assert _mcptoon_escape("a\\b") == "a\\\\b"

    def test_escape_multiple(self):
        assert _mcptoon_escape("a:b|c\\d") == "a\\cb\\pc\\\\d"

    def test_unescape_colon(self):
        assert _mcptoon_unescape("https\\c//example.com") == "https://example.com"

    def test_unescape_pipe(self):
        assert _mcptoon_unescape("a\\pb") == "a|b"

    def test_unescape_backslash(self):
        assert _mcptoon_unescape("a\\\\b") == "a\\b"

    def test_round_trip_escape(self):
        originals = [
            "https://example.com:8080/path",
            "a|b|c",
            "mixed:pipe|and\\backslash",
            "no special chars",
            "",
            "中文:测试|管道",
        ]
        for original in originals:
            escaped = _mcptoon_escape(original)
            unescaped = _mcptoon_unescape(escaped)
            assert unescaped == original, f"Round-trip failed: {original!r} → {escaped!r} → {unescaped!r}"


class TestMcptoonScalar:
    def test_bool_true(self):
        assert _mcptoon_scalar(True) == "true"

    def test_bool_false(self):
        assert _mcptoon_scalar(False) == "false"

    def test_none(self):
        assert _mcptoon_scalar(None) == "null"

    def test_int(self):
        assert _mcptoon_scalar(42) == "42"

    def test_float(self):
        assert _mcptoon_scalar(3.14) == "3.14"

    def test_string(self):
        assert _mcptoon_scalar("hello") == "hello"

    def test_string_with_colon_escaped(self):
        """Critical: colons should be escaped, not replaced (was the data-loss bug)."""
        result = _mcptoon_scalar("https://example.com")
        assert "\\c" in result
        assert "_" not in result  # Old behavior replaced with _, now escapes

    def test_string_with_pipe_escaped(self):
        result = _mcptoon_scalar("a|b")
        assert "\\p" in result

    def test_long_string_truncated(self):
        long_str = "x" * 600
        result = _mcptoon_scalar(long_str)
        assert len(result) <= 500 + 10  # Allow for escape expansion


class TestMcptoonValue:
    def test_empty_dict(self):
        assert _mcptoon_value({}) == "{}"

    def test_simple_dict(self):
        result = _mcptoon_value({"name": "search", "count": 3})
        assert "name:search" in result
        assert "count:3" in result
        assert "|" in result

    def test_dict_with_bool(self):
        assert _mcptoon_value({"ok": True}) == "ok:true"

    def test_dict_with_none(self):
        assert _mcptoon_value({"err": None}) == "err:null"

    def test_empty_list(self):
        assert _mcptoon_value([]) == "[]"

    def test_scalar_list(self):
        assert _mcptoon_value([1, 2, 3]) == "1 2 3"

    def test_string_list(self):
        assert _mcptoon_value(["a", "b", "c"]) == "a b c"

    def test_nested_dict_in_list(self):
        result = _mcptoon_value([{"name": "x"}])
        assert "name:x" in result


class TestMcptoonEncode:
    def test_string_passthrough(self):
        assert mcptoon_encode("hello") == "hello"

    def test_dict(self):
        result = mcptoon_encode({"name": "search", "count": 3})
        assert "name:search" in result
        assert "count:3" in result

    def test_list_of_dicts(self):
        result = mcptoon_encode([{"name": "a"}, {"name": "b"}])
        assert "name:a" in result
        assert "name:b" in result
        assert "\n" in result

    def test_bool_and_null(self):
        assert mcptoon_encode({"ok": True, "err": None}) == "ok:true|err:null"

    def test_url_not_mangled(self):
        """Critical: URL must be escaped, not destroyed."""
        result = mcptoon_encode({"url": "https://example.com"})
        assert "\\c" in result  # Colon is escaped
        assert "example.com" in result  # Domain preserved


class TestMcptoonDecode:
    def test_simple_dict(self):
        result = mcptoon_decode("name:search|count:3")
        assert result["name"] == "search"
        assert result["count"] == 3

    def test_bool_and_null(self):
        result = mcptoon_decode("ok:true|err:null")
        assert result["ok"] is True
        assert result["err"] is None

    def test_url_round_trip(self):
        original = {"url": "https://example.com:8080"}
        encoded = mcptoon_encode(original)
        decoded = mcptoon_decode(encoded)
        assert decoded == original

    def test_empty_string(self):
        assert mcptoon_decode("") is None

    def test_empty_dict(self):
        assert mcptoon_decode("{}") == {}

    def test_empty_list(self):
        assert mcptoon_decode("[]") == []

    def test_nested_value_with_pipe(self):
        original = {"desc": "a|b|c"}
        encoded = mcptoon_encode(original)
        decoded = mcptoon_decode(encoded)
        assert decoded == original

    def test_multiple_dicts(self):
        text = "name:a\nname:b"
        result = mcptoon_decode(text)
        assert isinstance(result, list)
        assert result[0]["name"] == "a"
        assert result[1]["name"] == "b"


class TestMcptoonRoundTrip:
    """Round-trip tests for legacy mcptoon format."""

    @pytest.mark.parametrize("data", [
        {"name": "search", "count": 3},
        {"ok": True, "err": None},
        {"url": "https://example.com"},
        {"url": "https://example.com:8080/path?q=1"},
        {"time": "12:30:00"},
        {"desc": "a|b|c"},
        {"mixed": "a:b|c\\d"},
        {"empty": ""},
        {"unicode": "中文测试"},
        {"nested": {"a": "b"}},
        [1, 2, 3],
        ["a", "b", "c"],
        [{"name": "a"}, {"name": "b"}],
    ])
    def test_round_trip(self, data):
        encoded = mcptoon_encode(data)
        decoded = mcptoon_decode(encoded)
        assert decoded == data, f"Round-trip failed for {data!r}\n  encoded: {encoded!r}\n  decoded: {decoded!r}"


class TestSplitUnescaped:
    def test_simple_split(self):
        assert _split_unescaped("a|b|c", "|") == ["a", "b", "c"]

    def test_escaped_delimiter(self):
        assert _split_unescaped("a\\pb|c", "|") == ["a\\pb", "c"]

    def test_no_delimiter(self):
        assert _split_unescaped("abc", "|") == ["abc"]


class TestFindUnescaped:
    def test_find_colon(self):
        assert _find_unescaped("a:b", ":") == 1

    def test_find_escaped_colon(self):
        assert _find_unescaped("a\\c:b", ":") == 3

    def test_not_found(self):
        assert _find_unescaped("abc", ":") == -1


# ═══════════════════════════════════════════════════════════════
# Deprecated Aliases Tests (backward compatibility)
# ═══════════════════════════════════════════════════════════════

class TestDeprecatedAliases:
    def test_toon_alias_works(self):
        """The old toon() function should still work (delegates to mcptoon_encode)."""
        result = toon({"name": "search", "count": 3})
        assert "name:search" in result

    def test_toon_scalar_alias(self):
        assert _toon_scalar(True) == "true"
        assert _toon_scalar(None) == "null"
        assert _toon_scalar(42) == "42"

    def test_toon_value_alias(self):
        assert _toon_value({"ok": True}) == "ok:true"

    def test_toon_string_passthrough(self):
        assert toon("hello") == "hello"

    def test_toon_list_of_dicts(self):
        result = toon([{"name": "a"}, {"name": "b"}])
        assert "name:a" in result
        assert "name:b" in result


# ═══════════════════════════════════════════════════════════════
# Slim TOON Tests (unchanged from before)
# ═══════════════════════════════════════════════════════════════

class TestSlimToon:
    def test_single_tool_with_required_string(self):
        tool = {"name": "search", "inputSchema": {
            "properties": {"q": {"type": "string"}},
            "required": ["q"]}}
        assert slim_toon(tool) == "search|q:s*"

    def test_single_tool_with_optional_number(self):
        tool = {"name": "search", "inputSchema": {
            "properties": {"q": {"type": "string"}, "n": {"type": "number"}},
            "required": ["q"]}}
        assert slim_toon(tool) == "search|q:s*|n:n"

    def test_tool_with_boolean_param(self):
        tool = {"name": "toggle", "inputSchema": {
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"]}}
        assert slim_toon(tool) == "toggle|enabled:b*"

    def test_tool_with_integer_param(self):
        tool = {"name": "paginate", "inputSchema": {
            "properties": {"page": {"type": "integer"}}}}
        assert slim_toon(tool) == "paginate|page:n"

    def test_tool_with_no_params(self):
        tool = {"name": "list_all", "inputSchema": {"properties": {}}}
        assert slim_toon(tool) == "list_all"

    def test_tool_with_no_schema(self):
        tool = {"name": "bare_tool"}
        assert slim_toon(tool) == "bare_tool"

    def test_tool_with_array_param(self):
        tool = {"name": "batch", "inputSchema": {
            "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["ids"]}}
        assert slim_toon(tool) == "batch|ids:a[s]*"

    def test_tool_with_array_of_numbers(self):
        tool = {"name": "sum", "inputSchema": {
            "properties": {"nums": {"type": "array", "items": {"type": "number"}}}}}
        assert slim_toon(tool) == "sum|nums:a[n]"

    def test_tool_with_object_param(self):
        tool = {"name": "create", "inputSchema": {
            "properties": {"meta": {"type": "object", "properties": {"title": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}}}}}
        result = slim_toon(tool)
        assert result == "create|meta:o{title,tags}"

    def test_tool_with_union_type(self):
        tool = {"name": "flex", "inputSchema": {
            "properties": {"val": {"type": ["string", "null"]}}}}
        assert slim_toon(tool) == "flex|val:s"

    def test_tool_with_unknown_type(self):
        tool = {"name": "weird", "inputSchema": {
            "properties": {"x": {"type": "custom_type"}}}}
        result = slim_toon(tool)
        assert "weird|x:" in result

    def test_multiple_tools_as_list(self):
        tools = [
            {"name": "search", "inputSchema": {"properties": {"q": {"type": "string"}}, "required": ["q"]}},
            {"name": "fetch", "inputSchema": {"properties": {"url": {"type": "string"}}, "required": ["url"]}},
        ]
        result = slim_toon(tools)
        assert "search|q:s*" in result
        assert "fetch|url:s*" in result
        assert "\n" in result

    def test_mixed_list_with_non_tool_dicts(self):
        items = [
            {"name": "tool1", "inputSchema": {"properties": {"x": {"type": "string"}}}},
            {"not_a_tool": True},
        ]
        result = slim_toon(items)
        assert "tool1|x:s" in result

    def test_non_dict_passthrough(self):
        assert slim_toon("hello") == "hello"
        assert slim_toon(42) == "42"

    def test_empty_list(self):
        assert slim_toon([]) == ""

    def test_all_required_marked(self):
        tool = {"name": "multi", "inputSchema": {
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "number"},
                "c": {"type": "boolean"},
            },
            "required": ["a", "b", "c"]}}
        result = slim_toon(tool)
        assert "a:s*" in result
        assert "b:n*" in result
        assert "c:b*" in result

    def test_no_required_means_no_stars(self):
        tool = {"name": "optional", "inputSchema": {
            "properties": {"x": {"type": "string"}}}}
        assert "*" not in slim_toon(tool)


# ═══════════════════════════════════════════════════════════════
# Compact Tests
# ═══════════════════════════════════════════════════════════════

class TestCompact:
    def test_list_of_dicts_with_name(self):
        result = compact([{"name": "a"}, {"name": "b"}, {"name": "c"}])
        assert result == "a b c"

    def test_list_of_dicts_with_id(self):
        result = compact([{"id": 1}, {"id": 2}])
        assert "1" in result and "2" in result

    def test_list_of_strings(self):
        assert compact(["x", "y", "z"]) == "x y z"

    def test_empty_list(self):
        assert compact([]) == ""

    def test_dict_with_name(self):
        assert compact({"name": "test"}) == "test"

    def test_max_items(self):
        result = compact([{"name": str(i)} for i in range(50)], max_items=5)
        assert result.count(" ") == 4  # 5 items = 4 spaces


# ═══════════════════════════════════════════════════════════════
# Head & Truncate Tests
# ═══════════════════════════════════════════════════════════════

class TestHead:
    def test_list(self):
        assert head([1, 2, 3, 4, 5], 2) == [1, 2]

    def test_dict_with_list_value(self):
        d = {"items": [1, 2, 3, 4, 5]}
        result = head(d, 2)
        assert result["items"] == [1, 2]

    def test_no_truncation_needed(self):
        assert head([1, 2], 10) == [1, 2]


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("short", 100) == "short"

    def test_long_text_truncated(self):
        text = "x" * 200
        result = _truncate(text, 50)
        assert len(result) < 200
        assert "[truncated" in result

    def test_max_chars_zero_no_truncation(self):
        text = "x" * 200
        assert _truncate(text, 0) == text


# ═══════════════════════════════════════════════════════════════
# Render Tests
# ═══════════════════════════════════════════════════════════════

class TestRender:
    def test_json_format(self):
        result = render({"a": 1}, fmt="json")
        assert json.loads(result) == {"a": 1}

    def test_compact_format(self):
        result = render([{"name": "x"}], fmt="compact")
        assert result == "x"

    def test_toon_format(self):
        """--toon now uses standard TOON encoder."""
        result = render({"ok": True}, fmt="toon")
        assert "true" in result
        assert "ok" in result

    def test_mcptoon_format(self):
        """--mcptoon uses legacy pipe format."""
        result = render({"ok": True}, fmt="mcptoon")
        assert result == "ok:true"

    def test_raw_format_string(self):
        assert render("raw text", fmt="raw") == "raw text"

    def test_head_n(self):
        result = render([1, 2, 3, 4, 5], fmt="json", head_n=2)
        assert json.loads(result) == [1, 2]

    def test_max_chars(self):
        result = render("x" * 200, fmt="json", max_chars=50)
        assert "[truncated" in result

    def test_full_disables_truncation(self):
        result = render("x" * 200, fmt="json", full=True)
        assert "[truncated" not in result

    def test_auto_format_default(self):
        result = render({"a": 1}, fmt="auto")
        assert "a" in result

    def test_slim_format(self):
        tool = {"name": "search", "inputSchema": {
            "properties": {"q": {"type": "string"}}, "required": ["q"]}}
        result = render([tool], fmt="slim")
        assert "search|q:s*" in result

    def test_slim_format_truncation(self):
        tools = []
        for i in range(100):
            tools.append({"name": f"tool_{i}", "inputSchema": {
                "properties": {"param": {"type": "string"}}}})
        result = render(tools, fmt="slim", max_chars=50)
        assert "[truncated" in result

    def test_slim_format_full(self):
        tool = {"name": "x", "inputSchema": {"properties": {"p": {"type": "string"}}}}
        result = render([tool], fmt="slim", full=True)
        assert "x|p:s" in result

    def test_mcptoon_format_with_url(self):
        """Ensure --mcptoon doesn't mangle URLs."""
        result = render({"url": "https://example.com"}, fmt="mcptoon")
        assert "example.com" in result
        assert "\\c" in result  # Colon escaped, not replaced
