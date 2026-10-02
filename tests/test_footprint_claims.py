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
           "docs/tiktoken-benchmarks.md", "docs/README-details.md",
           "skills/mcptoon/SKILL.md")

# Sizes once written down that are wrong now. A doc may not resurrect them.
# "200KB" was on this list and came off it on 2026-09-21: the wheel really is
# 200,171-ish bytes now (205,171 bytes, 200.36 KB), so the string that used to be a
# stale claim is the current truth. A retired-value list is a claim too — it says
# "no surface may say this", which stops being true when the number becomes right.
# Keep only sizes that are wrong *now*.
# 2026-09-24: "206KB" joins the list — it was the truth when last measured, then the
# footer/welcome modules grew the wheel past it while the docs kept saying 206KB.
# "232KB" joins it the same day, a few hours after it was correct: the essentials pack
# moved the wheel to 233KB. A number can become stale within one working session, which
# is exactly why the guard pins a value and not a memory.
# "233KB" joins the list later the same day, when the number was finally measured
# against a real artifact instead of this checkout (see the note on WHEEL_KB below).
# The same sweep found two surfaces the guard never looked at — the agent-facing
# skills/mcptoon/SKILL.md (shipped to ClawHub, read by other agents) said 189KB, and
# the live docs/README-details.html said 206KB — so they join COVERED and their old
# values are retired here. The other historical spellings below are on the list so a
# stale figure cannot be reintroduced from an old draft.
# 2026-09-27: "227KB" joins the list. It was the truth for 0.8.1 (measured
# 2026-09-24), and it stopped being true at 0.8.2: the footer broadcast, the smart
# compressor, the report command and the restore/undo hardening added real code —
# footer.py +24KB, sync.py +18KB, cli.py +17KB, plus four new modules — and the wheel
# the CI job now builds is 297KB. The retired-value list keeps the old figure out.
RETIRED_KB = ("50KB", "250KB", "206KB", "232KB", "233KB", "189KB", "128KB",
              "146KB", "180KB", "156KB", "179KB", "190KB", "227KB", "297KB", "301KB",
              "304KB", "306KB", "307KB", "308KB", "322KB", "327KB", "332KB")

# Surfaces that state the suite total but were outside the badge guard.
# 2026-09-17: the landing pages, DEVELOPERS.md and ROADMAP.md still advertised
# 915 / 894 / v0.7.12 after the suite had moved on. A number a visitor reads is a
# claim wherever it lives, so these are compared against collection too.
TEST_CLAIM_SURFACES = ("README.md", "README.zh-CN.md", "DEVELOPERS.md", "ROADMAP.md",
                       "docs/index.html", "docs/index-zh.html")
