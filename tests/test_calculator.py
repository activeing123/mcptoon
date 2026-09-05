"""Guards for the context-tax calculator pages (docs/tools/token-tax/).

The English and Chinese pages are separate files that must behave as one tool: same
math, same anchor, same promises. Each promise in their copy therefore gets a test,
run against both pages, plus cross-page tests that fail if the two drift apart.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "tools" / "token-tax"
PAGES = {"en": DOCS / "index.html", "zh": DOCS / "zh" / "index.html"}
ANCHOR = ROOT / "assets" / "benchmark_tiktoken.json"
SITE = "https://activeing123.github.io/mcptoon"

# Anything that could make a page talk to a machine other than the visitor's.
NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "sendBeacon", "new WebSocket", "import(",
    "@import", 'src="http', "url(http", "EventSource", "navigator.serviceWorker",
)


def anchor_row(tools: int = 255) -> dict:
    rows = json.loads(ANCHOR.read_text(encoding="utf-8"))
    return next(r for r in rows if r["tools"] == tools)


def math_block(html: str) -> str:
    m = re.search(r"/\*__MATH_START__\*/(.*?)/\*__MATH_END__\*/", html, re.S)
    assert m, "the math block lost its markers"
    return m.group(1)


def meta(html: str, prop: str):
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', html)
    return m.group(1) if m else None


class _PageTests:
    """Mixin, not a TestCase: pytest collects unittest.TestCase subclasses by base
    class, so inheriting here would run every test once with no page bound."""

    PAGE: Path

    @classmethod
    def setUpClass(cls):
        cls.html = cls.PAGE.read_text(encoding="utf-8")

    def test_page_exists_and_is_self_contained(self):
        self.assertTrue(self.PAGE.is_file(), f"{self.PAGE} is missing")
        self.assertLess(self.PAGE.stat().st_size, 40_000, "pages should stay small single files")

    def test_no_network_surface(self):
        hits = [p for p in NETWORK_PRIMITIVES if p in self.html]
        self.assertFalse(hits, f"calculator must not reach the network: {hits}")

    def test_no_external_subresources(self):
        """A canonical/alternate link is metadata the browser never fetches; these are not."""
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
        for token in (f"raw: {row['json']} / {row['tools']}", f"slim: {row['slim']} / {row['tools']}",
                      f"compact: {row['compact']} / {row['tools']}", f"toon: {row['toon']} / {row['tools']}"):
            self.assertIn(token, self.html, f"rate {token!r} is not derived from the anchor artifact")

    def test_caveats_cannot_be_deleted_silently(self):
        self.assertRegex(self.html, r"2\.3.{0,3}4\.1", "the name-index softness disclosure was removed")
        self.assertIn("wheel", self.html, "the repo-script disclosure was removed")
        self.assertRegex(self.html, "nothing is sent anywhere|不发往任何地方|nothing is uploaded|不上传",
                         "the local-only promise was removed")

    def test_card_tags_present(self):
        for prop in ("og:type", "og:title", "og:description", "og:url", "og:image",
                     "og:image:alt", "twitter:card"):
            self.assertTrue(meta(self.html, prop), f"{prop} missing - the share card degrades to a link")
        self.assertEqual(meta(self.html, "twitter:card"), "summary_large_image")

    def test_image_is_same_origin_and_exists(self):
        image = meta(self.html, "og:image")
        self.assertTrue(image.startswith(SITE), "og:image must be served from the Pages origin")
        path = urlsplit(image).path.strip("/")
        self.assertTrue(path.startswith("mcptoon/"), f"unexpected Pages base: {path}")
        target = ROOT / "docs" / Path(*path.split("/")[1:])
        self.assertTrue(target.is_file(), f"{image} is not in docs/ - the card would 404")
        raw = target.read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n", "og image is not a PNG")
        size = (int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big"))
        self.assertEqual(size, (1200, 630), "the card must be the size crawlers ask for")
        self.assertEqual((meta(self.html, "og:image:width"), meta(self.html, "og:image:height")),
                         ("1200", "630"), "declared dimensions disagree with the file")

    def test_canonical_is_the_deployed_url(self):
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', self.html).group(1)
        self.assertEqual(meta(self.html, "og:url"), canonical, "og:url and canonical disagree")
        expected = SITE + "/tools/token-tax" + ("/zh/" if self.PAGE.parent.name == "zh" else "/")
        self.assertEqual(canonical, expected, "canonical does not match where Pages serves this page")

    def test_hreflang_cluster_names_this_page_and_x_default(self):
        alts = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)"', self.html))
        self.assertIn("x-default", alts, "no x-default in the hreflang cluster")
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', self.html).group(1)
        self.assertIn(canonical, alts.values(),
                      "each page must list its own URL in its hreflang cluster")


class TestPageEn(_PageTests, unittest.TestCase):
    PAGE = PAGES["en"]


class TestPageZh(_PageTests, unittest.TestCase):
    PAGE = PAGES["zh"]


class TestPagesAgree(unittest.TestCase):
    """Two files, one tool."""

    @classmethod
    def setUpClass(cls):
        cls.en = PAGES["en"].read_text(encoding="utf-8")
        cls.zh = PAGES["zh"].read_text(encoding="utf-8")

    def test_math_block_is_byte_identical(self):
        self.assertEqual(math_block(self.en), math_block(self.zh),
                         "the two language pages compute different numbers")

    def test_anchor_savings_match_the_benchmark_artifact(self):
        row = anchor_row()
        pct = (1 - row["compact"] / row["json"]) * 100
        self.assertAlmostEqual(pct, row["compact_save"], places=1)
        self.assertGreaterEqual(pct, 99.0)

    def test_hreflang_points_at_the_other_page(self):
        for html, other_url in ((self.en, SITE + "/tools/token-tax/zh/"),
                                (self.zh, SITE + "/tools/token-tax/")):
            alts = re.findall(r'<link rel="alternate" hreflang="[^"]+" href="([^"]+)"', html)
            self.assertIn(other_url, alts, f"{other_url} is missing from the cluster")

    def test_each_page_links_the_other_in_body(self):
        self.assertIn('href="zh/"', self.en, "the English page has no visible 中文 link")
        self.assertIn('href="../"', self.zh, "the Chinese page has no visible English link")


class TestCalculatorIsLinked(unittest.TestCase):
    def test_both_readmes_link_a_token_tax_page(self):
        for name in ("README.md", "README.zh-CN.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("activeing123.github.io/mcptoon/tools/token-tax", text,
                          f"{name} does not link the calculator")

    def test_pages_site_root_links_the_tool(self):
        """docs/README.md is rendered as the Pages site root, so it is the one internal
        path a crawler reaching the domain can follow - in either language."""
        text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("tools/token-tax", text, "the site root does not link the calculator")
        self.assertIn("tools/token-tax/zh/", text, "the site root does not link the Chinese page")


if __name__ == "__main__":
    unittest.main()
