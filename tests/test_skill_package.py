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
from unittest.mock import patch

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

# The commands an agent reaches for on the common path. The skill must name all
# of them; it is free to omit the rest of the CLI (it deliberately does — see
# `test_the_skill_names_the_core_commands` for why a floor and not a manifest).
CORE_COMMANDS = ("manifest", "inspect", "search", "select", "call")


def yaml_frontmatter_error(frontmatter: str) -> str | None:
    """The first *real* YAML error in a frontmatter block, or None when it parses.

    Zero-dependency by design (AGENTS.md rule 1): this does not reimplement YAML,
    it pins the one rule that shipped broken. Inside a **plain** (unquoted) scalar
    a colon followed by a space opens a nested mapping, so

        description: tools seem to have gone missing: a gateway is mounted ...

    is invalid YAML. Real parsers (PyYAML, the ``yaml`` package a skill host uses)
    reject the whole block — and a host that cannot parse the frontmatter *drops
    the skill silently*: it ships, installs, and never loads.

    Why a dedicated guard instead of trusting ``plugin.parse_skill_frontmatter``:
    that home-grown reader splits each line on the *first* colon and is happy to
    return the broken description above, so mcptoon's own tooling (and the three-
    copies test) saw nothing wrong while every downstream agent saw no skill at
    all. A lenient reader cannot police the format it is lenient about.
    """
    for line in frontmatter.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in (" ", "\t", "-"):        # nested map / list item, not a key
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        # Quoted, block (|, >), or flow ([, {) scalars carry their own syntax.
        if value[:1] in ("'", '"', "|", ">", "[", "{"):
            continue
        if ": " in value or value.endswith(":"):
            return (f"{key.strip()}: a plain scalar cannot contain ': ' "
                    f"(opens a nested mapping) -> {value[:60]!r}")
    return None


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
        """`install_self` copies from this path, so it must be the real one.

        Two environments, one invariant.

        In a **source checkout** the packaged copy *is* the file under `src/`, so the
        two paths must be identical. In an **installed** package they are two
        different directories and can never be equal — a wheel puts one in
        `site-packages`, and Nix puts the package in `/nix/store` while the source
        sits in `/nix/var/nix/builds`. Asserting directory identity there asserts
        something false about a perfectly correct install.

        That is not hypothetical: it failed `nix-build` on all three platforms for
        0.8.7 (1 failed, 1739 passed), which blocked the numtide channel — the bump
        PR sat with `mergeable_state=blocked` while every other check was green.
        Locally and in CI it passed because both paths resolve to the same checkout.

        What must hold in *both* environments: the path exists, and it is the same
        **content** as the canonical copy. Byte identity is what `install_self`
        actually depends on; directory identity is an accident of how the tests
        happen to be invoked.
        """
        resolved = skills.packaged_skill_path()
        assert resolved.is_file(), resolved
        if resolved.resolve() == COPIES["packaged"].resolve():
            return                      # source checkout — identity is expected
        assert resolved.read_bytes() == COPIES["packaged"].read_bytes(), (
            f"the installed skill at {resolved} differs from the source-tree copy at "
            f"{COPIES['packaged']} — `install_self` would hand agents a different file"
        )

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

    def test_the_skill_names_the_core_commands(self):
        """A command the skill never names may as well not exist.

        Measured failure mode this guards (2026-10-09): `mcptoon select` shipped
        with its CLI wiring, its `--help` line, both READMEs and the completion
        table all updated — and the skill still never mentioned it. Nothing went
        red, because the skill is deliberately *not* a full command list: 37
        commands are advertised, the skill names ~17. So a missing one is
        invisible to every other guard, and the agent reading the skill simply
        never learns the feature exists. It was caught by the user asking
        "did you update the skill?" — not by CI.

        Scope is deliberately the four commands an agent reaches for on the
        common path, not all 37. This is a floor, not a manifest: a guard that
        demanded every command would fight the skill's job of being short, and a
        guard that fights the file gets deleted. The four are the ones whose
        absence actually breaks a session:

          manifest - see what tools exist
          inspect  - get one tool's real parameters
          search   - find a tool by capability
          select   - pick the right few when the catalog is too big to list
          call     - actually run one

        The exposure check above is the same shape; this is its sibling.
        """
        text = COPIES["packaged"].read_text(encoding="utf-8")
        missing = [c for c in CORE_COMMANDS if f"mcptoon {c}" not in text]
        assert not missing, (
            f"the skill never mentions these core commands: {missing}. An agent "
            "that reads only the skill would not know they exist — add a row to "
            "the 'When to use what' table."
        )

    def test_the_core_command_guard_actually_bites(self):
        """The guard above must fail when a command is removed.

        A guard nobody has watched fail is a guard nobody can trust — it might
        be asserting something vacuous (a typo'd string, a wrong copy). This
        feeds the check the exact edit it exists to catch: a skill whose table
        lost its `select` row.
        """
        text = COPIES["packaged"].read_text(encoding="utf-8")
        assert "mcptoon select" in text, "the real skill lost the row this test is about"
        # Replace with a string that does NOT contain the original as a substring,
        # or the check still finds "mcptoon select" inside the replacement and
        # reports no regression — which is exactly how this test failed first.
        removed = text.replace("mcptoon select", "mcptoon choose")
        missing = [c for c in CORE_COMMANDS if f"mcptoon {c}" not in removed]
        assert "select" in missing, (
            "the guard would not have caught the real regression it was written for"
        )