# A live claim always pairs the total with the skipped count, which is what
# separates it from a historical "N passed" (ROADMAP's older entries, CHANGELOG).
# The separator may be glued to "passed" ("956 passed, 1 skipped"), which the
# first cut required a space before — so a stale total hid in plain sight until
# 2026-09-18. Whitespace is optional on both sides of the separator now.
# 2026-09-26: the skipped count is no longer required to be `1`. This box skips two
# (case-insensitive NTFS; WSL-stub bash), and a hardcoded `1` made the guard reject
# the honest total rather than the stale one. The count is still *required* — a
# claim without it stays exempt as historical — but it is now any number.
TEST_CLAIM = re.compile(r"(\d+) passed\s*(?:·|\+|,)\s*\d+ skipped")
# How many tests the tree skips. The docs state the *passed* count, which is
# `collected - skipped`, so the guard's gap must cover every skip or it rejects the
# truth. Pinned rather than measured because `--collect-only` does not report skips
# (they are a runtime decision) and running the suite inside the guard would cost
# minutes. It is deliberately small: if a third environmental skip appears the guard
# fails loudly and a human decides, instead of the gap quietly widening.
SKIP_SLACK = 2
# The badge and the one-line claim are the machine-readable spellings; prose hides
# the total in plain English ("1035 tests", "1035 个测试"). Two stragglers survived
# every earlier guard - README's contributor note said 931 and DEVELOPERS.md said 730
# - because nothing looked at that shape. This regex does, so it is judged the same way.
SUITE_PROSE = re.compile(r"(\d[\d,]{2,6})\s*(?:tests?\b|个测试)")
# What `pip install mcptoon` downloads. 304KB, measured 2026-09-29 with the same
# method as the previous pin (convert the tree to LF, then build a wheel): the
# 0.8.4 tree plus `bench_tokens.py` builds to 311,543 bytes = 304.24 KB (floor).
# `pip install mcptoon` pulls only the wheel.
#
# It was 301KB at 0.8.3/0.8.4 (2026-09-28, 308,629 bytes published). The delta is
# `bench_tokens.py` — the reproduction script moved into the package so a pip user
# can run the README-caliber table without a clone; a new module grows the wheel
# whether or not the feature is announced. 301KB joins RETIRED_KB for the same
# reason every earlier value did: it was true, and the tree moved past it.
#
# The measurement method is load-bearing and predates this pin: line endings are
# pure overhead inside the wheel. The earlier "233KB" was never a shipped number —
# it came from `python -m build --wheel --no-isolation` on a Windows checkout whose
# sources were CRLF (the local autocrlf default). The same 0.7.21 tree builds to
# 233,034 bytes with CRLF and 231,687 with LF, and PyPI's real 0.7.21 artifact is
# 231,659 — so a CRLF checkout inflates every claim by ~1.4KB. Convert to LF first,
# then build. The guard pins a value measured from a real artifact, not from one
# developer's line endings.
#
# 2026-09-29 (P3): 304KB → 306KB. `mcptoon import` (the `import` verb + `--file`)
# grew cli.py and discover.py, so the same LF method now builds to 313,371 bytes =
# 306.03 KB. The margin over the 305/306 line is ~27 bytes, which is inside this
# method's run-to-run noise (~±100 bytes of zip metadata; the method reproduces the
# published 0.8.4 wheel to within 16 bytes and the prior 304KB pin to within 92),
# so 306KB is the honest floor for the tree and 304KB is retired like every value
# before it.
# 2026-09-29 (completion fix): 306KB → 307KB. The four shell-completion scripts
# were rewritten to embed one canonical verb list instead of four stale copies, and
# the two edits before it (the `welcome` validation and the wrong-shape config
# guard) added a little code, so the LF method now builds to 314,703 bytes =
# 307.33 KB. That is past the 307 line by ~340 bytes — well outside the ±100-byte
# noise, so the floor genuinely moved and 306KB is retired like every value before.
# 2026-09-29 (harden + freeze): 307KB → 308KB. Two small hardenings — `add --http`
# validates the URL, and a config file we cannot honor is preserved as `.bak`
# instead of dropped — pushed the LF build to 315,707 bytes = 308.31 KB, past the
# 308 line by ~318 bytes (again beyond the ±100-byte noise). 307KB is retired.
# 2026-10-02 (TOON re-vendor): 308KB → 322KB. The vendored TOON encoder moved from a
# single 855-line `toon_vendored.py` into python-toon v0.2.0's real package layout under
# `_toon/` (9 modules). The LF build now measures 329,878 bytes = 322.15 KB. The jump is
# packaging, not bloat: 0.2.0's decoder alone is 23.7KB of source, and the old
# single-file copy had been kept in sync by hand. 308KB is retired like every value
# before it — and CHANGELOG.md keeps saying 308KB, because that is what 0.8.5 shipped.
# 2026-10-02 (0.8.8 honesty sweep): 322KB → 327KB. The pre-release audit fixed ten
# reported defects (a TOML config deleted by quickstart, failed writes reported as
# successes, an unreachable server counted in three places) plus the tests that pin
# them, and the LF build now measures 335,476 bytes = 327.61 KB — past the 327 line
# by ~630 bytes, well outside the ±100-byte noise. 322KB is retired; CHANGELOG.md
# keeps saying 322KB, because that is what 0.8.7 shipped.
# 2026-10-02 (0.8.9 lossless sweep): 327KB → 334KB. Two behaviours changed shape and
# both cost bytes: the CCR store now keeps an entry it used to refuse outright (a
# payload over 1 MB was dropped *and* left the compressed view with no handle, so
# "retrieve" was a dead end past that size), and a payload this conversation already
# received is answered with a one-line reference instead of the body — including the
# per-request session scoping that keeps concurrent HTTP agents apart. The LF build
# measures 341,580 bytes = 333.57 KB — past the 334 line. 327KB is retired like every
# value before it; CHANGELOG.md keeps saying 327KB for 0.8.8, because that shipped.
# 2026-10-02 (0.8.10): 342,209 bytes = 334.19 KB — same claim, 629 bytes further
# from the boundary. The 0.8.10 fixes add one eviction guard and a size accounting
# correction, so the wheel grew without crossing a KB line.
WHEEL_KB = "334KB"


