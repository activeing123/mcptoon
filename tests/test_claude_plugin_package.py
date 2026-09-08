"""Guards for the Claude Code plugin package (claude-code-plugin/).

The plugin is a distribution shell, not a second source of truth:
- all JSON files must parse and follow the plugin schema conventions;
- the hook must work on Windows (commandWindows is mandatory);
- marketing text inside the package is pinned to the canonical token
  numbers and the banned-claims blacklist (same discipline as
  test_footprint_claims.py, applied to the plugin copy).
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "claude-code-plugin"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"

BANNED_STRINGS = (
    "zero-config",
    "Zero-config",
    "no config files",
    "No config files",
    "90,804",
    "99.8%",
    "99.9%",
    "123 tokens",
    "MCPTON",
)


def _load(path: pathlib.Path) -> dict:
    assert path.exists(), f"missing file: {path.relative_to(ROOT)}"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPluginPackageStructure:
    def test_plugin_json_is_valid(self):
        data = _load(PLUGIN / ".claude-plugin" / "plugin.json")
        assert data["name"] == "mcptoon"
        # Plugin names are permanent once published - pin the lowercase form.
        assert data["name"] == data["name"].lower()
        assert data["author"]["name"] == "activeing123"
        assert data["homepage"].startswith("https://github.com/")

    def test_marketplace_json_declares_plugin(self):
        data = _load(MARKETPLACE)
        assert data["name"] == "mcptoon"
        entries = data["plugins"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["name"] == "mcptoon"
        assert entry["source"] == "./claude-code-plugin"
        # The source directory must actually exist.
        assert (ROOT / entry["source"]).is_dir()

    def test_mcp_json_wires_serve_bridge(self):
        data = _load(PLUGIN / ".mcp.json")
        servers = data["mcpServers"]
        assert servers["mcptoon"]["command"] == "mcptoon"
        assert "serve" in servers["mcptoon"]["args"]

    def test_hooks_json_has_session_start_with_windows_variant(self):
        data = _load(PLUGIN / "hooks" / "hooks.json")
        start = data["hooks"]["SessionStart"]
        assert len(start) == 1
        hook = start[0]["hooks"][0]
        assert hook["type"] == "command"
        # Windows is a first-class target: a windows-specific command is
        # mandatory, not optional.
        assert hook["commandWindows"]
        assert "session_setup.py" in hook["command"]
        assert 0 < hook["timeout"] <= 120

    def test_setup_script_compiles_and_is_stdlib_only(self):
        source = (PLUGIN / "scripts" / "session_setup.py").read_text(
            encoding="utf-8"
        )
        compile(source, "session_setup.py", "exec")
        assert "pip" in source and "install" in source


class TestSkillAndCommandDocs:
    def test_skill_md_frontmatter_has_triggers_in_description(self):
        text = (PLUGIN / "skills" / "mcptoon" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert text.startswith("---")
        # Routing happens on the frontmatter description only: trigger
        # words must live there, not just in the body.
        fm = text.split("---", 2)[1]
        assert "name: mcptoon" in fm
        for trigger in ("mcptoon", "token", "MCP tool"):
            assert trigger in fm, f"missing trigger word in description: {trigger}"

    def test_skill_md_documents_core_commands(self):
        text = (PLUGIN / "skills" / "mcptoon" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for command in ("mcptoon manifest", "mcptoon call", "mcptoon doctor"):
            assert command in text

    def test_setup_command_has_frontmatter_description(self):
        text = (PLUGIN / "commands" / "mcptoon-setup.md").read_text(
            encoding="utf-8"
        )
        assert text.startswith("---")
        assert "description:" in text.split("---", 2)[1]


class TestCanonicalClaimsOnly:
    """Same banned-number discipline as test_footprint_claims.py."""

    def _texts(self):
        paths = [
            PLUGIN / ".claude-plugin" / "plugin.json",
            MARKETPLACE,
            PLUGIN / "skills" / "mcptoon" / "SKILL.md",
            PLUGIN / "commands" / "mcptoon-setup.md",
        ]
        return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8")
                for p in paths}

    def test_no_banned_claims(self):
        for name, text in self._texts().items():
            for banned in BANNED_STRINGS:
                assert banned not in text, f"{name} contains banned claim: {banned}"

    def test_headline_numbers_are_canonical(self):
        skill = (PLUGIN / "skills" / "mcptoon" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "71,929" in skill and "581" in skill
        plugin_json = _load(PLUGIN / ".claude-plugin" / "plugin.json")
        description = plugin_json["description"]
        assert "71,929" in description and "581" in description
