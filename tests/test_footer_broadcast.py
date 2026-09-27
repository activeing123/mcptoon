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

"""Tests for the two-line per-turn broadcast (2026-09-26).

The load-bearing claims: the skills half is counted at all (it never was), the
cumulative figure is *always* marked as an estimate (it is a lower bound, not a
measurement), and the change gate compares the figure lines rather than the
`note:` age that ticks every minute.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import footer as footer_mod  # noqa: E402


class _IsolatedState(unittest.TestCase):
    """Redirect the footer-state file so `changed()` cannot touch the real machine."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        patcher = patch.dict(os.environ, {
            "MCPTOON_SETTINGS_FILE": str(root / "settings.json"),
            "MCPTOON_CONFIG_FILE": str(root / "config.json"),
            "MCPTOON_CONFIG_FILE_TOML": str(root / "config.toml"),
            "MCPTOON_CACHE_DIR": str(root / "cache"),
            "MCPTOON_FOOTER_STATE_FILE": str(root / "footer-state.json"),
        }, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

_FACTS = {
    "servers": 12,
    "tools": 96,
    "tokens_full": 21074,
    "tokens_slim": 15955,
    "tokens_saved": 5119,
    "savings_pct": 24.3,
    "gateway_tokens": 2291,
    "gateway_pct": 89.1,
    "token_caliber": "tiktoken cl100k_base",
    "calls_recorded": 4000,
    "cache_age_seconds": 100.0,
    "servers_uncached": 0,
    "cache_ttl_seconds": 300,
    "skills": 409,
    "skills_tokens_full": 1030628,
    "skills_pointer_tokens": 39,
    "note": None,
}


class TestSkillsLine(unittest.TestCase):
    def test_the_skills_half_is_counted_at_all(self):
        """The footer only ever counted tools; skills were invisible."""
        out = footer_mod.skills_line(_FACTS, "zh")
        self.assertIsNotNone(out)
        self.assertIn("409", out)
        self.assertIn("1,030,628", out)
        self.assertIn("39", out)

    def test_the_skills_percentage_never_rounds_to_a_bare_100(self):
        """39/1,030,628 is 99.9962%; rounding it to `100%` reads as a typo."""
        out = footer_mod.skills_line(_FACTS, "zh")
        self.assertIn("99.99%", out)
        self.assertNotIn("100%", out)
        en = footer_mod.skills_line(_FACTS, "en")
        self.assertIn("99.99%", en)
        self.assertNotIn("100%", en)

    def test_the_report_pointer_and_the_skill_pointer_ride_here(self):
        """The cumulative estimate moved up to line 1 in the second 2026-09-26
        pass (it is the figure that moves, so it belongs where it is seen every
        turn); this line now carries the two entry points instead — `mcptoon
        report` for the omitted figures, `/mcptoon` for the explanation and the
        way back."""
        for lng in ("zh", "en"):
            out = footer_mod.skills_line(_FACTS, lng)
            self.assertIn("mcptoon report", out, out)
            self.assertIn("/mcptoon", out, out)

    def test_no_skill_catalog_means_no_skills_line(self):
        """A machine with no skills shows one line, not a zero dressed as a saving."""
        no_skills = dict(_FACTS, skills=0)
        self.assertIsNone(footer_mod.skills_line(no_skills, "en"))
        self.assertIsNone(footer_mod.skills_line(no_skills, "zh"))

    def test_a_skills_count_with_no_token_measurement_still_names_the_report(self):
        """A catalog that has a count but no measured bodies must not crash or
        print a fake percentage — it drops to the count plus the entry points."""
        partial = dict(_FACTS, skills_tokens_full=0)
        for lng in ("zh", "en"):
            out = footer_mod.skills_line(partial, lng)
            self.assertIsNotNone(out)
            self.assertIn("409", out)
            self.assertIn("/mcptoon", out)
            self.assertNotIn("%", out)

    def test_both_languages_say_it(self):
        zh = footer_mod.skills_line(_FACTS, "zh")
        en = footer_mod.skills_line(_FACTS, "en")
        self.assertIn("技能", zh)
        self.assertIn("skills", en)
        self.assertIn("1,030,628", en)


