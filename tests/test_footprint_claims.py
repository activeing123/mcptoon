"""Guard the footprint claims in the docs the Pages site publishes.

Enabling Pages turned repo markdown into public web pages, and these files had drifted:
one page said 50KB, another 200KB, a third 250KB, and two quoted test counts from
releases long past.

The line count here is deliberately the *physical* line count of src/mcptoon/*.py.
"Lines of code" has no single definition - three reasonable ways to count this tree
give 7,509, 7,873 and 8,328 - so a public claim that depends on the definition is a
claim an auditor cannot check. Physical lines are `wc -l` and beyond argument.

README.md and README.zh-CN.md are not covered yet: they carry the same stale trio
(~250KB, ~6,800 lines, 14 modules) and are mid-rewrite by a human. Add them to COVERED
once that lands.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mcptoon"

# Files whose claims this guard owns.
COVERED = ("DEVELOPERS.md", "docs/comparison.md", "docs/tiktoken-benchmarks.md")

# Sizes once written down that are wrong now. A doc may not resurrect them.
RETIRED_KB = ("50KB", "200KB", "250KB")
# What `pip install mcptoon` downloads: mcptoon-0.7.5-py3-none-any.whl is 131,052 bytes,
# measured from PyPI on 2026-09-05. Re-measure at each release.
WHEEL_KB = "128KB"


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
        for rel in ("docs/comparison.md", "docs/tiktoken-benchmarks.md"):
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

    def test_no_page_links_a_file_that_does_not_exist(self):
        """comparison.html advertised a companion page that was never written."""
        for rel, text in self.texts.items():
            base = (ROOT / rel).parent
            for target in re.findall(r"\]\(([^)#?]+\.(?:md|html))\)", text):
                if target.startswith(("http", "mailto:")):
                    continue
                self.assertTrue((base / target).exists(),
                                f"{rel} links to {target}, which is not in the repo")


if __name__ == "__main__":
    unittest.main()
