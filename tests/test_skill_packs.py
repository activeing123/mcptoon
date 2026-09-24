"""Tests for `mcptoon install --pack` / `--packs` — one-command skill packs.

A pack is a *bundle*: a named set of MCP tools (plus, later, skills) and a prefilled
prompt, installed together. The design constraints these tests pin:

  * a pack never bundles tool source — each tool is delegated to the existing
    ``install_npm`` / ``install_pip`` / ``install_http`` / ``install_by_name``;
  * the pack catalog is data (``packs.json``), layered builtin-then-user, so a
    user pack with the same name overrides the builtin one;
  * ``--dry`` writes nothing at all (no tools, no prompt);
  * the prompt lands under ``~/.mcptoon/packs/<name>/PROMPT.md`` and nowhere else.

All offline: the installers are patched, so no network and no real installs.
"""
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

from mcptoon import packs  # noqa: E402


def write_packs(path: Path, packs_list: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "packs": packs_list}), encoding="utf-8")
    return path


class TestPackCatalog(unittest.TestCase):
    def test_builtin_catalog_parses_and_is_nonempty(self):
        cat = packs.load_builtin()
        self.assertGreaterEqual(len(cat), 1)
        names = {p["name"] for p in cat}
        self.assertIn("web-research", names)

    def test_builtin_packs_are_well_formed(self):
        for p in packs.load_builtin():
            self.assertRegex(p["name"], r"^[a-z0-9-]+$")
            self.assertTrue(p.get("title"))
            self.assertTrue(p.get("description"))
            self.assertIsInstance(p.get("tools"), list)
            self.assertGreaterEqual(len(p["tools"]), 1)

    def test_user_layer_overrides_builtin_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            user = write_packs(Path(td) / "packs.json", [
                {"name": "web-research", "title": "Mine", "description": "override",
                 "tools": [{"name": "mine", "npm": "@me/mine"}]},
            ])
            merged = packs.load_catalog(user_path=user)
            hit = next(p for p in merged if p["name"] == "web-research")
            self.assertEqual(hit["title"], "Mine")
            self.assertEqual(hit["tools"], [{"name": "mine", "npm": "@me/mine"}])

    def test_missing_user_file_is_fine(self):
        merged = packs.load_catalog(user_path=Path("does") / "not" / "exist.json")
        self.assertGreaterEqual(len(merged), 1)

    def test_corrupt_user_file_raises_a_clear_error(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "packs.json"
            bad.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(packs.PackError):
                packs.load_catalog(user_path=bad)

    def test_find_pack(self):
        cat = packs.load_catalog(user_path=Path("nope.json"))
        self.assertIsNotNone(packs.find_pack(cat, "web-research"))
        self.assertIsNone(packs.find_pack(cat, "no-such-pack"))

    def test_packs_json_is_declared_as_package_data(self):
        """A data file that is not in package-data ships missing from the wheel.

        The builtin catalog is read at runtime, so `pip install mcptoon` must carry
        it. This pins the pyproject declaration rather than trusting it to survive
        a future packaging edit.
        """
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.setuptools.package-data]", text)
        self.assertRegex(text, r'(?m)^mcptoon\s*=\s*\[[^\]]*"packs\.json"')
        self.assertTrue(packs.builtin_path().is_file())


