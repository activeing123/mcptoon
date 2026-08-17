"""Cross-validation tests for standard TOON implementation.

Validates mcptoon's toon_encode/toon_decode against the documented TOON spec
(toon-format/toon — Token-Oriented Object Notation).

Spec summary (from official docs + community analysis):
  - Objects: key: value (YAML-style, one per line)
  - Nested objects: indented key: value under parent
  - Uniform object arrays: key[N]{f1,f2}:\\n v1a,v1b\\n v2a,v2b (CSV-style)
  - Scalar arrays: key[N]: v1,v2,v3 or one-per-line
  - Bool: true / false
  - Null: null
  - Strings: no quotes needed (commas in values → quoted)
  - Round-trip safe: decode(encode(x)) == x

References:
  - 博客园/deephub: "TOON全称Token-Oriented Object Notation"
  - 游乐网: "借鉴YAML的缩进风格与CSV的行式布局"
  - 博客园/xueweihan: "官方开源的TypeScript实现在GitHub上一周便斩获了3.5k Star"
  - 博客园/token-ai: "TOON同时做到更省Token、更稳的解析/检索、更易于写提示词"
"""
from mcptoon.output import toon_encode, toon_decode


class TestToonSpecConformance:
    """Tests against the documented TOON spec behaviors."""

    # ─── Object encoding (YAML-style) ───

    def test_object_key_value(self):
        """Spec: Objects use key: value, one per line."""
        result = toon_encode({"name": "search"})
        assert result == "name: search"

    def test_object_multiple_keys(self):
        """Spec: Multiple keys on separate lines."""
        result = toon_encode({"name": "search", "count": 3})
        assert "name: search" in result
        assert "count: 3" in result
        assert "\n" in result

    def test_nested_object_indentation(self):
        """Spec: Nested objects use indented key: value."""
        result = toon_encode({"config": {"host": "localhost", "port": 8080}})
        assert "config:" in result
        # Nested keys should be indented
        lines = result.split("\n")
        nested_lines = [l for l in lines if "host:" in l or "port:" in l]
        assert all(l.startswith("  ") for l in nested_lines)

    # ─── Scalar values ───

    def test_bool_true(self):
        """Spec: Boolean true → 'true'."""
        assert "true" in toon_encode({"ok": True})

    def test_bool_false(self):
        """Spec: Boolean false → 'false'."""
        assert "false" in toon_encode({"ok": False})

    def test_null(self):
        """Spec: Null → 'null'."""
        assert "null" in toon_encode({"err": None})

    def test_integer(self):
        """Spec: Numbers are literal."""
        assert "42" in toon_encode({"count": 42})

    def test_float(self):
        """Spec: Numbers are literal."""
        assert "3.14" in toon_encode({"pi": 3.14})

    # ─── String escaping (CSV-style) ───

    def test_string_with_comma_quoted(self):
        """Spec: Strings with commas are quoted (CSV-style)."""
        result = toon_encode({"desc": "hello, world"})
        assert '"hello, world"' in result

    def test_string_with_quote_escaped(self):
        """Spec: Internal quotes are doubled (CSV-style)."""
        result = toon_encode({"desc": 'say "hi"'})
        assert '""hi""' in result

    def test_url_preserved(self):
        """Spec: URLs should not be mangled."""
        result = toon_encode({"url": "https://example.com"})
        assert "https://example.com" in result

    # ─── Array encoding (CSV-style for uniform objects) ───

    def test_uniform_object_array_csv_style(self):
        """Spec: Uniform object arrays use key[N]{f1,f2}: + CSV rows."""
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = toon_encode(data)
        assert "[2]{id,name}:" in result
        assert "1,Alice" in result
        assert "2,Bob" in result

    def test_uniform_array_in_dict(self):
        """Spec: Arrays in dicts also use CSV-style."""
        data = {"users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]}
        result = toon_encode(data)
        assert "users[2]{id,name}:" in result

    def test_scalar_array(self):
        """Spec: Scalar arrays use key[N]: + values."""
        result = toon_encode({"tags": ["ai", "ml", "nlp"]})
        assert "tags[3]:" in result

    def test_mixed_type_array(self):
        """Spec: Mixed-type arrays use one value per line."""
        data = {"items": [1, "hello", True]}
        result = toon_encode(data)
        assert "items[3]:" in result

    # ─── Empty containers ───

    def test_empty_dict(self):
        assert toon_encode({}) == "{}"

    def test_empty_list(self):
        assert toon_encode([]) == "[]"

    # ─── Round-trip (decode(encode(x)) == x) ───

    def test_roundtrip_simple_dict(self):
        original = {"name": "search", "count": 3}
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_bool_null(self):
        original = {"ok": True, "err": None}
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_url(self):
        original = {"url": "https://example.com"}
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_nested_dict(self):
        original = {"config": {"host": "localhost", "port": 8080}}
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_uniform_array(self):
        original = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_string_with_comma(self):
        original = {"desc": "hello, world"}
        assert toon_decode(toon_encode(original)) == original

    def test_roundtrip_int_float(self):
        original = {"count": 42, "pi": 3.14}
        assert toon_decode(toon_encode(original)) == original

    # ─── Edge cases ───

    def test_empty_string_decode(self):
        assert toon_decode("") is None

    def test_none_decode(self):
        assert toon_decode(None) is None

    def test_string_passthrough(self):
        """Strings pass through unchanged."""
        assert toon_encode("hello") == "hello"

    def test_deeply_nested(self):
        """Deeply nested objects should work."""
        original = {"a": {"b": {"c": {"d": "deep"}}}}
        encoded = toon_encode(original)
        decoded = toon_decode(encoded)
        assert decoded == original


class TestToonTokenEfficiency:
    """Verify that TOON actually saves tokens vs JSON."""

    def test_simple_dict_saves_tokens(self):
        """TOON should be shorter than JSON for simple dicts."""
        data = {"name": "search", "count": 3, "active": True, "err": None}
        toon_len = len(toon_encode(data))
        import json
        json_len = len(json.dumps(data))
        assert toon_len < json_len

    def test_uniform_array_saves_tokens(self):
        """TOON CSV-style arrays should be much shorter than JSON."""
        data = [
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Charlie", "role": "user"},
        ]
        toon_len = len(toon_encode(data))
        import json
        json_len = len(json.dumps(data))
        assert toon_len < json_len * 0.7  # At least 30% shorter

    def test_nested_object_saves_tokens(self):
        """TOON should be shorter for nested objects."""
        data = {
            "server": "github",
            "config": {"host": "api.github.com", "port": 443, "ssl": True},
            "tools": ["search", "fetch", "create"],
        }
        toon_len = len(toon_encode(data))
        import json
        json_len = len(json.dumps(data))
        assert toon_len < json_len
