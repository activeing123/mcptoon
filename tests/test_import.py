"""Tests for `mcptoon import` — bringing servers over from another client.

The feature has two halves:

  * `discover.scan_import_file()` / `scan_import_client()` — read a config and
    normalize it to mcptoon's shape. Tested directly (no CLI).
  * `cli._cmd_import()` — the `mcptoon import` verb: dry-run report, `--write`
    merge, `--from`, `--file`, and the error paths.

The CLI half redirects `MCPTOON_CONFIG_FILE` at a temp path so `--write` never
touches the developer's real `~/.mcptoon/config.json` (same isolation the rest
of the suite uses; see conftest.py).
"""
import json

import pytest

from mcptoon import cli, discover
from mcptoon.cli import _cmd_import


# ─── Fixtures / helpers ───

def _claude_desktop_config(path, servers):
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _run(rest, fmt="auto"):
    """Call the handler directly (skips welcome/self-heal) and return nothing."""
    _cmd_import(rest, fmt)


# ═══════════════════════════════════════════════════
# discover.scan_import_file — reading an explicit file
# ═══════════════════════════════════════════════════

class TestScanImportFile:
    def test_reads_the_mcpservers_shape(self, tmp_path):
        f = tmp_path / "claude.json"
        _claude_desktop_config(f, {
            "fs": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]},
        })
        found = discover.scan_import_file(f)
        assert [x["name"] for x in found] == ["fs"]
        assert found[0]["config"]["transport"] == "stdio"
        assert found[0]["source"] == "file"

    def test_reads_the_servers_shape(self, tmp_path):
        """mcpm.sh and mcptoon both export under a top-level `servers` key."""
        f = tmp_path / "mcpm.json"
        f.write_text(json.dumps({"servers": {"sqlite": {"command": "uvx", "args": ["mcp-server-sqlite"]}}}),
                     encoding="utf-8")
        found = discover.scan_import_file(f)
        assert [x["name"] for x in found] == ["sqlite"]

    def test_normalizes_an_http_server(self, tmp_path):
        f = tmp_path / "remote.json"
        f.write_text(json.dumps({"mcpServers": {
            "api": {"url": "https://example.com/mcp", "transport": "http"},
        }}), encoding="utf-8")
        found = discover.scan_import_file(f)
        assert found[0]["config"]["transport"] == "http"
        assert found[0]["config"]["url"] == "https://example.com/mcp"

    def test_unrelated_json_yields_nothing(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text(json.dumps({"name": "x", "version": "1.0"}), encoding="utf-8")
        assert discover.scan_import_file(f) == []

    def test_invalid_json_raises(self, tmp_path):
        f = tmp_path / "broken.json"
        f.write_text("{ not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            discover.scan_import_file(f)

    def test_extract_servers_map_rejects_non_dict(self):
        assert discover._extract_servers_map(["nope"]) == {}
        assert discover._extract_servers_map({"mcpServers": "nope"}) == {}


# ═══════════════════════════════════════════════════
# discover.scan_import_client — named clients
# ═══════════════════════════════════════════════════

class TestScanImportClient:
    def test_alias_maps_to_canonical_scanner(self, tmp_path, monkeypatch):
        cfg = tmp_path / "claude_desktop_config.json"
        _claude_desktop_config(cfg, {"fs": {"command": "npx", "args": ["-y", "pkg"]}})
        monkeypatch.setattr(discover, "_scan_claude_desktop",
                            lambda: [{"name": "fs", "config": {}, "source": "claude-desktop", "reason": "x"}])
        # alias "claude" resolves to the same scanner as "claude-desktop"
        assert discover.scan_import_client("claude")[0]["name"] == "fs"
        assert discover.scan_import_client("claude-desktop")[0]["name"] == "fs"

    def test_unknown_client_yields_nothing(self):
        assert discover.scan_import_client("definitely-not-a-client") == []


# ═══════════════════════════════════════════════════
# cli._cmd_import — the verb
# ═══════════════════════════════════════════════════

class TestImportCommand:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        """Point the user config at a temp file and keep cwd out of the repo."""
        monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
        monkeypatch.chdir(tmp_path)
        self.tmp = tmp_path

    def _export(self, servers, name="export.json"):
        f = self.tmp / name
        f.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
        return f

    def test_dry_run_reports_and_writes_nothing(self, capsys):
        f = self._export({"fs": {"command": "npx", "args": ["-y", "pkg"]}})
        _run(["import", "--file", str(f)])
        out = capsys.readouterr().out
        assert "Found 1 server(s)" in out
        assert "fs" in out
        assert "--dry run" in out
        assert not (self.tmp / "config.json").exists()

    def test_write_merges_into_config(self, capsys):
        f = self._export({
            "fs": {"command": "npx", "args": ["-y", "pkg"]},
            "api": {"url": "https://x/mcp", "transport": "http"},
        })
        _run(["import", "--file", str(f), "--write"])
        out = capsys.readouterr().out
        assert "+2 new server(s) added" in out
        written = json.loads((self.tmp / "config.json").read_text(encoding="utf-8"))
        assert set(written["servers"]) == {"fs", "api"}

    def test_second_write_skips_then_force_overwrites(self, capsys):
        f = self._export({"fs": {"command": "npx", "args": ["-y", "pkg"]}})
        _run(["import", "--file", str(f), "--write"])
        capsys.readouterr()
        _run(["import", "--file", str(f), "--write"])
        assert "=1 existing server(s) skipped" in capsys.readouterr().out
        _run(["import", "--file", str(f), "--write", "--force"])
        assert "~1 overwritten" in capsys.readouterr().out

    def test_json_format_emits_the_servers_object(self, capsys):
        f = self._export({"fs": {"command": "npx", "args": ["-y", "pkg"]}})
        _run(["import", "--file", str(f)], fmt="json")
        payload = json.loads(capsys.readouterr().out)
        assert "fs" in payload

    def test_missing_file_exits_1(self, capsys):
        with pytest.raises(SystemExit) as e:
            _run(["import", "--file", str(self.tmp / "nope.json")])
        assert e.value.code == 1
        assert "not found" in capsys.readouterr().err

    def test_invalid_json_exits_1(self, capsys):
        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            _run(["import", "--file", str(bad)])
        assert e.value.code == 1
        assert "Not valid JSON" in capsys.readouterr().err

    def test_unknown_client_exits_1(self, capsys):
        with pytest.raises(SystemExit) as e:
            _run(["import", "--from", "bogus"])
        assert e.value.code == 1
        err = capsys.readouterr().err
        assert "Unknown client" in err
        assert "--file" in err  # points at the escape hatch

    def test_from_client_with_no_config_is_not_an_error(self, capsys, monkeypatch):
        monkeypatch.setattr(discover, "scan_import_client", lambda c: [])
        _run(["import", "--from", "cursor"])
        out = capsys.readouterr().out
        assert "No MCP servers found" in out
        assert "--file" in out  # still shows the escape hatch

    def test_equals_form_of_file_flag(self, capsys):
        f = self._export({"fs": {"command": "npx", "args": ["-y", "pkg"]}})
        _run([f"--file={f}"])
        assert "Found 1 server(s)" in capsys.readouterr().out

    def test_scan_all_clients_keeps_first_source_for_a_shared_name(self, capsys, monkeypatch):
        """Same server in several clients → one entry, attributed to the first.

        The scan order is claude-desktop, cursor, cline, windsurf; with the
        dedupe guard the surviving source is the first one seen. Without it the
        last scanner would win (and a real user would see the wrong origin).
        """
        monkeypatch.setattr(discover, "scan_import_client",
                            lambda c: [{"name": "shared", "config": {"transport": "stdio"},
                                        "source": c, "reason": "x"}])
        _run(["import"])
        out = capsys.readouterr().out
        assert "Found 1 server(s)" in out
        assert out.count("shared") == 1
        assert "[claude-desktop] shared" in out


# ═══════════════════════════════════════════════════
# Wiring: dispatch, flags, help
# ═══════════════════════════════════════════════════

class TestImportWiring:
    def test_from_and_file_are_known_flags(self):
        """Unknown flags warn on stderr; `import`'s two flags must not."""
        assert cli.unknown_flag_warnings(["--from", "cursor", "--file", "x.json"]) == []

    def test_help_mentions_import(self, capsys):
        cli._print_help()
        assert "mcptoon import" in capsys.readouterr().out

    def test_import_dispatches_through_main(self, tmp_path, monkeypatch, capsys):
        """End-to-end through cli.main() so the dispatch branch is covered."""
        monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
        monkeypatch.setenv("MCPTOON_SKIP_SELF_HEAL", "1")
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "export.json"
        f.write_text(json.dumps({"mcpServers": {"fs": {"command": "npx", "args": ["-y", "pkg"]}}}),
                     encoding="utf-8")
        monkeypatch.setattr(cli.sys, "argv", ["mcptoon", "import", "--file", str(f)])
        cli.main()
        out = capsys.readouterr().out
        assert "Found 1 server(s)" in out
        assert "unknown option" not in out
