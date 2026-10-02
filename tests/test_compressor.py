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
        # Prose, not `"x" * 500`: a punctuation-free alphanumeric run of 64+ chars
        # is treated as an opaque blob (see _looks_binary) because at that shape it
        # is indistinguishable from base64, and slicing it would corrupt it. The
        # intent here is the other case — an ordinary text value that is not
        # embedded JSON, which must still be cut rather than recursed into.
        obj = {"note": "a plain note with words " * 40, "a": 1, "b": 2, "c": 3,
               "d": 4, "e": 5, "f": 6, "g": 7}
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


class TestOpaqueBlobsSurvive(unittest.TestCase):
    """Invariant 5, at every depth — found false by probing, not by reading.

    2026-10-02: the guard lived only in ``is_compressible``, which inspects the
    top-level type. A base64 blob sitting inside a list of records therefore sailed
    past it and was sliced at the string budget: a 400-character blob came back as
    121 characters ending in an ellipsis, and decoding that yields garbage. The
    module's own comment already said why that is the one thing not to do
    ("a truncated base64 blob is not smaller context, it is a corrupted image").
    """

    @staticmethod
    def blob(nbytes: int) -> str:
        import base64
        return base64.b64encode(bytes(i % 256 for i in range(nbytes))).decode()

    def shapes(self):
        blob = self.blob(300)
        return {
            "list of records": [{"id": i, "image": blob} for i in range(3)],
            "nested array": {"rows": [{"blob": blob} for _ in range(3)]},
            "data URI in a record": [
                {"id": i, "src": "data:image/png;base64," + self.blob(400)}
                for i in range(3)],
            "dict with eight keys": {**{f"k{i}": "v" for i in range(7)},
                                     "payload": blob},
        }

    def test_a_blob_inside_a_container_is_never_cut(self):
        blob = self.blob(300)
        for label, payload in self.shapes().items():
            with self.subTest(shape=label):
                out, _ = C.compress(payload)
                text = json.dumps(out, ensure_ascii=False)
                self.assertIn(blob, text,
                              f"{label}: the blob was truncated — it is now a "
                              f"corrupted binary the model cannot decode")

    def test_a_data_uri_inside_a_container_is_never_cut(self):
        payload = [{"id": i, "src": "data:image/png;base64," + self.blob(400)}
                   for i in range(3)]
        out, _ = C.compress(payload)
        self.assertIn("data:image/png;base64," + self.blob(400),
                      json.dumps(out, ensure_ascii=False))

    def test_a_short_blob_is_protected_too(self):
        """121..255 characters used to be sliced: the old floor described a payload
        size, not the shape being guarded."""
        blob = self.blob(120)          # 160 characters
        self.assertGreater(len(blob), C.DEFAULT_STR_BUDGET)
        self.assertLess(len(blob), 256)
        out, _ = C.compress([{"id": i, "image": blob} for i in range(3)])
        self.assertIn(blob, json.dumps(out, ensure_ascii=False))

    def test_prose_without_punctuation_is_still_compressed(self):
        """The guard must not become a tax on ordinary text.

        The alphabet it matches contains every letter, every digit and — until this
        was fixed — every space, so a 400-character run of punctuation-free prose
        was classified as binary and exempted from compression. Spaces are now
        evidence *against* a blob, which is what keeps this case working.
        """
        prose = "the quick brown fox jumps over the lazy dog " * 10
        self.assertFalse(C._looks_binary(prose))
        out, st = C.compress({"note": prose, "a": 1, "b": 2, "c": 3, "d": 4,
                              "e": 5, "f": 6, "g": 7})
        self.assertTrue(st["applied"])
        self.assertTrue(out["note"].endswith(C.ELLIPSIS))

    def test_wrapped_base64_still_counts_as_binary(self):
        """MIME wraps base64 at 76 characters with newlines, not spaces."""
        wrapped = "\n".join(self.blob(300)[i:i + 76] for i in range(0, 300, 76))
        self.assertTrue(C._looks_binary(wrapped))


class TestNotAppliedMeansUntouched(unittest.TestCase):
    """`applied` False must mean "the object you got is your input".

    Without this, every caller has to remember to consult the flag before trusting
    the value, and one already did not: `output.render` discarded the stats and
    rendered the crushed payload anyway. A payload can also be *changed* without
    getting smaller — a 121-character string becomes 120 characters plus the
    ellipsis: same length, same token count, different bytes.
    """

    def test_a_changed_but_not_smaller_payload_comes_back_unchanged(self):
        payload = [{"i": 0, "t": "x" * 121}, {"i": 1, "t": "y" * 121}]
        out, st = C.compress(payload)
        if st["applied"]:
            self.assertNotEqual(out, payload)          # a real shrink happened
        else:
            self.assertEqual(out, payload,
                             "compress() edited the payload while reporting "
                             "applied=False")

    def test_not_applied_always_returns_the_identical_object(self):
        cases = [
            {"ok": True},
            [{"a": 1}, {"a": 2}],
            "a long prose answer " * 200,
            [{"i": 0, "t": "x" * 121}, {"i": 1, "t": "y" * 121}],
            [{"id": 1, "image": TestOpaqueBlobsSurvive.blob(300)} for _ in range(3)],
            [],
        ]
        for payload in cases:
            with self.subTest(payload=repr(payload)[:60]):
                out, st = C.compress(payload)
                if not st["applied"]:
                    self.assertEqual(
                        json.dumps(out, ensure_ascii=False, sort_keys=True),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        "applied=False but the value differs")
                    self.assertEqual(st["saved_tokens"], 0)
                    self.assertEqual(st["truncated_strings"], 0)
                    self.assertEqual(st["dropped_items"], 0)

    def test_counters_are_zeroed_when_nothing_was_applied(self):
        """Reporting cuts that were not made would be a false statement in the
        numbers a caller uses to describe what happened."""
        obj = {"ok": True, "n": 1}
        _, st = C.compress(obj)
        self.assertFalse(st["applied"])
        self.assertEqual((st["truncated_strings"], st["dropped_items"],
                          st["deduped_items"], st["saved_tokens"], st["pct"]),
                         (0, 0, 0, 0, 0))


class TestNonFiniteNumbers(unittest.TestCase):
    """Invariant 3's real caliber: `json.dumps` succeeds, strict JSON does not.

    NaN and Infinity are emitted as bare tokens by json.dumps and rejected by
    JavaScript's JSON.parse. They are left alone deliberately — rewriting them as
    null would destroy a value, and losslessness outranks JSON purity. This test
    exists so the limit is recorded rather than discovered.
    """

    def test_nan_and_infinity_survive_as_themselves(self):
        payload = [{"i": 0, "f": float("nan")}, {"i": 1, "f": float("inf")}]
        out, _ = C.compress(payload)
        text = json.dumps(out, ensure_ascii=False)
        self.assertIn("NaN", text)
        self.assertIn("Infinity", text)
        with self.assertRaises(ValueError):
            json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        # Python's own parser accepts them by default, which is why this is a
        # documented limit and not a scramble to "fix" the data.
        import math
        self.assertTrue(math.isnan(json.loads(text)[0]["f"]))
        self.assertEqual(json.loads(text)[1]["f"], float("inf"))


if __name__ == "__main__":
    unittest.main()
