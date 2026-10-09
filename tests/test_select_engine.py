# Tests for `mcptoon select` and the pluggable ranking engines.
#
# The design point (user's decision, 2026-10-09): the default engine must be
# pure stdlib so `dependencies = []` stays true, and an external engine is
# opt-in. The failure mode this file guards hardest is a *silent* fallback: a
# user who configured a ranker and quietly got the built-in one has no way to
# know their ranker is broken.
import json
import sys
from unittest.mock import patch

from mcptoon import config as cfg
from mcptoon import manifest as manifest_mod


TOOLS = [
    {"server": "filesystem", "name": "search_files",
     "description": "Recursively search for files matching a pattern"},
    {"server": "filesystem", "name": "read_file",
     "description": "Read the complete contents of a file as text"},
    {"server": "exa", "name": "search", "description": "Search the web"},
]


def _settings(tmp_path, **vals):
    """Point the settings file at tmp_path and return a patcher."""
    return patch.object(cfg, "_settings_file", return_value=tmp_path / "settings.json")


class TestLexicalEngine:
    def test_default_engine_is_lexical(self, tmp_path):
        with _settings(tmp_path):
            ranked, note = manifest_mod.rank_tools("search files", TOOLS)
        assert note == "lexical"
        assert ranked, "the lexical engine found nothing for an obvious query"

    def test_lexical_needs_no_external_program(self, tmp_path):
        # The whole point of the default: it must not shell out at all.
        with _settings(tmp_path), \
             patch.object(manifest_mod, "_command_rank") as cmd:
            manifest_mod.rank_tools("search files", TOOLS)
        cmd.assert_not_called()

    def test_results_are_sorted_by_score(self, tmp_path):
        with _settings(tmp_path):
            ranked, _ = manifest_mod.rank_tools("search files", TOOLS)
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)


class TestCommandEngine:
    def _with_command(self, tmp_path, command):
        s = tmp_path / "settings.json"
        s.write_text(json.dumps({"select.engine": "command",
                                 "select.command": command}), encoding="utf-8")
        return s

    def test_external_engine_is_used_and_named(self, tmp_path):
        # A ranker that puts exa/search first regardless of the query.
        script = tmp_path / "ranker.py"
        script.write_text(
            "import json,sys\n"
            "q=json.load(sys.stdin)\n"
            "out=[{'server':t['server'],'name':t['name'],"
            "'score':9.0 if t['name']=='search' else 0.1} for t in q['tools']]\n"
            "print(json.dumps(out))\n", encoding="utf-8")
        with _settings(tmp_path, **{}), \
             patch.object(cfg, "_settings_file",
                          return_value=self._with_command(tmp_path, f"{sys.executable} {script}")):
            ranked, note = manifest_mod.rank_tools("anything", TOOLS)
        assert note == "command"
        assert ranked[0]["name"] == "search"

    def test_output_is_sorted_even_if_the_ranker_is_not(self, tmp_path):
        # The contract says any order is accepted; mcptoon must sort.
        script = tmp_path / "unsorted.py"
        script.write_text(
            "import json,sys\n"
            "q=json.load(sys.stdin)\n"
            "print(json.dumps([{'server':t['server'],'name':t['name'],'score':i}"
            " for i,t in enumerate(q['tools'])]))\n", encoding="utf-8")
        with patch.object(cfg, "_settings_file",
                          return_value=self._with_command(tmp_path, f"{sys.executable} {script}")):
            ranked, note = manifest_mod.rank_tools("q", TOOLS)
        assert note == "command"
        assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)


class TestCommandEngineFallbacks:
    """Every way the external engine can fail must degrade AND say so."""

    def _run(self, tmp_path, command):
        s = tmp_path / "settings.json"
        s.write_text(json.dumps({"select.engine": "command",
                                 "select.command": command}), encoding="utf-8")
        with patch.object(cfg, "_settings_file", return_value=s):
            return manifest_mod.rank_tools("search files", TOOLS)

    def test_missing_program(self, tmp_path):
        ranked, note = self._run(tmp_path, "definitely-not-a-real-program-xyz")
        assert "command failed" in note
        assert ranked, "must still return the lexical ranking"

    def test_nonzero_exit(self, tmp_path):
        script = tmp_path / "boom.py"
        script.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
        _, note = self._run(tmp_path, f"{sys.executable} {script}")
        assert "command failed" in note

    def test_garbage_stdout(self, tmp_path):
        script = tmp_path / "garbage.py"
        script.write_text("print('this is not json')\n", encoding="utf-8")
        _, note = self._run(tmp_path, f"{sys.executable} {script}")
        assert "command failed" in note

    def test_wrong_shape(self, tmp_path):
        script = tmp_path / "wrong.py"
        script.write_text("print('{\"not\": \"a list\"}')\n", encoding="utf-8")
        _, note = self._run(tmp_path, f"{sys.executable} {script}")
        assert "command failed" in note

    def test_command_engine_with_no_command_set(self, tmp_path):
        _, note = self._run(tmp_path, "")
        assert "no select.command set" in note

    def test_fallback_is_never_silent(self, tmp_path):
        # The headline rule: a configured engine that did not answer must be
        # visible in the note. If this ever returns a bare "lexical", the user
        # cannot tell their ranker is broken.
        _, note = self._run(tmp_path, "definitely-not-a-real-program-xyz")
        assert note != "lexical"


class TestSettingsWiring:
    def test_defaults_include_the_new_keys(self):
        assert cfg.SETTING_DEFAULTS["select.engine"] == "lexical"
        assert cfg.SETTING_DEFAULTS["select.command"] == ""

    def test_engine_is_a_closed_choice(self):
        assert cfg.SETTING_CHOICES["select.engine"] == ("lexical", "command")

    def test_bad_engine_is_rejected(self, tmp_path):
        with _settings(tmp_path):
            try:
                cfg.set_setting("select.engine", "bogus")
            except ValueError as e:
                assert "lexical" in str(e)
            else:
                raise AssertionError("a bogus engine must be rejected, not stored")

    def test_command_is_free_text(self, tmp_path):
        # It holds a path with spaces, so it must NOT be in SETTING_CHOICES.
        assert "select.command" not in cfg.SETTING_CHOICES

    def test_free_text_value_keeps_its_case(self, tmp_path):
        """`config set` must not lowercase a path.

        Regression: the CLI lowercased both key and value, which is fine for the
        closed-choice settings and fatal for this one — a ranker path with any
        uppercase in it was stored mangled, so the external engine silently
        never ran. Enums still accept "ON"/"Off"; free text is stored verbatim.
        """
        from mcptoon import cli
        with _settings(tmp_path):
            cli._cmd_config(["set", "select.command", "python E:/Tools/Ranker.PY"], "auto")
            assert cfg.load_settings()["select.command"] == "python E:/Tools/Ranker.PY"

    def test_enum_value_still_accepts_any_case(self, tmp_path):
        from mcptoon import cli
        with _settings(tmp_path):
            cli._cmd_config(["set", "footer", "OFF"], "auto")
            assert cfg.load_settings()["footer"] == "off"