class TestPackInstall(unittest.TestCase):
    def _install(self, pack, **kw):
        calls = []

        def fake_npm(pkg, name=None):
            calls.append(("npm", pkg, name))
            return {"installed": name or pkg}

        def fake_pip(pkg, name=None):
            calls.append(("pip", pkg, name))
            return {"installed": name or pkg}

        def fake_http(url, name=None):
            calls.append(("http", url, name))
            return {"installed": name or url}

        def fake_by_name(name, server_name=None):
            calls.append(("by_name", name, server_name))
            return {"installed": name}

        with tempfile.TemporaryDirectory() as td:
            packs_root = Path(td) / "packs"
            with patch("mcptoon.packs.install_npm", fake_npm), \
                 patch("mcptoon.packs.install_pip", fake_pip), \
                 patch("mcptoon.packs.install_http", fake_http), \
                 patch("mcptoon.packs.install_by_name", fake_by_name):
                report = packs.install_pack(pack, packs_root=packs_root, **kw)
            prompt = packs_root / pack["name"] / "PROMPT.md"
            # Read the prompt before the temp dir is torn down.
            pinfo = {"exists": prompt.is_file(),
                     "text": prompt.read_text(encoding="utf-8") if prompt.is_file() else ""}
            return report, calls, pinfo

    def test_routes_each_tool_to_the_right_installer(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "a", "npm": "@x/a"},
                          {"name": "b", "pip": "mcp-b"},
                          {"name": "c", "url": "https://ex/mcp"},
                          {"name": "d", "registry": "d"}]}
        report, calls, _ = self._install(pack)
        kinds = [c[0] for c in calls]
        self.assertEqual(kinds, ["npm", "pip", "http", "by_name"])
        self.assertEqual(report["pack"], "demo")
        self.assertEqual(len(report["tools"]), 4)
        self.assertTrue(all(t["ok"] for t in report["tools"]))

    def test_prompt_is_written_under_the_pack_dir(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "a", "npm": "@x/a"}],
                "prompt": "Do the thing."}
        _, _, pinfo = self._install(pack)
        self.assertTrue(pinfo["exists"])
        self.assertEqual(pinfo["text"].strip(), "Do the thing.")

    def test_dry_run_writes_nothing(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "a", "npm": "@x/a"}], "prompt": "x"}
        report, calls, pinfo = self._install(pack, dry_run=True)
        self.assertEqual(calls, [], "dry run must not install anything")
        self.assertFalse(pinfo["exists"], "dry run must not write the prompt")
        self.assertTrue(report["dry_run"])
        self.assertEqual(len(report["tools"]), 1)

    def test_one_bad_tool_does_not_abort_the_rest(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "bad", "npm": "@x/bad"},
                          {"name": "good", "npm": "@x/good"}]}

        def flaky_npm(pkg, name=None):
            if name == "bad":
                raise RuntimeError("boom")
            return {"installed": name}

        with tempfile.TemporaryDirectory() as td:
            with patch("mcptoon.packs.install_npm", flaky_npm):
                report = packs.install_pack(pack, packs_root=Path(td) / "packs")
        oks = {t["name"]: t["ok"] for t in report["tools"]}
        self.assertFalse(oks["bad"])
        self.assertTrue(oks["good"], "a failing tool must not stop the others")
        self.assertFalse(report["ok"])

    def test_unknown_tool_shape_is_reported_not_crashed(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "weird", "wat": "??"}]}
        report, calls, _ = self._install(pack)
        self.assertEqual(calls, [])
        self.assertFalse(report["tools"][0]["ok"])

    def test_self_entry_registers_the_gateway_via_sync(self):
        """`"self": true` is the gateway, not a package: it goes through sync --self."""
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "a", "npm": "@x/a"}, {"name": "mcptoon", "self": True}]}
        seen = {}

        def fake_sync_to_all(include_self=False, **kw):
            seen["include_self"] = include_self
            return [{"written": True}]

        with tempfile.TemporaryDirectory() as td:
            with patch("mcptoon.packs.install_npm", lambda pkg, name=None: {"ok": name}), \
                 patch("mcptoon.sync.sync_to_all", fake_sync_to_all):
                report = packs.install_pack(pack, packs_root=Path(td) / "packs")
        self.assertTrue(seen.get("include_self"), "sync must run with include_self=True")
        self_entry = next(t for t in report["tools"] if t["name"] == "mcptoon")
        self.assertTrue(self_entry["ok"])
        self.assertEqual(self_entry["kind"], "self")

    def test_self_entry_is_planned_on_dry_run_and_never_syncs(self):
        pack = {"name": "demo", "title": "Demo", "description": "d",
                "tools": [{"name": "mcptoon", "self": True}]}

        def boom(**kw):
            raise AssertionError("dry run must not touch agent configs")

        with tempfile.TemporaryDirectory() as td:
            with patch("mcptoon.sync.sync_to_all", boom):
                report = packs.install_pack(pack, packs_root=Path(td) / "packs", dry_run=True)
        self.assertTrue(report["tools"][0]["ok"])
        self.assertIn("planned", report["tools"][0]["detail"])

    def test_builtin_essentials_pack_has_the_four_chosen_tools(self):
        """The user's chosen four, by name, in order — none needing an API key."""
        cat = packs.load_catalog(user_path=Path("nope.json"))
        ess = packs.find_pack(cat, "essentials")
        self.assertIsNotNone(ess, "essentials pack must ship builtin")
        names = [t["name"] for t in ess["tools"]]
        self.assertEqual(names, ["filesystem", "playwright", "memory", "duckduckgo"])


if __name__ == "__main__":
    unittest.main()
