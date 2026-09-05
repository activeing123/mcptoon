"""Guards for docs/tools/token-tax/index.html (the context-tax calculator).

The page makes three promises in its own copy: it runs entirely in the browser,
its numbers come from a measured anchor, and it states where the estimate is
soft. Each promise gets a test, so a future edit cannot quietly break one.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "tools" / "token-tax" / "index.html"
ANCHOR = ROOT / "assets" / "benchmark_tiktoken.json"

# Anything that could make the page talk to a machine other than the visitor's.
NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "sendBeacon", "new WebSocket", "import(",
    "@import", 'src="http', "url(http", "EventSource", "navigator.serviceWorker",
)


def anchor_row(tools: int = 255) -> dict:
    rows = json.loads(ANCHOR.read_text(encoding="utf-8"))
    return next(r for r in rows if r["tools"] == tools)


class TestCalculatorPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_page_exists_and_is_self_contained(self):
        self.assertTrue(PAGE.is_file(), "the calculator page is missing")
        self.assertLess(PAGE.stat().st_size, 40_000, "page should stay a small single file")

    def test_no_network_surface(self):
        hits = [p for p in NETWORK_PRIMITIVES if p in self.html]
        self.assertFalse(hits, f"calculator must not be able to talk to the network: {hits}")

    def test_no_external_subresources(self):
        """A canonical link is metadata the browser never fetches; these are not."""
        lowered = self.html.lower()
        for tag in ("<script src", "<img ", "<iframe", "<video", "<audio", "<object",
                    '<link rel="stylesheet"', '<link rel="preload"', '<link rel="icon"',
                    '<link rel="manifest"'):
            self.assertNotIn(tag, lowered, f"{tag} would pull something in from elsewhere")

    def test_every_script_targeted_id_exists(self):
        used = set(re.findall(r"\$\('([^']+)'\)", self.html))
        declared = set(re.findall(r'id="([^"]+)"', self.html))
        self.assertTrue(used, "no DOM ids found - did the render function change?")
        self.assertFalse(used - declared, f"script touches ids the markup lacks: {sorted(used - declared)}")

    def test_rates_are_the_measured_anchor_not_invented_numbers(self):
        row = anchor_row()
        expected = (
            f"raw: {row['json']} / {row['tools']}",
            f"slim: {row['slim']} / {row['tools']}",
            f"compact: {row['compact']} / {row['tools']}",
            f"toon: {row['toon']} / {row['tools']}",
        )
        for token in expected:
            self.assertIn(token, self.html, f"rate {token!r} is not derived from the anchor artifact")

    def test_anchor_savings_match_the_benchmark_artifact(self):
        row = anchor_row()
        pct = (1 - row["compact"] / row["json"]) * 100
        self.assertAlmostEqual(pct, row["compact_save"], places=1)
        self.assertGreaterEqual(pct, 99.0)

    def test_caveats_cannot_be_deleted_silently(self):
        self.assertRegex(self.html, r"2\.3.{0,3}4\.1 tokens per tool",
                         "the name-index softness disclosure was removed")
        self.assertIn("not part of the wheel", self.html,
                      "the repo-script disclosure was removed")
        self.assertRegex(self.html, r"nothing is sent anywhere|runs entirely in your browser",
                         "the local-only promise was removed")


class TestSocialPreview(unittest.TestCase):
    """The page exists to be shared. A share that renders as a bare text link is a
    lost click, so the card tags and the image behind them are gated here."""

    OG = PAGE.parent / "og.png"

    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def meta(self, prop):
        m = re.search(
            rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', self.html)
        return m.group(1) if m else None

    def test_card_tags_present(self):
        for prop in ("og:type", "og:title", "og:description", "og:url", "og:image",
                     "og:image:alt", "twitter:card"):
            self.assertTrue(self.meta(prop), f"{prop} missing - the share card degrades to a link")
        self.assertEqual(self.meta("twitter:card"), "summary_large_image")

    def test_image_is_same_origin_as_the_canonical(self):
        canonical = self.meta("og:url")
        self.assertTrue(canonical, "no og:url to compare against")
        origin = re.match(r"https?://[^/]+", canonical).group(0)
        self.assertTrue(self.meta("og:image").startswith(origin + "/"),
                        "og:image must be served from the same Pages origin")

    def test_image_file_exists_where_the_url_says(self):
        path = re.sub(r"^https?://[^/]+", "", self.meta("og:image")).strip("/")
        # A GitHub *project* page serves /docs under /<repo>/: the first URL segment is
        # the repository name, the remainder is relative to docs/.
        repo, _, rest = path.partition("/")
        self.assertEqual(repo, "mcptoon", f"unexpected Pages base segment: {repo!r}")
        target = ROOT / "docs" / PurePosixPath(rest)
        self.assertTrue(target.is_file(), f"{rest} is not in docs/ - the card would 404")

    def test_image_is_a_real_png_at_the_declared_size(self):
        raw = self.OG.read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n", "og.png is not a PNG")
        size = (int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big"))
        self.assertEqual(size, (1200, 630), "the card must be the size the crawlers ask for")
        self.assertEqual((self.meta("og:image:width"), self.meta("og:image:height")),
                         ("1200", "630"), "declared dimensions disagree with the file")

    def test_canonical_points_at_the_deployed_url(self):
        self.assertEqual(self.meta("og:url"),
                         "https://activeing123.github.io/mcptoon/tools/token-tax/")


class TestCalculatorIsLinked(unittest.TestCase):
    URL = "activeing123.github.io/mcptoon/tools/token-tax/"

    def test_both_readmes_link_the_page(self):
        for name in ("README.md", "README.zh-CN.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(self.URL, text, f"{name} does not link the calculator")

    def test_linked_path_exists_in_repo(self):
        self.assertTrue(PAGE.is_file())


if __name__ == "__main__":
    unittest.main()