class TestCumulativeEstimate(unittest.TestCase):
    def test_the_estimate_is_calls_times_the_per_turn_saving(self):
        got = footer_mod._cumulative_estimate(_FACTS)
        self.assertEqual(got, (4000, 4000 * (21074 - 2291)))

    def test_the_estimate_is_absent_without_calls(self):
        self.assertIsNone(footer_mod._cumulative_estimate(dict(_FACTS, calls_recorded=0)))

    def test_the_line_always_marks_it_as_an_estimate(self):
        """It is a lower bound built on an assumption, so `≈` is not decoration.
        Since the second pass it rides on line 1 (it is the figure that moves)."""
        for lng in ("en", "zh"):
            out = footer_mod.line(_FACTS, lng)
            self.assertIn("≈", out, out)

    def test_the_estimate_scales_with_calls(self):
        a = footer_mod._cumulative_estimate(dict(_FACTS, calls_recorded=100))
        b = footer_mod._cumulative_estimate(dict(_FACTS, calls_recorded=200))
        self.assertEqual(b[1], a[1] * 2)

    def test_a_legacy_dict_without_gateway_gets_no_estimate(self):
        """No gateway figure → no per-turn saving to multiply → no estimate."""
        legacy = {k: v for k, v in _FACTS.items()
                  if k not in ("gateway_tokens", "gateway_pct")}
        self.assertNotIn("≈", footer_mod.line(legacy, "en"))
        self.assertNotIn("≈", footer_mod.skills_line(legacy, "en"))


class TestHumanTokens(unittest.TestCase):
    def test_it_is_short_enough_for_a_one_line_broadcast(self):
        self.assertEqual(footer_mod._human_tokens(76_484_376), "76M")
        self.assertEqual(footer_mod._human_tokens(4_273_042_784), "4.3B")
        self.assertEqual(footer_mod._human_tokens(12_345), "12,345")


class TestFloorPct(unittest.TestCase):
    def test_it_floors_rather_than_rounds(self):
        """39/1,030,628 is 99.9962%; rounding prints a "100%" that reads as a typo."""
        self.assertEqual(footer_mod.floor_pct(1_030_589, 1_030_628), 99.99)
        self.assertEqual(footer_mod.floor_pct(1_030_589, 1_030_628, 1), 99.9)

    def test_it_never_reaches_100_unless_it_really_is(self):
        self.assertEqual(footer_mod.floor_pct(100, 100), 100.0)
        self.assertLess(footer_mod.floor_pct(99_999, 100_000), 100.0)

    def test_nothing_to_divide_is_none_not_zero(self):
        self.assertIsNone(footer_mod.floor_pct(0, 100))
        self.assertIsNone(footer_mod.floor_pct(5, 0))
        self.assertIsNone(footer_mod.floor_pct(-1, 100))

    def test_the_footer_and_the_report_agree_on_the_same_pair(self):
        """The two surfaces must not print different percentages for one pair —
        that is the "same machine, two numbers" failure this project keeps fixing."""
        from mcptoon import report as report_mod

        out = report_mod.render({
            "caliber": "tiktoken cl100k_base",
            "tools_exposed": 8,
            "tools": {"count": 96, "servers": 12, "full_tokens": 21074,
                      "gateway_tokens": 2291, "gateway_pct": 89.1,
                      "slim_tokens": 15955, "slim_pct": 24.3},
            "skills": {"count": 409, "full_tokens": 1030628, "pointer_tokens": 39,
                       "resolve_tokens": 652},
            "per_turn": {"native_tokens": 1051702, "after_tokens": 2330,
                         "saved_pct": 99.8},
            "calls": {"total": 4142, "success_rate": "970/1000",
                      "result_tokens_lifetime": 132369},
            "note": None,
        }, "zh")
        # The report's pointer row and the footer's skills line quote the same pct.
        self.assertIn("99.99%", out)
        self.assertIn("99.99%", footer_mod.skills_line(_FACTS, "zh"))


class TestExposedToolCount(unittest.TestCase):
    def test_the_reduction_rides_on_the_tool_line(self):
        out = footer_mod.line(_FACTS, "zh")
        exposed = footer_mod._exposed_tool_count()
        if exposed:
            self.assertIn(f"→{exposed}", out)
            self.assertIn("96", out)


