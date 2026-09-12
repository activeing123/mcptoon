"""Pin gemini-extension.json to the release so the Gemini gallery cannot drift.

The gallery indexes by GitHub topic + a root manifest, and the docs require the
manifest version to match the release tag (see docs/extensions/releasing.md in
google-gemini/gemini-cli). These assertions fail CI if the manifest version,
the pyproject version, the bridge command, or the context file drift apart.

pyproject is parsed with a regex, not tomllib, because the package supports 3.10.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "gemini-extension.json").read_text(encoding="utf-8"))
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

# Locked public copy claims: numbers/phrasings that must never appear here.
BANNED = ["99.8%", "97%", "123 tokens", "no config file", "configure once"]


def project_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT, re.M)
    assert m, "version not found in pyproject.toml"
    return m.group(1)


class TestGeminiManifest(unittest.TestCase):
    def test_name_is_lowercase_mcptoon(self):
        self.assertEqual(MANIFEST["name"], "mcptoon")

    def test_version_matches_pyproject(self):
        self.assertEqual(
            MANIFEST["version"], project_version(), "gemini-extension.json version != pyproject"
        )

    def test_bridge_serves_stdio_mcptoon(self):
        servers = MANIFEST["mcpServers"]
        self.assertEqual(list(servers), ["mcptoon"])
        self.assertEqual(servers["mcptoon"]["command"], "mcptoon")
        self.assertEqual(servers["mcptoon"]["args"], ["serve"])

    def test_context_file_exists_next_to_manifest(self):
        ctx = ROOT / MANIFEST["contextFileName"]
        self.assertTrue(ctx.is_file(), f"{MANIFEST['contextFileName']} missing at repo root")
        self.assertGreater(len(ctx.read_text(encoding="utf-8").strip()), 200)

    def test_description_is_short_and_clean(self):
        desc = MANIFEST["description"]
        self.assertTrue(10 <= len(desc) <= 200, "description length outside gallery bounds")
        for banned in BANNED:
            self.assertNotIn(banned, desc, f"banned claim in description: {banned}")

    def test_cold_start_caveat_is_documented(self):
        ctx = (ROOT / MANIFEST["contextFileName"]).read_text(encoding="utf-8")
        self.assertIn("pre-warm", ctx.lower(), "bridge cold-start note must stay honest")


if __name__ == "__main__":
    unittest.main()
