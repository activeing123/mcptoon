# Copyright 2025-2026 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the specific language
# governing permissions and limitations under the License.

"""Tests for schema cache content fingerprinting and staleness handling."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mcptoon import cache as c


def _tools(names_reqs):
    return [{"name": n, "inputSchema": {"type": "object", "required": list(r)}}
            for n, r in names_reqs]


class CacheIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_file = Path(self._tmp.name) / "schema_cache.json"
        p1 = mock.patch.object(c, "_CACHE_FILE", self.cache_file)
        p2 = mock.patch.object(c, "_LOCK_FILE", Path(self._tmp.name) / "lock")
        p1.start()
        p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)
        self.addCleanup(self._tmp.cleanup)


class TestFingerprint(CacheIsolated):
    def test_fingerprint_stable_and_content_sensitive(self):
        a = c.tools_fingerprint(_tools([("add", ["a", "b"])]))
        b = c.tools_fingerprint(_tools([("add", ["a", "b"])]))
        self.assertEqual(a, b, "same surface -> same signature")
        # required-arg change flips the signature
        d = c.tools_fingerprint(_tools([("add", ["a"])]))
        self.assertNotEqual(a, d)
        # added tool flips it
        e = c.tools_fingerprint(_tools([("add", ["a", "b"]), ("mul", ["x"])]))
        self.assertNotEqual(a, e)

    def test_set_reports_changed_only_on_surface_change(self):
        tools = _tools([("add", ["a", "b"])])
        self.assertTrue(c.set_cached_tools("s", tools), "first write counts as change")
        self.assertFalse(c.set_cached_tools("s", tools), "identical rewrite -> unchanged")
        self.assertTrue(c.set_cached_tools("s", _tools([("add", ["a", "b"]), ("del", ["id"])])),
                        "adding a tool -> changed")

    def test_cached_fingerprint_matches_last_set(self):
        tools = _tools([("add", ["a"])])
        c.set_cached_tools("s", tools)
        self.assertEqual(c.cached_fingerprint("s"), c.tools_fingerprint(tools))
        self.assertIsNone(c.cached_fingerprint("missing"))


class TestRevalidate(CacheIsolated):
    def test_note_revalidated_keeps_tools_and_clears_age(self):
        c.set_cached_tools("s", _tools([("add", ["a"])]))
        # age the entry past the default TTL
        data = c._load_cache()
        data["s"]["ts"] = time.time() - 99999
        c._save_cache(data)
        self.assertIsNone(c.get_cached_tools("s"), "expired -> not served")
        self.assertTrue(c.note_revalidated("s"), "watcher can refresh a live entry")
        self.assertIsNotNone(c.get_cached_tools("s"), "refresh -> fresh again")
        # tools content preserved by the heartbeat
        self.assertEqual([t["name"] for t in c.get_cached_tools("s")], ["add"])

    def test_note_revalidated_missing_entry_returns_false(self):
        self.assertFalse(c.note_revalidated("never-cached"))


if __name__ == "__main__":
    unittest.main()