class TestSkillTokenCache(_IsolatedState):
    """The figures are cached by catalog signature, so a turn costs a stat walk.

    This is what makes the skills half affordable per turn at all: tokenizing the
    bodies is ~481 ms and 1,030,628 tokens on the reference machine, which the
    footer would pay every turn if it recomputed.
    """

    def setUp(self):
        super().setUp()
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        base = Path(self.tmp2.name)
        self.root = base / "root"
        (self.root / "alpha").mkdir(parents=True)
        (self.root / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: does alpha things\n---\n\nbody text\n",
            encoding="utf-8")
        patcher = patch.dict(os.environ, {
            "MCPTOON_SKILLS_INDEX": str(base / "idx.json"),
            "MCPTOON_SKILLS_ROOTS": str(self.root),
        }, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_computes_once_then_serves_the_cache(self):
        from mcptoon import skills as sk

        first = sk.cached_skill_token_figures()
        self.assertEqual(first.get("count"), 1)
        self.assertGreater(first.get("native_tokens"), 0)
        # The second call must not re-tokenize: it reads the sidecar.
        calls = []
        real = sk.skill_token_figures

        def spy(roots=None):
            calls.append(1)
            return real(roots)

        with patch.object(sk, "skill_token_figures", spy):
            second = sk.cached_skill_token_figures()
        self.assertEqual(calls, [], "a warm cache must not tokenize again")
        self.assertEqual(second, first)

    def test_the_signature_walk_is_skipped_inside_the_ttl(self):
        """The walk is ~400 ms here (symlink farms, ~9,800 files); inside the TTL
        the footer must not pay it, or every command pays it."""
        from mcptoon import skills as sk

        sk.cached_skill_token_figures()
        walks = []
        real = sk.catalog_signature

        def spy(roots):
            walks.append(1)
            return real(roots)

        with patch.object(sk, "catalog_signature", spy):
            sk.cached_skill_token_figures()
        self.assertEqual(walks, [], "inside the TTL the catalog is not re-walked")

    def test_an_expired_ttl_re_walks_but_keeps_an_unchanged_measurement(self):
        from mcptoon import skills as sk

        before = sk.cached_skill_token_figures()
        store = json.loads(sk._skill_token_cache_file().read_text(encoding="utf-8"))
        store["checked_at"] = 0  # long expired
        sk._skill_token_cache_file().write_text(json.dumps(store), encoding="utf-8")
        calls = []
        real = sk.skill_token_figures

        def spy(roots=None):
            calls.append(1)
            return real(roots)

        with patch.object(sk, "skill_token_figures", spy):
            after = sk.cached_skill_token_figures()
        self.assertEqual(calls, [], "an unchanged catalog is not re-measured")
        self.assertEqual(after, before)

    def test_a_changed_catalog_invalidates_the_cache(self):
        from mcptoon import skills as sk

        before = sk.cached_skill_token_figures()
        (self.root / "beta").mkdir()
        (self.root / "beta" / "SKILL.md").write_text(
            "---\nname: beta\ndescription: does beta things\n---\n\n" + "x" * 200 + "\n",
            encoding="utf-8")
        # Inside the TTL the walk is skipped on purpose (that is the whole point of
        # the timestamp), so expire it the way five minutes of wall clock would.
        store = json.loads(sk._skill_token_cache_file().read_text(encoding="utf-8"))
        store["checked_at"] = 0
        sk._skill_token_cache_file().write_text(json.dumps(store), encoding="utf-8")
        after = sk.cached_skill_token_figures()
        self.assertEqual(after.get("count"), 2)
        self.assertGreater(after.get("native_tokens"), before.get("native_tokens"))

    def test_the_sidecar_records_the_signature_and_when_it_was_checked(self):
        from mcptoon import skills as sk

        sk.cached_skill_token_figures()
        store = json.loads(sk._skill_token_cache_file().read_text(encoding="utf-8"))
        self.assertEqual(store["signature"], sk.catalog_signature([self.root]))
        self.assertIsInstance(store["checked_at"], (int, float))
        self.assertEqual(store["figures"]["count"], 1)

    def test_no_catalog_yields_no_figures_rather_than_a_zero(self):
        from mcptoon import skills as sk

        empty = Path(self.tmp2.name) / "nothing"
        with patch.dict(os.environ, {"MCPTOON_SKILLS_ROOTS": str(empty)}, clear=False):
            self.assertEqual(sk.cached_skill_token_figures(), {})


class TestCompressionLine(_IsolatedState):
    """The third axis: tool *results*, compressed by default since 2026-09-26."""

    def test_on_by_default_and_says_so(self):
        """A fresh install compresses redundant results — the line must say so."""
        out = footer_mod.compression_line({}, "zh")
        self.assertIn("已启用", out)
        self.assertIn("自动", out)

    def test_it_still_prints_when_explicitly_off(self):
        """"Off" is a fact the reader needs — the lever is theirs to pull."""
        from mcptoon import config as cfg

        with patch.object(cfg, "get_setting", lambda k: "off" if k == "compress" else "auto"):
            out = footer_mod.compression_line({}, "zh")
            self.assertIn("未启用", out)
            en = footer_mod.compression_line({}, "en")
        self.assertIn("off", en)

    def test_a_policy_means_on(self):
        from mcptoon import config as cfg

        with patch.object(cfg, "load_policies", lambda: {"srv:tool": "toon"}), \
                patch.object(cfg, "auto_smart_enabled", lambda: False):
            out = footer_mod.compression_line({}, "zh")
        self.assertIn("已启用", out)

    def test_the_agent_type_env_means_on(self):
        from mcptoon import config as cfg

        with patch.object(cfg, "auto_smart_enabled", lambda: False), \
                patch.dict(os.environ, {"MCPTOON_AGENT_TYPE": "claude"}, clear=False):
            out = footer_mod.compression_line({}, "zh")
        self.assertIn("已启用", out)

    def test_the_benchmark_pct_is_offered_not_claimed(self):
        """`~34%` is a benchmark, never a banked saving — it is only ever an offer."""
        from mcptoon import config as cfg

        with patch.object(cfg, "get_setting", lambda k: "off" if k == "compress" else "auto"):
            out = footer_mod.compression_line({}, "zh")
        self.assertIn("34%", out)
        self.assertIn("可省", out, "must read as an offer, not a result")

    def test_it_names_the_retrieve_path_when_idle(self):
        """Nothing compressed this run: the line still says the originals are
        recoverable, so a user who *thinks* something was compressed has a path."""
        from mcptoon import compressor as comp

        comp.reset_compressed_this_run()
        out = footer_mod.compression_line({}, "zh")
        self.assertIn("mcptoon_retrieve", out)
        self.assertNotIn("本轮已压缩", out)

    def test_it_says_so_when_this_run_compressed_something(self):
        """The 2026-09-26 requirement: a turn that actually compressed a result
        must point the user at the explanation — and *replace* the retrieve hint
        rather than append to it (the result itself already carries the handle, so
        appending would push the line past 80 columns)."""
        from mcptoon import compressor as comp

        comp.reset_compressed_this_run()
        comp._mark_applied()
        try:
            for lng, needle in (("zh", "本轮已压缩"), ("en", "compressed this turn")):
                out = footer_mod.compression_line({}, lng)
                self.assertIn(needle, out, out)
                self.assertIn("/mcptoon", out, out)
                self.assertNotIn("mcptoon_retrieve", out,
                                 "the retrieve hint is replaced, not appended")
        finally:
            comp.reset_compressed_this_run()


class TestHeadlineMovesWithCalls(unittest.TestCase):
    """Line 1 must *move* turn over turn — the counter is why it is worth reading."""

    def test_the_call_count_rides_on_line_one(self):
        facts = dict(_FACTS, calls_recorded=4407)
        for lng in ("zh", "en"):
            out = footer_mod.line(facts, lng)
            self.assertIn("4,407", out, out)

    def test_the_counter_is_not_rounded_to_thousands(self):
        """`4k` would only tick once per thousand calls — the line would look
        frozen again, which is the complaint this redesign answers."""
        a = footer_mod.line(dict(_FACTS, calls_recorded=4407), "zh")
        b = footer_mod.line(dict(_FACTS, calls_recorded=4408), "zh")
        self.assertNotEqual(a, b, "one more call must change the line")

    def test_it_moves_but_stays_inside_the_budget(self):
        import unicodedata

        def width(s: str) -> int:
            return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

        grown = dict(_FACTS, tools=1209, gateway_tokens=2499, gateway_pct=98.2,
                     skills=1209, skills_tokens_full=3031439, calls_recorded=90000)
        for lng in ("zh", "en"):
            for ln in footer_mod.block(grown, lng).splitlines():
                self.assertLessEqual(width(ln), 80, ln)


class TestBlockOrderAndGate(_IsolatedState):
    def test_block_order_is_tools_skills_compression_note(self):
        stale = dict(_FACTS, servers_uncached=1, cache_age_seconds=99999.0)
        block = footer_mod.block(stale, "zh")
        lines = block.splitlines()
        self.assertTrue(lines[0].startswith(footer_mod.MARK + " mcptoon:"), lines[0])
        self.assertTrue(lines[1].lstrip().startswith("技能"), lines[1])
        self.assertTrue(lines[2].lstrip().startswith("结果压缩"), lines[2])
        self.assertTrue(lines[3].startswith("note: "), lines[3])

    def test_the_gate_ignores_the_ticking_age(self):
        """A fresh `note:` age must not resurrect a byte-identical figure block."""
        figures = footer_mod._figures_of(footer_mod.block(_FACTS, "zh"))
        with_age_a = figures + "\nnote: 目录已 1 分钟没更新"
        with_age_b = figures + "\nnote: 目录已 99 分钟没更新"
        self.assertEqual(footer_mod._figures_of(with_age_a),
                         footer_mod._figures_of(with_age_b))
        self.assertIn("note: ", with_age_a)
        self.assertNotIn("note: ", footer_mod._figures_of(with_age_a))

    def test_an_identical_block_is_suppressed_and_a_new_one_is_not(self):
        """The real `changed`/`remember` round trip, on an isolated state file."""
        block = footer_mod.block(_FACTS, "zh")
        self.assertTrue(footer_mod.changed(block), "nothing shown yet -> always show")
        footer_mod.remember(block)
        self.assertFalse(footer_mod.changed(block), "byte-identical figures -> silent")
        # Only the age changed: still silent, or the line reappears every minute.
        self.assertFalse(footer_mod.changed(block + "\nnote: 目录已 42 分钟没更新"))
        # The cumulative estimate is rendered to two significant-ish digits (`75M`),
        # so one more call does not move it. Step it enough to cross that boundary.
        moved = footer_mod.block(dict(_FACTS, calls_recorded=4500), "zh")
        self.assertTrue(footer_mod.changed(moved), "a moved figure must be shown")

    def test_a_real_figure_change_is_seen(self):
        a = footer_mod.block(_FACTS, "zh")
        b = footer_mod.block(dict(_FACTS, calls_recorded=4500), "zh")
        self.assertNotEqual(footer_mod._figures_of(a), footer_mod._figures_of(b))

    def test_the_skills_change_alone_is_seen(self):
        """A catalog edit must surface even when the tool figures are unchanged."""
        a = footer_mod.block(_FACTS, "zh")
        b = footer_mod.block(dict(_FACTS, skills=410, skills_tokens_full=1031000), "zh")
        self.assertNotEqual(footer_mod._figures_of(a), footer_mod._figures_of(b))


class TestLineWidthBudget(unittest.TestCase):
    """Every line fits 80 display columns, so nothing wraps on a normal terminal.

    This is the invariant the 2026-09-26 redesign exists for: the *previous* line
    put five figures on one line and measured 166 columns, wrapping to three rows
    on every turn. Width, not word count, is the binding constraint, so it is
    pinned here. CJK glyphs are double-width (`unicodedata.east_asian_width` in
    `WF`), which is why a Chinese line that looks short can still wrap.
    """

    @staticmethod
    def _width(s: str) -> int:
        import unicodedata

        return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)

    def _assert_fits(self, block: str, label: str) -> None:
        for ln in block.splitlines():
            w = self._width(ln)
            self.assertLessEqual(w, 80, f"{label}: {w} cols (wraps): {ln!r}")

    def _every_state(self) -> list[tuple[str, dict]]:
        """The broadcast in every state a real machine reaches, incl. growth."""
        # A machine that has grown: more tools, more skills, a bigger cumulative.
        grown = dict(_FACTS, tools=1209, tokens_full=141074, gateway_tokens=2499,
                     gateway_pct=98.2, skills=1209, skills_tokens_full=3031439,
                     calls_recorded=90000)
        # No gateway measurement: a catalog smaller than the gateway footprint, or
        # a legacy `--json` payload. This is the *fresh install* state, and the
        # branch that used to render the 143-column raw-pair line.
        no_gateway = {k: v for k, v in _FACTS.items()
                      if k not in ("gateway_tokens", "gateway_pct", "gateway_saved")}
        no_gateway["calls_recorded"] = 0
        return [
            ("normal", _FACTS),
            ("uncached", dict(_FACTS, servers_uncached=1, cache_age_seconds=99999.0)),
            ("stale+cached", dict(_FACTS, cache_age_seconds=99999.0)),
            ("no skills", dict(_FACTS, skills=0)),
            ("no calls", dict(_FACTS, calls_recorded=0)),
            ("fresh", dict(_FACTS, cache_age_seconds=1.0)),
            ("grown", grown),
            ("no gateway", no_gateway),
            # `pip install mcptoon` with zero dependencies: tiktoken is absent, so
            # the caliber is the long fallback string. It used to blow the budget
            # on the gateway branch too, where the test only ever used the short
            # tiktoken name.
            ("no tiktoken", dict(_FACTS, token_caliber="chars/4 estimate")),
            ("no gateway, no tiktoken",
             dict(no_gateway, token_caliber="chars/4 estimate")),
        ]

    def test_every_line_fits_in_every_state(self):
        for label, facts in self._every_state():
            for lng in ("zh", "en"):
                self._assert_fits(footer_mod.block(facts, lng), f"{label}/{lng}")

    def test_the_compressed_hint_also_fits(self):
        """The third line changes shape when this run compressed something; that
        state must fit the budget too (it replaces the retrieve hint, it does not
        append to it)."""
        from mcptoon import compressor as comp

        comp.reset_compressed_this_run()
        comp._mark_applied()
        try:
            for label, facts in self._every_state():
                for lng in ("zh", "en"):
                    self._assert_fits(footer_mod.block(facts, lng),
                                      f"compressed/{label}/{lng}")
        finally:
            comp.reset_compressed_this_run()

    def test_the_headline_line_alone_fits(self):
        for label, facts in self._every_state():
            for lng in ("zh", "en"):
                self._assert_fits(footer_mod.line(facts, lng), f"{label}/{lng}")

    def test_the_caliber_suffix_survives_on_the_headline(self):
        """The `[caliber]` handle is load-bearing for parsers; it stays on line 1."""
        for lng in ("zh", "en"):
            out = footer_mod.line(_FACTS, lng)
            self.assertTrue(out.endswith("[tiktoken cl100k_base]"), out)

    def test_the_headline_fits_on_a_machine_without_tiktoken(self):
        """The zero-dependency install is the common one, and its caliber name is
        the longest. A fresh `pip install mcptoon` has no tiktoken, so this is not
        an edge case — it is the default state of every new user's line 1."""
        fallback = dict(_FACTS, token_caliber="chars/4 estimate")
        for lng in ("zh", "en"):
            self._assert_fits(footer_mod.line(fallback, lng), f"no-tiktoken/{lng}")

    def test_the_gateway_headline_fits_at_the_worst_reachable_size(self):
        """Grow the catalog until every field on the line is at its widest.

        The four-digit tool count, a five-digit call count and a `B`-scale
        cumulative at once — the state a long-lived machine reaches."""
        worst = dict(_FACTS, tools=1209, gateway_tokens=2499, gateway_pct=98.2,
                     calls_recorded=999999)
        for lng in ("zh", "en"):
            self._assert_fits(footer_mod.line(worst, lng), f"grown/{lng}")

    def test_the_note_fits_with_both_caveats_at_once(self):
        """Worst case: an uncached server *and* a very old cache, four-digit age."""
        worst = dict(_FACTS, servers_uncached=1, cache_age_seconds=99999.0)
        for lng in ("zh", "en"):
            n = footer_mod.note(worst, lng)
            self.assertLessEqual(self._width(f"note: {n}"), 80, f"{lng}: {n!r}")


if __name__ == "__main__":
    unittest.main()
