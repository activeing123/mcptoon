"""CCR — the retrieve half of compression (`ccr.py`).

Compression without a way back is a one-way door. These tests pin the door:
what goes in comes out byte-identical, handles are content-addressed, and every
failure mode degrades to a *reported status* instead of raising — a busy temp
file must never fail a tool call.

Retention changed in 0.8.9: entries no longer expire by default, so the tests
that used `ttl=0` as "expire immediately" now drive a fake clock. `ttl=0` means
"never expires" — the opposite of what it used to mean — because a store that
destroys data on a timer is not a store you can call lossless. See
`tests/test_ccr_lossless.py` for the contract that depends on this.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcptoon import ccr


class EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(
            os.environ,
            {"MCPTOON_CCR_DIR": self._tmp.name, "MCPTOON_CCR_TTL": ""},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _store_at(self, now: float, payload, **kw):
        """Store with a pinned clock, so age assertions need no sleep."""
        with mock.patch("mcptoon.ccr.time.time", return_value=now):
            return ccr.store(payload, **kw)

    def _at(self, now: float, handle: str):
        with mock.patch("mcptoon.ccr.time.time", return_value=now):
            return ccr.retrieve_status(handle)


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

    def test_status_set_is_closed(self):
        # Callers switch on these; the set is part of the API, not an accident.
        self.assertEqual(ccr.RETRIEVE_STATUSES, (
            "ok", "bad-handle", "never-stored", "expired", "unreadable"))
        self.assertEqual(self._at(1000.0, "../../etc/passwd")[0], "bad-handle")
        self.assertEqual(self._at(1000.0, "deadbeef0000")[0], "never-stored")


class TestTtl(EnvIsolated):
    def test_default_never_expires(self):
        """The load-bearing default: only eviction removes an entry, never a clock."""
        handle = self._store_at(1000.0, {"a": 1}, server="s", tool="t")
        # Ten years later, still readable.
        status, original = self._at(1000.0 + 315_360_000, handle)
        self.assertEqual(status, "ok")
        self.assertEqual(original, {"a": 1})

    def test_opt_in_ttl_reports_expired(self):
        handle = self._store_at(1000.0, {"a": 1}, server="s", tool="t", ttl=60)
        self.assertEqual(self._at(1030.0, handle)[0], "ok")
        self.assertEqual(self._at(1070.0, handle)[0], "expired")
        self.assertIsNone(ccr.retrieve(handle))

    def test_env_ttl_is_opt_in(self):
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_TTL": "120"}):
            handle = self._store_at(1000.0, {"a": 1}, server="s", tool="t")
            self.assertEqual(self._at(1100.0, handle)[0], "ok")
            self.assertEqual(self._at(1200.0, handle)[0], "expired")

    def test_sweep_removes_expired_only(self):
        expired = self._store_at(1000.0, {"a": 1}, server="s", tool="t", ttl=60)
        keeper = self._store_at(1000.0, {"a": 2}, server="s", tool="t")
        with mock.patch("mcptoon.ccr.time.time", return_value=1200.0):
            self.assertEqual(ccr.sweep(), 1)
            self.assertEqual(ccr.stats()["count"], 1)
            self.assertEqual(ccr.retrieve_status(keeper)[0], "ok")
        self.assertIsNone(ccr.retrieve(expired))


class TestLimits(EnvIsolated):
    def test_oversize_reports_too_big(self):
        """Refused only when it could not fit the whole store budget anyway."""
        budget = ccr._max_store_bytes()
        huge = {"blob": "x" * (budget + 10)}
        outcome = ccr.store_ex(huge, server="s", tool="t")
        self.assertIsNone(outcome.handle)
        self.assertEqual(outcome.reason, ccr.REASON_TOO_BIG)
        self.assertGreater(outcome.bytes, budget)

    def test_large_payload_is_stored_now(self):
        """Over the *entry* size this used to refuse outright — that was the bug."""
        payload = {"blob": "x" * 1_200_000}
        outcome = ccr.store_ex(payload, server="s", tool="t")
        self.assertIsNotNone(outcome.handle)
        self.assertIsNone(outcome.reason)
        self.assertEqual(ccr.retrieve(outcome.handle), payload)

    def test_unserialisable_reports_reason(self):
        outcome = ccr.store_ex({"f": object()}, server="s", tool="t")
        self.assertIsNone(outcome.handle)
        self.assertEqual(outcome.reason, ccr.REASON_UNSERIALISABLE)

    def test_write_failure_reports_reason(self):
        with mock.patch("mcptoon.ccr.Path.write_text",
                        side_effect=OSError("disk full")):
            outcome = ccr.store_ex({"a": 1}, server="s", tool="t")
        self.assertIsNone(outcome.handle)
        self.assertEqual(outcome.reason, ccr.REASON_WRITE_FAILED)

    def test_store_still_returns_bare_handle(self):
        self.assertIsNotNone(ccr.store({"a": 1}, server="s", tool="t"))


class TestEviction(EnvIsolated):
    def test_evicted_entry_reports_never_stored(self):
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": "4000"}):
            old = ccr.store({"pad": "x" * 3000}, server="s", tool="t")
            self.assertEqual(ccr.retrieve_status(old)[0], "ok")
            for i in range(4):
                ccr.store({"pad": "y" * 3000, "i": i}, server="s", tool="t")
            status, original = ccr.retrieve_status(old)
            self.assertEqual(status, "never-stored")
            self.assertIsNone(original)


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

    def test_policy_shape(self):
        p = ccr.policy()
        self.assertEqual(set(p.keys()), {"ttl", "max_bytes", "session", "deduped"})
        self.assertEqual(p["ttl"], 0)


class TestSessions(EnvIsolated):
    def setUp(self):
        super().setUp()
        self.addCleanup(ccr.end_session, "s-test")

    def test_sent_set_is_per_session(self):
        ccr.begin_session("s-test")
        self.assertFalse(ccr.was_sent("abc123"))
        ccr.mark_sent("abc123")
        self.assertTrue(ccr.was_sent("abc123"))
        ccr.begin_session("s-other")
        self.assertFalse(ccr.was_sent("abc123"))

    def test_default_session_is_the_process(self):
        ccr.begin_session("")
        with mock.patch.dict(os.environ, {"MCPTOON_SESSION_ID": ""}):
            self.assertTrue(ccr.current_session().startswith("pid-"))

    def test_end_session_forgets_bookkeeping(self):
        handle = ccr.store({"a": 1}, server="s", tool="t")
        ccr.begin_session("s-test")
        ccr.mark_sent(handle)
        ccr.end_session("s-test")
        ccr.begin_session("s-test")
        self.assertFalse(ccr.was_sent(handle))
        # The payload itself survives — only the "have I sent it" memory is gone.
        self.assertEqual(ccr.retrieve(handle), {"a": 1})


if __name__ == "__main__":
    unittest.main()
