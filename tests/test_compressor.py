"""Structure-aware compression (`compressor.py`) — the Headroom idea, stdlib-only.

The contract these tests pin is the one that makes compression safe to ship:
the navigation survives (keys, structure, scalar types) while the payload is
compressed, the operation is idempotent, and payloads that must never be touched
(binary/base64) are refused. Compression that loses a key is not compression,
it is data loss with a smaller token count.
"""

from __future__ import annotations

import json
import unittest

from mcptoon import compressor as C


def search_rows(n=25):
    return [
        {
            "path": f"src/module_{i}/handler.py",
            "line": 100 + i,
            "score": round(0.99 - i * 0.01, 3),
            "snippet": "def handle_request(self, req):  # a long context line " * 6,
            "matched_terms": ["request", "handler", "timeout"],
            "language": "python",
            "is_vendor": False,
            "extra": None,
        }
        for i in range(n)
    ]


class TestInvariants(unittest.TestCase):
    def test_keys_preserved(self):
        rows = search_rows()
        out, _ = C.compress(rows)
        self.assertEqual(set(rows[0].keys()), set(out[0].keys()))

    def test_scalars_intact(self):
        rows = search_rows()
        out, _ = C.compress(rows)
        self.assertIs(out[0]["is_vendor"], False)
        self.assertIsNone(out[0]["extra"])
        self.assertIsInstance(out[0]["line"], int)
        self.assertIsInstance(out[0]["score"], float)

    def test_valid_json_out(self):
        out, _ = C.compress(search_rows())
        self.assertIsInstance(json.loads(json.dumps(out)), list)

    def test_idempotent(self):
        out, st1 = C.compress(search_rows())
        out2, st2 = C.compress(out)
        self.assertLessEqual(st2["after_tokens"], st1["after_tokens"] + 2)

    def test_actually_compresses(self):
        _, st = C.compress(search_rows())
        self.assertTrue(st["applied"])
        self.assertGreater(st["pct"], 50)

    def test_nested_keys_preserved(self):
        obj = {"a": {"b": {"c": "x" * 500}}, "keep": [{"k": 1, "v": "y" * 400}]}
        out, _ = C.compress(obj)
        self.assertEqual(set(out.keys()), {"a", "keep"})
        self.assertEqual(set(out["a"].keys()), {"b"})
        self.assertEqual(set(out["a"]["b"].keys()), {"c"})
        self.assertEqual(set(out["keep"][0].keys()), {"k", "v"})


class TestKindDetection(unittest.TestCase):
    def test_search(self):
        self.assertEqual(C.detect_kind(search_rows()), "search")

    def test_log(self):
        text = "\n".join(f"2026-09-26 10:00:0{i} INFO request served" for i in range(10))
        self.assertEqual(C.detect_kind(text), "log")

    def test_binary(self):
        self.assertEqual(C.detect_kind("data:image/png;base64," + "A" * 400), "binary")

    def test_json(self):
        self.assertEqual(C.detect_kind({"a": 1, "b": [1, 2, 3]}), "json")

    def test_scalar(self):
        self.assertEqual(C.detect_kind(42), "scalar")


class TestSafety(unittest.TestCase):
    def test_binary_never_compressed(self):
        blob = "data:image/png;base64," + "A" * 5000
        out, st = C.compress(blob)
        self.assertFalse(st["applied"])
        self.assertEqual(out, blob)

    def test_short_payload_unchanged(self):
        obj = {"ok": True, "n": 1}
        out, st = C.compress(obj)
        self.assertEqual(out, obj)

    def test_log_dedup(self):
        text = "\n".join(["ERROR boom"] * 5 + ["INFO fine"] * 3)
        out, st = C.compress(text)
        self.assertIn("(x5)", out)
        self.assertIn("(x3)", out)
        self.assertGreater(st["merged_lines"], 0)

    def test_search_keeps_head(self):
        out, st = C.compress(search_rows(25))
        self.assertLessEqual(len(out), C.DEFAULT_KEEP_HEAD)
        self.assertGreater(st["dropped_items"], 0)

    def test_string_truncated_at_word_boundary(self):
        # A string is only crushed inside a compressible shape (a record with
        # enough keys); a lone long string is deliberately left intact.
        obj = {"s": "word " * 100, "a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
               "f": 6, "g": 7}
        out, _ = C.compress(obj)
        self.assertTrue(out["s"].endswith(C.ELLIPSIS))
        self.assertNotIn("  ", out["s"])


class TestEmbeddedJson(unittest.TestCase):
    def test_json_string_is_recursed_not_truncated(self):
        """MCP servers often ship JSON inside a text field; crush its structure."""
        import json as _json
        inner = [{"name": f"f{i}.py", "type": "file"} for i in range(40)]
        obj = {"content": _json.dumps(inner)}
        out, st = C.compress(obj)
        self.assertIsInstance(out["content"], list)
        self.assertTrue(st["applied"])

    def test_plain_string_in_a_record_is_truncated(self):
        obj = {"note": "x" * 500, "a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
               "f": 6, "g": 7}
        out, _ = C.compress(obj)
        self.assertIsInstance(out["note"], str)
        self.assertTrue(out["note"].endswith(C.ELLIPSIS))


class TestSafetyGate(unittest.TestCase):
    """The gate that makes compression safe to leave on by default."""

    def test_lone_long_string_is_not_compressed(self):
        out, st = C.compress("a long prose answer " * 200)
        self.assertFalse(st["applied"])

    def test_small_dict_with_one_long_string_is_not_compressed(self):
        obj = {"answer": "the full text of a document " * 100}
        out, st = C.compress(obj)
        self.assertFalse(st["applied"])
        self.assertEqual(out, obj)

    def test_record_with_many_keys_is_compressible(self):
        obj = {f"k{i}": "value " * 50 for i in range(10)}
        _, st = C.compress(obj)
        self.assertTrue(st["applied"])

    def test_list_payload_is_compressible(self):
        self.assertTrue(C.is_compressible([{"a": 1}, {"a": 2}]))

    def test_binary_is_not_compressible(self):
        self.assertFalse(C.is_compressible("data:image/png;base64," + "A" * 400))


class TestNotice(unittest.TestCase):
    def test_notice_has_handle(self):
        _, st = C.compress(search_rows())
        line = C.notice(st, "abc123def456")
        self.assertIn("mcptoon_retrieve", line)
        self.assertIn("abc123def456", line)

    def test_no_notice_when_not_applied(self):
        _, st = C.compress({"ok": True})
        self.assertEqual(C.notice(st, "x"), "")


if __name__ == "__main__":
    unittest.main()
