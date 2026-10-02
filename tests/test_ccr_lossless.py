"""The lossless contract for smart compression (`compressor.compress_with_ccr`).

Compression is allowed to **hide** information from the context. It is never
allowed to **destroy** it. Three measured failures used to break that (all
reproduced 2026-10-02, before the fix):

1. a payload over 1 MB was refused by the store *and* the compressed view carried
   no handle at all — 1,416,690 bytes went to 218 tokens with the notice saying
   "-52 items · 8 strings cut" and nowhere to go;
2. the default 5-minute TTL physically unlinked the original, so a handle went
   dead on a timer;
3. `retrieve` answered `None` for four different situations, so "you typed it
   wrong" and "that data is gone" were indistinguishable.

Each class below is one of those, plus the de-duplication shortcut that must not
be allowed to reintroduce any of them. The rule every test here enforces: for any
information withheld from the model, either the handle brings it back
byte-identical, or the notice says out loud that there is nothing to bring back.
Silence is the failure mode.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from mcptoon import ccr, compressor


def _search_result(rows: int = 60) -> list:
    """A realistic payload shape: a search hit list that compresses well."""
    return [{"path": f"src/mod{i}.py", "line": i, "text": "x" * 200}
            for i in range(rows)]


class LosslessBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {
            "MCPTOON_CCR_DIR": self._tmp.name,
            "MCPTOON_CCR_TTL": "",
            "MCPTOON_CCR_MAX_BYTES": "",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        # Every test starts a fresh conversation, so the de-dup shortcut can only
        # fire where the test intends it to.
        ccr.begin_session(f"lossless-{self.id()}")
        self.addCleanup(ccr.end_session, f"lossless-{self.id()}")
        compressor.reset_compressed_this_run()

    def _smart(self, payload, server="demo", tool="search"):
        text, stats = compressor.compress_with_ccr(payload, server=server, tool=tool)
        self.assertIsNotNone(text, "payload should compress for this test to mean anything")
        return text, stats

    @staticmethod
    def _handle_in(text: str) -> str | None:
        marker = "handle="
        if marker not in text:
            return None
        return text.split(marker, 1)[1].split()[0].rstrip("]")


class TestBoundary1Immediately(LosslessBase):
    """Just stored: the handle must return the payload byte-identical."""

    def test_roundtrip_is_byte_identical(self):
        payload = _search_result()
        text, stats = self._smart(payload)
        handle = self._handle_in(text)
        self.assertIsNotNone(handle)
        original = ccr.retrieve(handle)
        # Compare on the serialised form: that is exactly what the model gets.
        self.assertEqual(json.dumps(original, ensure_ascii=False),
                         json.dumps(payload, ensure_ascii=False))

    def test_various_shapes_roundtrip(self):
        shapes = {
            "long-text": {"body": "y" * 40_000},
            "nested": {"a": [{"b": {"c": ["z" * 300] * 60}}]},
            "log": "\n".join(f"2026-10-02 INFO step {i} ok" for i in range(400)),
            "list-obj": [{"i": i, "s": "q" * 120} for i in range(300)],
        }
        for name, payload in shapes.items():
            with self.subTest(shape=name):
                text, stats = compressor.compress_with_ccr(
                    payload, server="demo", tool=name)
                if text is None:
                    # Nothing was withheld, so there is nothing to lose — the
                    # payload passes through whole. Also a lossless outcome.
                    self.assertFalse(stats["applied"])
                    continue
                handle = self._handle_in(text)
                self.assertIsNotNone(handle, f"{name}: compressed with no way back")
                self.assertEqual(
                    json.dumps(ccr.retrieve(handle), ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False))


class TestBoundary2Expiry(LosslessBase):
    """The timer must not be the thing that loses data; eviction may be."""

    def test_no_ttl_means_still_retrievable_much_later(self):
        payload = _search_result()
        text, _ = self._smart(payload)
        handle = self._handle_in(text)
        # A day later — far past the old 300-second default.
        with mock.patch("mcptoon.ccr.time.time",
                        return_value=time.time() + 86_400):
            status, original = ccr.retrieve_status(handle)
        self.assertEqual(status, "ok")
        self.assertEqual(json.dumps(original, ensure_ascii=False),
                         json.dumps(payload, ensure_ascii=False))

    def test_opt_in_ttl_reports_expiry_rather_than_going_quiet(self):
        payload = _search_result()
        handle = ccr.store(payload, server="demo", tool="search", ttl=60)
        self.assertIsNotNone(handle)
        with mock.patch("mcptoon.ccr.time.time",
                        return_value=time.time() + 3600):
            status, original = ccr.retrieve_status(handle)
        self.assertEqual(status, "expired")
        self.assertIsNone(original)


class TestBoundary3Oversize(LosslessBase):
    """Over 1 MB: either it comes back whole, or the notice says it will not."""

    def test_oversize_payload_is_still_retrievable(self):
        payload = [{"i": i, "text": "A" * 2000} for i in range(700)]  # ~1.4 MB
        self.assertGreater(len(json.dumps(payload)), 1_000_000)
        text, stats = self._smart(payload, tool="dump")
        handle = self._handle_in(text)
        self.assertIsNotNone(handle, "1.4 MB payload compressed with no handle")
        self.assertEqual(json.dumps(ccr.retrieve(handle), ensure_ascii=False),
                         json.dumps(payload, ensure_ascii=False))

    def test_when_it_cannot_be_stored_the_notice_says_so(self):
        """The exact regression: trimmed view + no handle + no explanation."""
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": "5000"}):
            payload = [{"i": i, "text": "A" * 2000} for i in range(700)]
            text, stats = self._smart(payload, tool="dump")
        self.assertIsNone(self._handle_in(text))
        self.assertEqual(stats["store_reason"], ccr.REASON_TOO_BIG)
        self.assertIn("original not stored", text)
        self.assertIn("all there is", text)
        self.assertNotIn("mcptoon_retrieve", text)

    def test_a_truncated_view_never_claims_to_be_complete(self):
        """Either a handle, or the admission. Never neither."""
        for payload in (_search_result(), [{"i": i, "t": "A" * 2000} for i in range(700)]):
            with self.subTest(size=len(json.dumps(payload))):
                text, _ = self._smart(payload)
                self.assertTrue(
                    "mcptoon_retrieve handle=" in text or "all there is" in text,
                    "a trimmed view with neither a handle nor an admission")


class TestBoundary4Eviction(LosslessBase):
    """Evicted entries must fail loudly and specifically, never silently empty."""

    def test_a_returned_handle_always_points_at_a_readable_entry(self):
        """The property, over a store small enough to force eviction constantly.

        Found by attacking the 0.8.9 code: with the budget judged on the *payload*
        size, a 5,911-byte payload under a 6,000-byte budget was written, then
        deleted by that same call's eviction pass (the wrapper pushes the file
        past the budget), and `store_ex` returned a handle anyway — the store was
        left with zero files. Judging by the bytes actually written fixes the
        arithmetic; exempting the new entry from its own eviction pass fixes the
        mtime-tie case, where "newest" is a guess.
        """
        budget = 8000
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": str(budget)}):
            for i in range(12):
                payload = [{"i": i, "n": j, "t": "D" * 400} for j in range(i + 2)]
                outcome = ccr.store_ex(payload, server="demo", tool=f"t{i}")
                if outcome.handle is None:
                    continue
                with self.subTest(i=i, handle=outcome.handle):
                    status, original = ccr.retrieve_status(outcome.handle)
                    self.assertEqual(
                        status, "ok",
                        f"store_ex returned {outcome.handle} but it reads as {status}")
                    self.assertEqual(json.dumps(original, ensure_ascii=False),
                                     json.dumps(payload, ensure_ascii=False))

    def test_eviction_spares_the_entry_it_was_asked_to_keep(self):
        """Directly: a backdated 'newest' entry still survives its own eviction."""
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": "12000"}):
            fresh = [{"n": i, "t": "N" * 3000} for i in range(2)]
            handle = ccr.store(fresh, server="demo", tool="fresh")
            self.assertIsNotNone(handle)

            # Make the new entry the *oldest* by mtime, so nothing but `keep`
            # can save it.
            path = ccr._store_dir() / f"{handle}.json"
            ancient = time.time() - 10_000
            os.utime(path, (ancient, ancient))

            # Push the store over budget without going through `store`, because
            # `store` runs its own eviction pass and would leave it under budget
            # again before the call under test.
            decoy = ccr._store_dir() / "decoy0000.json"
            decoy.write_text(json.dumps({"original": "D" * 9000}), encoding="utf-8")
            total = sum(p.stat().st_size for p in ccr._store_dir().glob("*.json"))
            self.assertGreater(total, 12000)

            removed = ccr._maybe_evict(keep=handle)
            self.assertGreater(removed, 0, "the pass should have evicted the decoy")
            self.assertTrue(path.exists(), "eviction deleted the entry it was told to keep")
            self.assertEqual(ccr.retrieve_status(handle)[0], "ok")

    def test_budget_is_judged_on_the_bytes_written(self):
        """A payload that 'fits' but whose file does not must be refused, not lost."""
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": "1500"}):
            # Payload clearly under the budget; the JSON wrapper pushes it over.
            payload = {"pad": "b" * 1400}
            outcome = ccr.store_ex(payload, server="demo", tool="t")
            if outcome.handle is not None:
                # If it was accepted it must be readable — that is the invariant.
                self.assertEqual(ccr.retrieve_status(outcome.handle)[0], "ok")
            else:
                self.assertEqual(outcome.reason, ccr.REASON_TOO_BIG)
                self.assertGreater(outcome.bytes, 1500)

    def test_the_store_stays_within_budget_after_a_successful_store(self):
        budget = 9000
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": str(budget)}):
            for i in range(8):
                ccr.store([{"i": i, "t": "S" * 2000}], server="demo", tool=f"s{i}")
            total = sum(p.stat().st_size for p in ccr._store_dir().glob("*.json"))
        self.assertLessEqual(total, budget,
                             "eviction left the store over its own budget")

    def test_evicted_handle_reports_never_stored(self):
        # Budget fits the payload, then one more pushes it over. The first entry
        # is backdated so eviction order does not depend on two files sharing an
        # mtime tick.
        with mock.patch.dict(os.environ, {"MCPTOON_CCR_MAX_BYTES": "20000"}):
            payload = _search_result()
            text, _ = self._smart(payload)
            handle = self._handle_in(text)
            self.assertIsNotNone(handle)
            self.assertEqual(ccr.retrieve_status(handle)[0], "ok")

            path = ccr._store_dir() / f"{handle}.json"
            old = time.time() - 3600
            os.utime(path, (old, old))

            ccr.store(_search_result(61), server="demo", tool="search")
            status, original = ccr.retrieve_status(handle)
        self.assertEqual(status, "never-stored")
        self.assertIsNone(original)

    def test_retrieve_tool_answers_with_a_reason(self):
        from mcptoon import native_tools
        out = native_tools._retrieve({"handle": "deadbeef1234"}, {})
        self.assertFalse(out["found"])
        self.assertEqual(out["status"], "never-stored")
        self.assertIn("evicted", out["notice"])

        out = native_tools._retrieve({"handle": "../../etc/passwd"}, {})
        self.assertEqual(out["status"], "bad-handle")
        self.assertNotIn("evicted", out["notice"])

        out = native_tools._retrieve({}, {})
        self.assertEqual(out["status"], "bad-handle")

    def test_successful_retrieve_reports_ok(self):
        from mcptoon import native_tools
        handle = ccr.store({"a": 1}, server="s", tool="t")
        out = native_tools._retrieve({"handle": handle}, {})
        self.assertTrue(out["found"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["original"], {"a": 1})


class TestSessionDedup(LosslessBase):
    """The saving: the same payload twice in one conversation is sent once."""

    def test_second_identical_call_sends_a_reference_not_a_body(self):
        payload = _search_result()
        first, _ = self._smart(payload)
        second, stats = self._smart(payload)

        self.assertIn("mcptoon_retrieve handle=", second)
        self.assertTrue(stats["deduped"])
        self.assertLess(len(second), len(first) // 4,
                        f"second send was {len(second)} chars vs first {len(first)}")

    def test_the_reference_still_gets_the_original_back(self):
        """De-dup must not lose anything: the handle in the reference works."""
        payload = _search_result()
        first, _ = self._smart(payload)
        second, _ = self._smart(payload)
        handle = self._handle_in(second)
        self.assertEqual(handle, self._handle_in(first))
        self.assertEqual(json.dumps(ccr.retrieve(handle), ensure_ascii=False),
                         json.dumps(payload, ensure_ascii=False))

    def test_dedup_is_scoped_to_one_session(self):
        payload = _search_result()
        first, _ = self._smart(payload)
        # A different conversation has never seen this payload, so it must get the
        # body — "same as before" would reference something it never saw.
        ccr.begin_session("a-different-conversation")
        third, stats = self._smart(payload)
        self.assertFalse(stats.get("deduped"))
        self.assertEqual(len(third), len(first))

    def test_deduped_count_is_reported(self):
        before = ccr.deduped_count()
        payload = _search_result()
        self._smart(payload)
        self._smart(payload)
        self._smart(payload)
        self.assertEqual(ccr.deduped_count() - before, 2)

    def test_different_payloads_are_not_deduped(self):
        a, _ = self._smart(_search_result(60), tool="a")
        b, stats = self._smart(_search_result(61), tool="b")
        self.assertFalse(stats.get("deduped"))
        self.assertNotEqual(self._handle_in(a), self._handle_in(b))

    def test_dedup_survives_the_store_being_re_entered(self):
        """Storing twice is idempotent, so the second store must not reset the set."""
        payload = _search_result()
        handle1 = ccr.store(payload, server="demo", tool="search")
        ccr.mark_sent(handle1)
        self._smart(payload)
        self.assertTrue(ccr.was_sent(handle1))


class TestSessionIsolation(LosslessBase):
    """De-duplication must never claim a conversation saw something it did not."""

    def test_dedup_off_when_the_caller_cannot_name_the_conversation(self):
        payload = _search_result()
        ccr.begin_session(None, dedup=False)
        first, _ = self._smart(payload)
        second, stats = self._smart(payload)
        self.assertFalse(stats.get("deduped"))
        self.assertEqual(len(first), len(second))

    def test_unnamed_session_allocates_nothing(self):
        ccr.begin_session(None, dedup=False)
        payload = _search_result()
        self._smart(payload)
        self.assertEqual(ccr.deduped_count(), 0)

    def test_two_threads_do_not_steal_each_others_session(self):
        """One HTTP process serves several agents; a process-wide id would leak."""
        payload = _search_result()
        seen: dict[str, bool] = {}
        errors: list[Exception] = []

        def work(name: str) -> None:
            try:
                ccr.begin_session(name)
                # Both threads compress the *same* payload, which is the trap: if
                # the id were shared, the second thread would be told "already
                # sent" for a body its own agent never received.
                _, stats = compressor.compress_with_ccr(
                    payload, server="demo", tool="search")
                seen[name] = bool(stats.get("deduped"))
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(f"agent-{i}",))
                   for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(seen, {"agent-0": False, "agent-1": False})

    def test_same_thread_repeats_are_still_deduped(self):
        ccr.begin_session("repeat-on-this-thread")
        payload = _search_result()
        self._smart(payload)
        _, stats = self._smart(payload)
        self.assertTrue(stats["deduped"])


class TestNoticeHonesty(LosslessBase):
    def test_no_notice_when_nothing_was_compressed(self):
        stats = compressor.compress("short")[1]
        self.assertFalse(stats["applied"])
        self.assertEqual(compressor.notice(stats, None), "")

    def test_notice_states_the_numbers_it_saved(self):
        text, stats = self._smart(_search_result())
        self.assertIn(f"{stats['before_tokens']}\u2192{stats['after_tokens']} tok", text)
        self.assertIn(f"\u2212{stats['pct']}%", text)


if __name__ == "__main__":
    unittest.main()