class TestFrontmatterIsRealYaml:
    """Every shipped copy's frontmatter must parse as *actual* YAML.

    Regression guard for v0.8.2: the ``description`` was written unquoted and
    contained ``: `` (``tools seem to have gone missing: a gateway …``). The
    three-copies test passed and mcptoon's own lenient reader was happy, but
    every host that parses frontmatter with a real YAML parser — Claude Code,
    DSH, Codex — dropped the skill with a warning nobody reads. The skill
    shipped, installed, and never loaded. This is the check that would have
    caught it before the release.
    """

    def test_every_copy_frontmatter_parses(self):
        for name, path in COPIES.items():
            body = path.read_text(encoding="utf-8")
            assert body.startswith("---"), f"{name} copy has no frontmatter"
            frontmatter = body.split("---", 2)[1]
            err = yaml_frontmatter_error(frontmatter)
            assert err is None, f"{name} copy has invalid YAML frontmatter: {err}"

    def test_the_guard_rejects_the_shape_that_shipped_broken(self):
        """The guard must actually fire on the v0.8.2 bug, not just pass."""
        broken = ("name: mcptoon\n"
                  "description: route here when the user's MCP tools seem to "
                  "have gone missing: a gateway is mounted in COMPACT\n")
        assert yaml_frontmatter_error(broken) is not None

    def test_the_guard_accepts_a_quoted_description_with_colons(self):
        """The fix must pass: a quoted scalar may hold ``: `` safely."""
        fixed = ('name: mcptoon\n'
                 'description: "tools seem to have gone missing: a gateway '
                 'is mounted"\n')
        assert yaml_frontmatter_error(fixed) is None


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

    def test_it_does_not_create_a_view_for_an_agent_that_is_not_installed(self, tmp_path):
        """Default views only — an explicit `--view` is still honoured.

        On a machine with none of the six agents, `install_self` used to `mkdir` all
        six default view roots and report "installed for 6 agent(s)". A default root
        that is not there means the agent is not installed, and an empty `.codex/skills`
        shell helps nobody. An explicit `views=` (the CLI's `--view`, for an agent we do
        not know about) is a deliberate instruction and must still create the folder.
        """
        with patch.object(skills, "_view_roots",
                          return_value=[tmp_path / "there" / "skills",
                                        tmp_path / "absent" / "skills"]):
            (tmp_path / "there" / "skills").mkdir(parents=True)
            rows = skills.install_self()

        assert rows[0]["written"] is True
        assert not (tmp_path / "absent" / "skills").exists(), (
            "a default view that did not exist must not be created")

        # Explicit views are a different contract: the user named the folder.
        explicit = tmp_path / "explicit" / "skills"
        skills.install_self(views=[explicit])
        assert (explicit / "mcptoon" / "SKILL.md").is_file()

    def test_views_missing_our_skill_tracks_only_existing_views(self, tmp_path):
        present = self._view(tmp_path, "present")
        absent = tmp_path / "absent" / "skills"
        with patch.object(skills, "_view_roots", return_value=[present, absent]):
            assert skills.views_missing_our_skill() is True
            skills.install_self()
            assert skills.views_missing_our_skill() is False, (
                "an absent view is not 'missing our skill' — there is no agent to miss it")
            (absent).mkdir(parents=True)
            assert skills.views_missing_our_skill() is True, (
                "a view that just appeared must be reported as missing our skill")

    def test_never_overwrites_a_skill_that_is_not_ours(self, tmp_path):
        """Another manager may own that folder — a foreign skill stays put.

        The realistic case: tongbu-skills junctions `<view>/mcptoon` at a source
        directory. A file with no `name: mcptoon` frontmatter is not ours to edit,
        so it is left byte-for-byte alone. (Our *own* stale copy is a different
        case — see TestInstallSelfRefreshesOurOwnCopy.)
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


class TestInstallSelfRefreshesOurOwnCopy:
    """An upgrade must reach a user who already has the skill.

    Presence was the original test, and it is right for *someone else's* folder —
    but wrong for our own file. A user who installed an older release keeps that
    copy forever, so a newer explanation (a new default, a new tool, a new preset)
    never reaches the agent that needs it. The refresh is keyed on the frontmatter
    `name`: only a file that declares `name: mcptoon` is ours to update.
    """

    def _view_with(self, tmp_path, body):
        view = tmp_path / "skills"
        (view / "mcptoon").mkdir(parents=True)
        (view / "mcptoon" / "SKILL.md").write_text(body, encoding="utf-8")
        return view

    def test_our_stale_copy_is_refreshed(self, tmp_path):
        stale = ("---\nname: mcptoon\ndescription: an old copy\n---\n\nold body\n")
        view = self._view_with(tmp_path, stale)
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is True
        assert rows[0]["updated"] is True
        assert (view / "mcptoon" / "SKILL.md").read_bytes() == \
            skills.packaged_skill_path().read_bytes()

    def test_a_current_copy_is_left_alone(self, tmp_path):
        view = tmp_path / "skills"
        (view / "mcptoon").mkdir(parents=True)
        (view / "mcptoon" / "SKILL.md").write_bytes(
            skills.packaged_skill_path().read_bytes())
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is False
        assert rows[0]["skipped"] is True
        assert rows[0]["updated"] is False

    def test_someone_elses_named_skill_is_never_touched(self, tmp_path):
        """A different `name` is a different skill, even in a `mcptoon` folder."""
        other = "---\nname: not-mcptoon\ndescription: someone else\n---\n\nbody\n"
        view = self._view_with(tmp_path, other)
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is False
        assert rows[0]["skipped"] is True
        assert (view / "mcptoon" / "SKILL.md").read_text(encoding="utf-8") == other

    def test_a_dry_run_reports_a_refresh_but_writes_nothing(self, tmp_path):
        stale = "---\nname: mcptoon\ndescription: old\n---\n\nold\n"
        view = self._view_with(tmp_path, stale)
        rows = skills.install_self(views=[view], dry_run=True)
        assert rows[0]["updated"] is True
        assert rows[0]["written"] is False
        assert (view / "mcptoon" / "SKILL.md").read_text(encoding="utf-8") == stale

    def test_an_unreadable_existing_file_is_left_alone(self, tmp_path):
        """No name read back means "not ours" — the safe direction."""
        view = self._view_with(tmp_path, "")  # empty: parses to no name
        rows = skills.install_self(views=[view])
        assert rows[0]["written"] is False
        assert rows[0]["skipped"] is True


class TestFreshInstallCountsTheSkillOnce:
    """The whole first-run path: install into every view, then read the catalog.

    Why this class exists: `TestInstallSelf` always passed an explicit ``views=``
    list and `RealPathDedupTests` always used *junctions*. Neither covered the
    layout a real ``pip install`` produces — the packaged skill **copied** into
    six agent folders — so the index counted it six times, printed six identical
    `skills list` rows, emitted a bogus ``SKILL_DUPLICATE``, and quoted 12,163
    tokens for one 3,130-token file. The tool's own savings numbers were 4x
    inflated on exactly the machine that had just installed it.
    """

    VIEW_NAMES = ("claude", "agents", "codex", "cursor", "catpaw",
                  "codeium/windsurf")

    def _installed(self, tmp_path):
        views = [tmp_path / n / "skills" for n in self.VIEW_NAMES]
        skills.install_self(views=views)
        return views

    def test_the_index_reports_one_skill_not_six(self, tmp_path):
        views = self._installed(tmp_path)
        idx = skills.scan_roots(views)
        assert [s["slug"] for s in idx["skills"]] == ["mcptoon"]

    def test_no_duplicate_warning_for_identical_copies(self, tmp_path):
        """Copies are the *same* skill; warning about them is noise, not signal."""
        idx = skills.scan_roots(self._installed(tmp_path))
        assert [w for w in idx["warnings"] if w["code"] == "SKILL_DUPLICATE"] == []

    def test_the_token_figure_is_not_multiplied_by_the_copy_count(self, tmp_path):
        """One 3,130-token file must read as ~3,130, never 6 x that."""
        from mcptoon import bench

        views = self._installed(tmp_path)
        files, _dupes = bench._unique_skill_files(views)
        assert len(files) == 1
        figs = skills.skill_token_figures(roots=views)
        single = skills.packaged_skill_path().read_text(encoding="utf-8")
        encode, _cal, _exact = bench._tokenizer()
        assert figs["count"] == 1
        assert figs["native_tokens"] == encode("\n" + single)

    def test_a_real_conflict_still_warns(self, tmp_path):
        """Same slug, *different* bytes is two skills fighting for one name — the
        collapse must not swallow that case."""
        views = self._installed(tmp_path)
        clash = views[1] / "mcptoon" / "SKILL.md"
        clash.write_text("---\nname: mcptoon\ndescription: different\n---\n\nx\n",
                         encoding="utf-8")
        idx = skills.scan_roots(views)
        assert "SKILL_DUPLICATE" in {w["code"] for w in idx["warnings"]}


class TestDefaultRootsCoverEveryView:
    """A root the catalog installs into but never scans is a skill it hides.

    The bug this pins: ``_view_roots`` (where ``install_self`` writes) listed six
    folders while ``_default_roots`` (what the index scans) listed four, so on a
    fresh machine the two views that only ``_view_roots`` knew about were written
    to and then never read back. The two lists are now the same set.
    """

    def test_default_roots_match_the_view_roots_that_exist(self, monkeypatch, tmp_path):
        home = tmp_path / "home"
        for name in (".claude", ".agents", ".codex", ".cursor", ".catpaw",
                     ".codeium/windsurf"):
            (home / name / "skills").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.delenv("MCPTOON_SKILLS_ROOTS", raising=False)
        monkeypatch.delenv("MCPTOON_SKILLS_VIEWS", raising=False)
        if Path.home() != home:
            pytest.skip("Path.home() did not follow the patched HOME on this box")
        assert set(skills._default_roots()) == set(skills._view_roots())
        assert len(skills._default_roots()) == 6


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
