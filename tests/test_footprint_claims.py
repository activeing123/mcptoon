"""Guard the footprint claims in the docs the Pages site publishes.

Enabling Pages turned repo markdown into public web pages, and these files had drifted:
one page said 50KB, another 200KB, a third 250KB, and two quoted test counts from
releases long past.

The line count here is deliberately the *physical* line count of src/mcptoon/*.py.
"Lines of code" has no single definition - three reasonable ways to count this tree
give 7,509, 7,873 and 8,328 - so a public claim that depends on the definition is a
claim an auditor cannot check. Physical lines are `wc -l` and beyond argument.

README.md and README.zh-CN.md joined COVERED on 2026-09-05, after their stale trio
(~250KB, ~6,800 lines, 14 modules) and a badge that had drifted twice were corrected.
They are the highest-traffic surface in the repo, so they are the ones this guard most
needs to own.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mcptoon"

# Files whose claims this guard owns.
COVERED = ("README.md", "README.zh-CN.md", "DEVELOPERS.md", "docs/comparison.md",
           "docs/tiktoken-benchmarks.md")

# Sizes once written down that are wrong now. A doc may not resurrect them.
RETIRED_KB = ("50KB", "200KB", "250KB")

# Surfaces that state the suite total but were outside the badge guard.
# 2026-09-17: the landing pages, DEVELOPERS.md and ROADMAP.md still advertised
# 915 / 894 / v0.7.12 after the suite had moved on. A number a visitor reads is a
# claim wherever it lives, so these are compared against collection too.
TEST_CLAIM_SURFACES = ("README.md", "README.zh-CN.md", "DEVELOPERS.md", "ROADMAP.md",
                       "docs/index.html", "docs/index-zh.html")
# A live claim always pairs the total with the skipped count, which is what
# separates it from a historical "N passed" (ROADMAP's older entries, CHANGELOG).
TEST_CLAIM = re.compile(r"(\d+) passed (?:·|\+|,) 1 skipped")
# What `pip install mcptoon` downloads: mcptoon-0.7.14-py3-none-any.whl is 158,271 bytes
# (154.6 KB), measured from PyPI on 2026-09-17. Re-measure at each release.
WHEEL_KB = "155KB"


def modules() -> list[Path]:
    return sorted(SRC.glob("*.py"))


def physical_lines() -> int:
    return sum(len(p.read_text(encoding="utf-8").splitlines()) for p in modules())


class TestFootprintClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n_modules = len(modules())
        cls.lines = physical_lines()
        cls.texts = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in COVERED}

    def test_measured_numbers_are_sane(self):
        """If the measurement itself breaks, every other test here passes vacuously."""
        self.assertGreater(self.n_modules, 10)
        self.assertGreater(self.lines, 5000)

    def test_no_retired_size_claims(self):
        for rel, text in self.texts.items():
            for bad in RETIRED_KB:
                self.assertNotIn(bad, text, f"{rel} still claims mcptoon is {bad}")

    def test_the_current_wheel_size_is_stated_where_it_matters(self):
        """The live pages must carry the number that is true, not merely lack the old
        wrong ones - otherwise a later edit can delete the claim and pass quietly."""
        for rel in ("README.md", "README.zh-CN.md", "docs/comparison.md",
                    "docs/tiktoken-benchmarks.md"):
            self.assertIn(WHEEL_KB, self.texts[rel], f"{rel} no longer states the {WHEEL_KB} wheel")

    def test_module_count_claims_match_the_tree(self):
        pat = re.compile(r"(\d{1,3})\s*(?:个)?\s*模块|\b(\d{1,3}) modules\b")
        seen = 0
        for rel, text in self.texts.items():
            for m in pat.finditer(text):
                seen += 1
                n = int(m.group(1) or m.group(2))
                self.assertEqual(n, self.n_modules,
                                 f"{rel} says {n} modules; src/mcptoon has {self.n_modules}")
        self.assertGreater(seen, 0, "no module-count claim found - did the wording change?")

    def test_line_count_claims_match_the_tree(self):
        pat = re.compile(r"~?([\d,]{4,6})\s*(?:行|lines of)")
        seen = 0
        for rel, text in self.texts.items():
            for m in pat.finditer(text):
                n = int(m.group(1).replace(",", ""))
                seen += 1
                self.assertAlmostEqual(
                    n, self.lines, delta=self.lines * 0.02,
                    msg=(f"{rel} claims {n:,} lines; src/mcptoon/*.py is {self.lines:,} "
                         "physical lines"))
        self.assertGreater(seen, 0, "no line-count claim found - did the wording change?")

    def test_test_count_badge_has_not_drifted(self):
        """`Tests-<n> passed` drifted 694 -> 703 -> 713 unnoticed, and this guard's own
        author then wrote 736 when the truth was 737. A stale badge is a stale claim, so
        the number is compared against collection rather than against someone's memory.
        The gap allows only what skipped tests can explain."""
        proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                              capture_output=True, text=True, cwd=ROOT)
        collected = sum(1 for line in proc.stdout.splitlines() if "::" in line)
        self.assertGreater(collected, 500, "collection failed - the badge cannot be judged")
        for rel in ("README.md", "README.zh-CN.md"):
            for n in re.findall(r"Tests-(\d+)%20passed", self.texts[rel]):
                self.assertTrue(collected - 5 <= int(n) <= collected,
                                f"{rel} badge says {n} but {collected} tests are collected")

    def test_no_page_links_a_file_that_does_not_exist(self):
        """comparison.html advertised a companion page that was never written."""
        for rel, text in self.texts.items():
            base = (ROOT / rel).parent
            for target in re.findall(r"\]\(([^)#?]+\.(?:md|html))\)", text):
                if target.startswith(("http", "mailto:")):
                    continue
                self.assertTrue((base / target).exists(),
                                f"{rel} links to {target}, which is not in the repo")

    def test_the_favicon_the_theme_links_exists(self):
        """The Pages theme injects /<repo>/favicon.ico on every rendered page; it 404ed
        until docs/favicon.ico landed. Repo-relative link checks cannot see it."""
        icon = ROOT / "docs" / "favicon.ico"
        self.assertTrue(icon.is_file(), "docs/favicon.ico is missing - every page 404s on it")
        self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00", "not an ICO file")

    def test_suite_total_is_the_same_on_every_surface(self):
        """The badge guard only saw the two READMEs. The landing pages, DEVELOPERS.md
        and ROADMAP.md kept advertising 915 / 894 / v0.7.12 for days after the suite
        moved on, because nothing compared them against collection.

        Only the live claim (total + skipped, one line) is judged: ROADMAP's older
        entries and the CHANGELOG record what was true then and must not be edited."""
        proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                              capture_output=True, text=True, cwd=ROOT)
        collected = sum(1 for line in proc.stdout.splitlines() if "::" in line)
        self.assertGreater(collected, 500, "collection failed - the claims cannot be judged")
        seen = 0
        for rel in TEST_CLAIM_SURFACES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for n in TEST_CLAIM.findall(text):
                seen += 1
                self.assertTrue(collected - 5 <= int(n) <= collected,
                                f"{rel} advertises {n} passed but {collected} tests are collected")
        self.assertGreater(seen, 0, "no live suite-total claim found - did the wording change?")

    def test_no_retired_version_in_the_live_claim(self):
        """ROADMAP's header still said v0.7.12 when 0.7.14 was current. The version in
        the same one-line claim must be the one in pyproject."""
        import tomllib
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        for rel in ("DEVELOPERS.md", "ROADMAP.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for m in re.finditer(r"v(\d+\.\d+\.\d+)[ ·|]+(\d+) passed", text):
                self.assertEqual(m.group(1), version,
                                 f"{rel} claims v{m.group(1)}; pyproject says {version}")


if __name__ == "__main__":
    unittest.main()
