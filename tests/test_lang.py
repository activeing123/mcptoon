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

"""Language tests — the answer to "how does it decide Chinese or English?".

The question that started this: mcptoon prints a one-line savings figure, and
nobody could say which language it would come out in. `mcptoon config set lang`
is the explicit half of the answer; the interesting half is `auto`, because the
machine's own signals disagree. Measured on the author's box: the Windows UI
language is Chinese (LANGID 0x804) while the shell exports `LANG=en_US.UTF-8`.

A detector with no stated priority is a coin flip that can land differently in a
terminal than under a scheduled task, which for a line that gets quoted into a
chat turn is a defect, not a preference. So these tests pin the *order* — explicit
setting > `MCPTOON_LANG` > OS UI language > LC_*/LANG > English — and pin that
both languages keep the machine-readable handles (`mcptoon:`, `[caliber]`) that
every other suite keys on.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import footer as footer_mod


def _run_main(argv):
    """Run cli.main() with argv and return stdout."""
    buf = io.StringIO()
    with patch.object(cli.sys, "argv", ["mcptoon", *argv]), redirect_stdout(buf):
        try:
            cli.main()
        except SystemExit:
            pass
    return buf.getvalue()


class _IsolatedState(unittest.TestCase):
    """Redirect every path mcptoon reads, so no test can touch the real machine.

    Settings, servers and the schema cache all move into one temp directory, and
    the environment's own language signals are cleared: a language test that
    inherits the runner's locale is testing the runner.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.settings = root / "settings.json"
        env = {
            "MCPTOON_SETTINGS_FILE": str(self.settings),
            "MCPTOON_CONFIG_FILE": str(root / "config.json"),
            "MCPTOON_CONFIG_FILE_TOML": str(root / "config.toml"),
            "MCPTOON_CACHE_DIR": str(root / "cache"),
            "MCPTOON_WELCOME_FILE": str(root / ".welcome"),
        }
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("LANG", "LC_ALL", "LC_MESSAGES", "MCPTOON_LANG"):
            self.addCleanup(os.environ.pop, key, None)
            os.environ.pop(key, None)
        # Pretend the first-run welcome already happened: stdout assertions here
        # are about one line, and a greeting riding along would only add noise.
        (root / ".welcome").write_text("", encoding="utf-8")


class TestLanguageDetection(_IsolatedState):
    def test_lang_is_a_known_setting_and_defaults_to_auto(self):
        self.assertIn("lang", cfg.SETTING_DEFAULTS)
        self.assertEqual(cfg.SETTING_DEFAULTS["lang"], "auto")

    def test_locale_tags_map_to_a_language(self):
        """Both shapes Python hands back are understood, and neither is guessed."""
        cases = (
            ("zh_CN", "zh"),
            ("zh-TW", "zh"),
            ("Chinese (Simplified)_China", "zh"),
            ("en_US.UTF-8", "en"),
            ("English_United States", "en"),
            ("de_DE", None),
            ("", None),
            (None, None),
        )
        for tag, expected in cases:
            self.assertEqual(cfg._lang_from_tag(tag), expected, f"tag={tag!r}")

    def test_the_os_ui_language_outranks_a_contradicting_lang(self):
        """The measured conflict, pinned: `LANG=en_US.UTF-8` must not win.

        This is the whole reason `auto` is an order instead of a heuristic.
        """
        os.environ["LANG"] = "en_US.UTF-8"
        with patch.object(cfg, "_os_ui_lang", return_value="zh"):
            self.assertEqual(cfg.resolve_lang(), "zh",
                             "LANG outranked the OS UI language")

    def test_without_an_os_answer_the_environment_decides(self):
        with patch.object(cfg, "_os_ui_lang", return_value=None):
            os.environ["LANG"] = "zh_CN.UTF-8"
            self.assertEqual(cfg.resolve_lang(), "zh")

    def test_lc_all_outranks_lang(self):
        with patch.object(cfg, "_os_ui_lang", return_value=None):
            os.environ["LANG"] = "zh_CN.UTF-8"
            os.environ["LC_ALL"] = "en_US.UTF-8"
            self.assertEqual(cfg.resolve_lang(), "en")

    def test_an_unrecognised_locale_is_not_a_language(self):
        with patch.object(cfg, "_os_ui_lang", return_value=None):
            os.environ["LANG"] = "de_DE.UTF-8"
            self.assertEqual(cfg.resolve_lang(), "en",
                             "an unnamed language must fall back, not crash")

    def test_with_nothing_to_go_on_it_is_english(self):
        with patch.object(cfg, "_os_ui_lang", return_value=None):
            self.assertEqual(cfg.resolve_lang(), "en")

    def test_the_explicit_setting_beats_every_detected_signal(self):
        os.environ["MCPTOON_LANG"] = "zh"
        with patch.object(cfg, "_os_ui_lang", return_value="zh"):
            self.assertEqual(cfg.resolve_lang("en"), "en", "an argument must win")
            cfg.set_setting("lang", "en")
            self.assertEqual(cfg.resolve_lang(), "en", "the setting must win")

    def test_the_env_override_pins_the_language_without_a_settings_file(self):
        with patch.object(cfg, "_os_ui_lang", return_value="zh"):
            os.environ["MCPTOON_LANG"] = "en"
            self.assertEqual(cfg.resolve_lang(), "en")

    def test_auto_is_not_a_language_and_falls_through(self):
        cfg.set_setting("lang", "auto")
        with patch.object(cfg, "_os_ui_lang", return_value="zh"):
            self.assertEqual(cfg.resolve_lang(), "zh")

    def test_an_unrecognised_setting_falls_through_instead_of_raising(self):
        """A hand-edited settings file must not break a command that prints a line."""
        cfg.set_setting("lang", "fr")
        with patch.object(cfg, "_os_ui_lang", return_value="en"):
            self.assertEqual(cfg.resolve_lang(), "en")