def modules() -> list[Path]:
    """Every shipped .py under src/mcptoon, **recursively**.

    Was `SRC.glob("*.py")`, which is not recursive and therefore silently ignored
    subpackages. That was harmless while src/mcptoon had none; `_toon/` (the vendored
    python-toon package, added 2026-10-02) made it the first one, and the README's
    "N lines across M modules" claim would have kept describing a codebase that no
    longer existed. A guard that cannot see part of the tree is not a guard.
    """
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


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
                    "docs/tiktoken-benchmarks.md", "docs/README-details.md",
                    "skills/mcptoon/SKILL.md"):
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
                    msg=(f"{rel} claims {n:,} lines; src/mcptoon/**/*.py is {self.lines:,} "
                         "physical lines"))
        self.assertGreater(seen, 0, "no line-count claim found - did the wording change?")

    def test_test_count_badge_has_not_drifted(self):
        """`Tests-<n> passed` drifted 694 -> 703 -> 713 unnoticed, and this guard's own
        author then wrote 736 when the truth was 737. A stale badge is a stale claim, so
        the number is compared against collection rather than against someone's memory.
        The gap allows only what skipped tests can explain (`SKIP_SLACK`)."""
        proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                              capture_output=True, text=True, cwd=ROOT)
        collected = sum(1 for line in proc.stdout.splitlines() if "::" in line)
        self.assertGreater(collected, 500, "collection failed - the badge cannot be judged")
        for rel in ("README.md", "README.zh-CN.md"):
            for n in re.findall(r"Tests-(\d+)%20passed", self.texts[rel]):
                self.assertTrue(collected - SKIP_SLACK <= int(n) <= collected,
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
        entries and the CHANGELOG record what was true then and must not be edited.

        2026-09-17: the first cut allowed a gap of 5, and the guard's own two new
        tests pushed the suite past the badge while every surface still said 925.
        The gap is now the number of tests the tree actually skips (`SKIP_SLACK`), so
        a stale total cannot hide."""
        proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                              capture_output=True, text=True, cwd=ROOT)
        collected = sum(1 for line in proc.stdout.splitlines() if "::" in line)
        self.assertGreater(collected, 500, "collection failed - the claims cannot be judged")
        seen = 0
        for rel in TEST_CLAIM_SURFACES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for n in TEST_CLAIM.findall(text):
                seen += 1
                self.assertTrue(collected - SKIP_SLACK <= int(n) <= collected,
                                f"{rel} advertises {n} passed but {collected} tests are collected")
        self.assertGreater(seen, 0, "no live suite-total claim found - did the wording change?")

    def test_prose_suite_totals_match_collection(self):
        """The total is also stated in prose, and that spelling had no guard.

        README's contributor note still said "(931 tests" and DEVELOPERS.md plus
        docs/tiktoken-benchmarks.md said "730 tests" - three stale claims that survived
        every earlier check because they never pair the total with "1 skipped". Prose
        is judged the same way the badge is.

        The regex only fires when the number is immediately followed by "test(s)" or
        "个测试", so the token figures this repo is full of ("8,282 tokens", "581
        tokens", "300-page book") are never mistaken for a suite total."""
        proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                              capture_output=True, text=True, cwd=ROOT)
        collected = sum(1 for line in proc.stdout.splitlines() if "::" in line)
        self.assertGreater(collected, 500, "collection failed - the prose claims cannot be judged")
        seen = 0
        for rel in TEST_CLAIM_SURFACES + ("docs/tiktoken-benchmarks.md",):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for raw in SUITE_PROSE.findall(text):
                n = int(raw.replace(",", ""))
                seen += 1
                self.assertTrue(collected - SKIP_SLACK <= n <= collected,
                                f"{rel} says {raw} tests but {collected} are collected")
        self.assertGreater(seen, 0, "no prose suite-total claim found - did the wording change?")
        # Pin the exclusion rule so a later wording change cannot silently widen the net.
        self.assertEqual(SUITE_PROSE.findall("581 tests"), ["581"])
        self.assertEqual(SUITE_PROSE.findall("1036 个测试"), ["1036"])
        self.assertEqual(SUITE_PROSE.findall("8,282 tokens"), [],
                         "a token figure must not be read as a suite total")
        self.assertEqual(SUITE_PROSE.findall("a 300-page book"), [])

    def test_claim_regex_sees_every_separator_spelling(self):
        """The guard missed "956 passed, 1 skipped" for two days because it required a
        space before the separator. Every spelling a contributor might write must match,
        or a stale total hides where the guard cannot look."""
        for text in ("978 passed · 1 skipped", "978 passed + 1 skipped",
                     "978 passed, 1 skipped", "978 passed,1 skipped"):
            self.assertEqual(TEST_CLAIM.findall(text), ["978"], text)
        # a historical line without the skipped count stays exempt
        self.assertEqual(TEST_CLAIM.findall("931 tests passed in v0.7.14"), [])

    def test_no_retired_version_in_the_live_claim(self):
        """ROADMAP's header still said v0.7.12 when 0.7.14 was current. The version in
        the same one-line claim must be the one in pyproject.

        pyproject is parsed with a regex, not tomllib, for the same reason
        test_registry_sync.py does it: the package supports 3.10 and tomllib arrived
        in 3.11. Using tomllib here turned CI red on 3.10 the first time round."""
        m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(
            encoding="utf-8"), re.M)
        self.assertTrue(m, "version not found in pyproject.toml")
        version = m.group(1)
        for rel in ("DEVELOPERS.md", "ROADMAP.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for claim in re.finditer(r"v(\d+\.\d+\.\d+)[ ·|]+(\d+) passed", text):
                self.assertEqual(claim.group(1), version,
                                 f"{rel} claims v{claim.group(1)}; pyproject says {version}")


if __name__ == "__main__":
    unittest.main()
