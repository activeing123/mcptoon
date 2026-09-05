"""Bind the MCP Registry record to the release, so it cannot drift again.

AGENTS.md promised "keep server.json in sync" with no mechanism behind it, and the
registry served 0.7.2 through three releases while server.json's package version
lagged a release behind its own top-level version. These assertions are the
mechanism: server.json, pyproject.toml, the README ownership marker and the publish
workflow are checked against each other, so the next release either updates all of
them or fails CI.

pyproject is parsed with a regex, not tomllib, because the package supports 3.10 and
tomllib arrived in 3.11.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
WORKFLOW = ROOT / ".github" / "workflows" / "publish-mcp.yml"

# The schema we publish against. An upstream bump must be a deliberate edit here.
SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"


def project_field(field: str) -> str:
    m = re.search(rf'^{field}\s*=\s*"([^"]+)"', PYPROJECT, re.M)
    assert m, f"{field} not found in pyproject.toml"
    return m.group(1)


class TestServerJsonMatchesRelease(unittest.TestCase):
    def test_versions_agree_across_the_release(self):
        version = project_field("version")
        self.assertEqual(SERVER["version"], version, "server.json version != pyproject")
        for pkg in SERVER["packages"]:
            self.assertEqual(
                pkg["version"], version,
                f"packages[{pkg['identifier']}].version != pyproject - the registry "
                "verifies this against PyPI, so a stale value publishes a stale record",
            )

    def test_package_identity_matches_the_distribution(self):
        pkg = SERVER["packages"][0]
        self.assertEqual(pkg["registryType"], "pypi")
        self.assertEqual(pkg["identifier"], project_field("name"))
        self.assertEqual(pkg["transport"]["type"], "stdio")

    def test_namespace_belongs_to_the_repository_owner(self):
        owner = SERVER["name"].split("/")[0]
        self.assertTrue(owner.startswith("io.github."), f"unexpected namespace: {owner}")
        self.assertIn(owner.removeprefix("io.github."), SERVER["repository"]["url"])

    def test_schema_is_pinned(self):
        self.assertEqual(SERVER["$schema"], SCHEMA)

    def test_description_fits_the_registry_limit(self):
        # The registry rejects a publish outright at 422 if this is too long, so the
        # limit belongs in CI rather than in a failed release run.
        self.assertLessEqual(
            len(SERVER["description"]), 100,
            f"description is {len(SERVER['description'])} chars; the MCP Registry "
            "allows 100 and answers 422 above that",
        )

    def test_description_keeps_the_measured_anchor(self):
        text = SERVER["description"]
        self.assertIn("581", text, "the description must carry the measured name-index figure")
        self.assertIn("71,929", text, "the description must carry the raw-JSON baseline")


class TestOwnershipMarker(unittest.TestCase):
    """The registry proves PyPI ownership by finding `mcp-name:` in the package
    README, which is the PyPI description (pyproject `readme = ...`)."""

    def readme(self) -> str:
        return (ROOT / project_field("readme")).read_text(encoding="utf-8")

    def test_marker_names_this_server(self):
        self.assertIn(
            f"mcp-name: {SERVER['name']}", self.readme(),
            "the README marker the MCP Registry checks is missing or points elsewhere",
        )

    def test_marker_is_hidden_not_prose(self):
        self.assertRegex(
            self.readme(), r"<!--\s*mcp-name:\s*\S+\s*-->",
            "the marker must stay an HTML comment so it does not render on PyPI",
        )


class TestPublishMechanism(unittest.TestCase):
    def test_workflow_exists_and_uses_oidc(self):
        self.assertTrue(WORKFLOW.is_file(),
                        "no registry publish workflow - the record can only be "
                        "refreshed by hand, which is how it went stale")
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("id-token: write", text, "OIDC needs the id-token permission")
        self.assertIn("login github-oidc", text)
        self.assertIn("mcp-publisher publish", text)

    def test_workflow_triggers_on_release(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(text, r"release:\s*\n\s*types:\s*\[published\]")


if __name__ == "__main__":
    unittest.main()