_FACTS = {
    "servers": 12,
    "tools": 95,
    "tokens_full": 20914,
    "tokens_slim": 15719,
    "tokens_saved": 5195,
    "savings_pct": 25.0,
    "token_caliber": "tiktoken cl100k_base",
    "calls_recorded": 0,
    "cache_age_seconds": 100.0,
    "servers_uncached": 1,
    "cache_ttl_seconds": 300,
    "note": None,
}


class TestRendering(_IsolatedState):
    def test_the_english_line_is_byte_identical_to_before(self):
        self.assertEqual(
            footer_mod.line(_FACTS, "en"),
            "🎉 mcptoon: 95 tools in 12 servers — 20,914 → 15,719 tokens "
            "(saved 5,195, 25%) [tiktoken cl100k_base]")

    def test_the_chinese_line_says_the_same_thing(self):
        out = footer_mod.line(_FACTS, "zh")
        self.assertIn("95 个工具", out)
        self.assertIn("12 个服务器", out)
        self.assertIn("省 5,195", out)

    def test_both_languages_keep_the_machine_readable_handles(self):
        """`mcptoon:`, the word `tokens` and `[caliber]` are load-bearing.

        Every other suite and every downstream parser keys on them; a handle that
        changes with the language hands a parsing problem to someone who never
        asked for one.
        """
        for lng in ("en", "zh"):
            out = footer_mod.line(_FACTS, lng)
            self.assertTrue(out.startswith(footer_mod.MARK + " mcptoon:"), out)
            self.assertIn("tokens", out)
            self.assertTrue(out.endswith("[tiktoken cl100k_base]"), out)
            self.assertIn("20,914", out)
            self.assertIn("15,719", out)

    def test_the_note_carries_both_caveats_in_both_languages(self):
        stale = dict(_FACTS, servers_uncached=1, cache_age_seconds=99999.0)
        en = footer_mod.note(stale, "en")
        zh = footer_mod.note(stale, "zh")
        self.assertIn("not cached", en)
        self.assertIn("old", en)
        self.assertIn("12 个服务器里有 1 个还没缓存", zh)
        self.assertIn("分钟没更新", zh)
        self.assertIn("可能滞后", zh)

    def test_a_fresh_cache_has_no_note_in_either_language(self):
        fresh = dict(_FACTS, servers_uncached=0, cache_age_seconds=1.0)
        self.assertIsNone(footer_mod.note(fresh, "en"))
        self.assertIsNone(footer_mod.note(fresh, "zh"))

    def test_no_servers_configured_is_reported_in_both_languages(self):
        empty = dict(_FACTS, servers=0, tools=0, servers_uncached=0)
        self.assertEqual(footer_mod.note(empty, "en"), "no servers configured")
        self.assertEqual(footer_mod.note(empty, "zh"), "尚未配置任何服务器")

    def test_the_block_keeps_the_ascii_note_label(self):
        """`note: ` stays ASCII in both languages for the same reason `mcptoon:` does."""
        stale = dict(_FACTS, servers_uncached=1, cache_age_seconds=99999.0)
        for lng in ("en", "zh"):
            out = footer_mod.block(stale, lng)
            self.assertIn("\nnote: ", out)
            self.assertEqual(len(out.splitlines()), 2, out)

    def test_a_hand_built_dict_without_caveat_inputs_keeps_its_own_note(self):
        """A caller passing a `--json`-shaped dict must not get a re-render."""
        carried = dict(_FACTS, note="catalog is 5 min old (cache TTL 1 min)")
        carried.pop("servers_uncached")
        self.assertEqual(footer_mod.note(carried, "zh"),
                         "catalog is 5 min old (cache TTL 1 min)")


class TestSurfacesFollowTheSetting(_IsolatedState):
    def test_the_footer_facts_command_speaks_the_setting(self):
        cfg.set_setting("lang", "zh")
        out = _run_main(["footer-facts"])
        self.assertIn("0 个工具", out)
        self.assertIn("mcptoon:", out, "the ASCII handle must survive translation")

        cfg.set_setting("lang", "en")
        out = _run_main(["footer-facts"])
        self.assertIn("0 tools in 0 servers", out)

    def test_the_json_payload_stays_english(self):
        """`--json` is a machine channel: its note is data, not a message to a person."""
        cfg.set_setting("lang", "zh")
        out = _run_main(["footer-facts", "--json"])
        self.assertIn('"note": "no servers configured"', out)

    def test_config_set_lang_refuses_an_unknown_language(self):
        out = _run_main(["config", "set", "lang", "fr"])
        self.assertIn("lang accepts only: auto | zh | en", out)

    def test_config_set_lang_saves_and_reports_what_it_resolved_to(self):
        out = _run_main(["config", "set", "lang", "zh"])
        self.assertIn("lang: zh", out)
        self.assertIn("will speak: zh", out)
        self.assertEqual(_run_main(["config", "get", "lang"]).strip(), "zh")

    def test_config_show_explains_the_setting(self):
        out = _run_main(["config"])
        self.assertIn("lang", out)
        self.assertIn("auto follows the OS language", out)


if __name__ == "__main__":
    unittest.main()
