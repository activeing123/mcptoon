# Tests for mcptoon's own skill: that it ships, that the three copies agree, and
# that installing it never fights another manager.
#
# Why this file exists at all: the skill is the file that tells an agent what the
# exposure default is and how to switch presets when a tool panel looks empty
# (CONTEXT.md: Skill-as-Explainer). Three different channels ship it, and before
# 2026-09-25 the packaged one did not exist at all — `pip install mcptoon`
# produced a machine with no skill anywhere, so the explanation could not reach
# the agent that needed it.

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcptoon import skills  # noqa: E402

# The three distribution copies. Each is the correct file for its channel; they
# must agree byte for byte or the channels tell agents different things.
COPIES = {
    "packaged": ROOT / "src" / "mcptoon" / "skill" / "SKILL.md",
    "repo-root": ROOT / "skills" / "mcptoon" / "SKILL.md",
    "plugin": ROOT / "claude-code-plugin" / "skills" / "mcptoon" / "SKILL.md",
}


class TestThreeCopiesAgree:
    def test_every_copy_exists(self):
        for name, path in COPIES.items():
            assert path.is_file(), f"{name} copy is missing: {path}"

    def test_copies_are_byte_identical(self):
        texts = {name: p.read_bytes() for name, p in COPIES.items()}
        reference = texts["packaged"]
        for name, body in texts.items():
            assert body == reference, (
                f"the {name} copy drifted from the packaged one — the channels "
                "now describe the tool differently"
            )

    def test_packaged_path_resolves_to_the_copy_on_disk(self):
        """`install_self` copies from this path, so it must be the real one."""
        resolved = skills.packaged_skill_path()
        assert resolved.is_file(), resolved
        assert resolved.resolve() == COPIES["packaged"].resolve()

    def test_the_skill_ships_in_the_wheel(self):
        """A file on disk is not a file a `pip install` gets.

        `packs.json` needed the same entry for the same reason; this asserts the
        packaged skill is listed too, so an upgrade cannot silently drop it.
        """
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        section = pyproject.split("[tool.setuptools.package-data]", 1)[1]
        lines = [ln for ln in section.splitlines() if ln.strip().startswith("mcptoon")]
        assert lines, "no mcptoon entry in package-data"
        assert "skill/SKILL.md" in lines[0], (
            "skill/SKILL.md is not in package-data — the wheel would ship without "
            "the skill, and `install_self` would fail on every pip install"
        )

    def test_the_skill_explains_the_exposure_default(self):
        """The one thing this skill must never lose.

        Measured failure mode it guards: a user reporting "my MCP tools
        disappeared", answered by an agent that has no idea a preset is
        withholding them.
        """
        text = COPIES["packaged"].read_text(encoding="utf-8")
        assert "exposure" in text
        assert "mcptoon config set exposure full" in text
        # and it must be reachable from the trigger surface, not only the body:
        # routing reads the frontmatter description alone.
        frontmatter = text.split("---", 2)[1]
        assert "exposure" in frontmatter, (
            "the trigger for 'my tools vanished' must be in the frontmatter "
            "description, where routing can see it"
        )


class TestInstallSelf:
    def _view(self, tmp_path, name="claude"):
        view = tmp_path / name / "skills"
        view.mkdir(parents=True, exist_ok=True)
        return view

    def test_installs_into_a_view_that_lacks_it(self, tmp_path):
        view = self._view(tmp_path)
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is True
        installed = view / "mcptoon" / "SKILL.md"
        assert installed.is_file()
        assert installed.read_bytes() == skills.packaged_skill_path().read_bytes()

    def test_installs_into_every_view(self, tmp_path):
        views = [self._view(tmp_path, "a"), self._view(tmp_path, "b")]
        rows = skills.install_self(views=views)
        assert [r["written"] for r in rows] == [True, True]
        for v in views:
            assert (v / "mcptoon" / "SKILL.md").is_file()

    def test_never_overwrites_a_view_that_already_has_it(self, tmp_path):
        """Another manager may own that folder — presence means done.

        The realistic case: tongbu-skills junctions `<view>/mcptoon` at a source
        directory. Writing through it would edit a file mcptoon does not own, and
        this machine's own skill views are exactly that shape.
        """
        view = self._view(tmp_path)
        existing = view / "mcptoon"
        existing.mkdir(parents=True)
        marker = existing / "SKILL.md"
        marker.write_text("someone else's skill\n", encoding="utf-8")

        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is False
        assert rows[0]["skipped"] is True
        assert marker.read_text(encoding="utf-8") == "someone else's skill\n"

    def test_a_second_run_is_a_no_op(self, tmp_path):
        view = self._view(tmp_path)
        first = skills.install_self(views=[view])
        second = skills.install_self(views=[view])
        assert first[0]["written"] is True
        assert second[0]["written"] is False
        assert second[0]["skipped"] is True

    def test_dry_run_writes_nothing(self, tmp_path):
        view = self._view(tmp_path)
        rows = skills.install_self(views=[view], dry_run=True)
        assert rows[0]["written"] is False
        assert not (view / "mcptoon").exists()

    def test_creates_a_missing_view_directory(self, tmp_path):
        """A machine where an agent is installed but its skill folder is not."""
        view = tmp_path / "codex" / "skills"
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is True
        assert (view / "mcptoon" / "SKILL.md").is_file()

    def test_a_missing_package_copy_is_reported_not_crashed(self, tmp_path, monkeypatch):
        view = self._view(tmp_path)
        monkeypatch.setattr(skills, "packaged_skill_path",
                            lambda: tmp_path / "nope" / "SKILL.md")
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is False
        assert "packaged skill missing" in rows[0]["error"]

    def test_json_report_is_serializable(self, tmp_path):
        view = self._view(tmp_path)
        json.dumps(skills.install_self(views=[view]))


class TestExposureSettingRoundTrip:
    """The rollback path the skill tells users to run, end to end on disk."""

    def test_set_and_read_back_both_presets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        from mcptoon import config

        assert config.exposure_mode() == "compact"      # the shipped default
        config.set_setting("exposure", "full")
        assert config.exposure_mode() == "full"
        config.set_setting("exposure", "compact")
        assert config.exposure_mode() == "compact"

    def test_an_unknown_value_is_refused_at_the_keyboard(self, tmp_path, monkeypatch):
        """A silent downgrade would tell the user their tools are visible when
        they are not, so the typo has to fail here rather than fall back later."""
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        from mcptoon import config

        with pytest.raises(ValueError):
            config.set_setting("exposure", "Compact")
