"""CCR — the retrieve half of compression (`ccr.py`).

Compression without a way back is a one-way door. These tests pin the door:
what goes in comes out byte-identical, handles are content-addressed, entries
expire, and every failure mode degrades to "not found" instead of raising — a
busy temp file must never fail a tool call.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mcptoon import ccr


class EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(
            os.environ, {"MCPTOON_CCR_DIR": self._tmp.name, "MCPTOON_CCR_TTL": "300"}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class TestRoundtrip(EnvIsolated):
    def test_store_retrieve_identical(self):
        payload = {"rows": [{"a": 1, "b": "x" * 500}], "n": 25}
        handle = ccr.store(payload, server="fs", tool="search")
        self.assertIsNotNone(handle)
        self.assertEqual(ccr.retrieve(handle), payload)

    def test_dedupe_same_handle(self):
        payload = {"a": 1}
        h1 = ccr.store(payload, server="s", tool="t")
        h2 = ccr.store(payload, server="s", tool="t")
        self.assertEqual(h1, h2)

    def test_different_content_different_handle(self):
        h1 = ccr.store({"a": 1}, server="s", tool="t")
        h2 = ccr.store({"a": 2}, server="s", tool="t")
        self.assertNotEqual(h1, h2)

    def test_missing_handle_returns_none(self):
        self.assertIsNone(ccr.retrieve("deadbeef0000"))

    def test_bad_handle_returns_none(self):
        self.assertIsNone(ccr.retrieve("../../etc/passwd"))
        self.assertIsNone(ccr.retrieve(""))
        self.assertIsNone(ccr.retrieve(None))


class TestTtl(EnvIsolated):
    def test_expired_returns_none(self):
        handle = ccr.store({"a": 1}, server="s", tool="t", ttl=0)
        time.sleep(0.01)
        self.assertIsNone(ccr.retrieve(handle))

    def test_sweep_removes_expired(self):
        ccr.store({"a": 1}, server="s", tool="t", ttl=0)
        ccr.store({"a": 2}, server="s", tool="t", ttl=300)
        time.sleep(0.01)
        self.assertEqual(ccr.sweep(), 1)
        self.assertEqual(ccr.stats()["count"], 1)


class TestLimits(EnvIsolated):
    def test_oversize_not_stored(self):
        huge = {"blob": "x" * (ccr._MAX_ENTRY_BYTES + 10)}
        self.assertIsNone(ccr.store(huge, server="s", tool="t"))

    def test_unserialisable_not_stored(self):
        self.assertIsNone(ccr.store({"f": object()}, server="s", tool="t"))


class TestAtomicity(EnvIsolated):
    def test_no_tmp_files_left(self):
        ccr.store({"a": 1}, server="s", tool="t")
        leftovers = list(Path(self._tmp.name).glob("*.tmp*"))
        self.assertEqual(leftovers, [])

    def test_stats_shape(self):
        ccr.store({"a": 1}, server="s", tool="t")
        s = ccr.stats()
        self.assertEqual(set(s.keys()), {"count", "bytes", "oldest_age"})
        self.assertEqual(s["count"], 1)


if __name__ == "__main__":
    unittest.main()
