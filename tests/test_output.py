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

"""Tests for mcptoon output module — TOON format and rendering."""
import json
import os
import pytest

from mcptoon.output import toon, compact, render, _toon_scalar, _toon_value, head, _truncate


class TestToonScalar:
    def test_bool_true(self):
        assert _toon_scalar(True) == "T"

    def test_bool_false(self):
        assert _toon_scalar(False) == "F"

    def test_none(self):
        assert _toon_scalar(None) == "∅"

    def test_int(self):
        assert _toon_scalar(42) == "42"

    def test_float(self):
        assert _toon_scalar(3.14) == "3.14"

    def test_string(self):
        assert _toon_scalar("hello") == "hello"

    def test_string_with_colon(self):
        assert _toon_scalar("a:b") == "a＿b"

    def test_string_with_newline(self):
        assert _toon_scalar("line1\nline2") == "line1↲line2"

    def test_long_string_truncated(self):
        long_str = "x" * 300
        result = _toon_scalar(long_str)
        assert len(result) == 200


class TestToonValue:
    def test_empty_dict(self):
        assert _toon_value({}) == "{}"

    def test_simple_dict(self):
        result = _toon_value({"name": "search", "count": 3})
        assert "name:search" in result
        assert "count:3" in result
        assert "|" in result

    def test_dict_with_bool(self):
        assert _toon_value({"ok": True}) == "ok:T"

    def test_dict_with_none(self):
        assert _toon_value({"err": None}) == "err:∅"

    def test_empty_list(self):
        assert _toon_value([]) == "[]"

    def test_scalar_list(self):
        assert _toon_value([1, 2, 3]) == "1 2 3"

    def test_string_list(self):
        assert _toon_value(["a", "b", "c"]) == "a b c"

    def test_nested_dict_in_list(self):
        result = _toon_value([{"name": "x"}])
        assert "name:x" in result


class TestToon:
    def test_string_passthrough(self):
        assert toon("hello") == "hello"

    def test_dict(self):
        result = toon({"name": "search", "count": 3})
        assert "name:search" in result
        assert "count:3" in result

    def test_list_of_dicts(self):
        result = toon([{"name": "a"}, {"name": "b"}])
        assert "name:a" in result
        assert "name:b" in result
        assert "\n" in result

    def test_bool_and_null(self):
        assert toon({"ok": True, "err": None}) == "ok:T|err:∅"


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


class TestRender:
    def test_json_format(self):
        result = render({"a": 1}, fmt="json")
        assert json.loads(result) == {"a": 1}

    def test_compact_format(self):
        result = render([{"name": "x"}], fmt="compact")
        assert result == "x"

    def test_toon_format(self):
        result = render({"ok": True}, fmt="toon")
        assert result == "ok:T"

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
        # Without env var, should work without error
        result = render({"a": 1}, fmt="auto")
        assert "a" in result
