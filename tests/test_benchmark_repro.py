"""Pin the TOON benchmark so it can never become an unreproducible claim again.

Background (2026-10-02). The README's headline "~34%" was measured once on 2026-08-18
by a script that no longer existed, on a corpus that was never committed. Two problems
followed:

1. Nobody — including us — could reproduce it, so the encoder moving from python-toon
   0.1.1 to 0.2.0 went unnoticed.
2. Worse, that 34% was a *tool schema* number quoted as if it described *call results*,
   which is what `--toon` actually encodes. The two payloads behave very differently.

These tests exist to make (1) and (2) impossible to reintroduce:

- The committed assets must match a fresh run of scripts/make_benchmark.py, so the
  numbers in the repo are reproducible from the repo.
- The historical assets/benchmark_tiktoken.json must stay untouched. It is a real
  measurement with a lost corpus; overwriting it with numbers from a corpus invented
  later would trade a real number for a reproducible one.
- No shipped doc may attribute a flat percentage to `--toon` on call results.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent / "mcptoon"
ASSETS = ROOT / "assets"
HISTORICAL = ASSETS / "benchmark_tiktoken.json"

tiktoken = pytest.importorskip("tiktoken", reason="the benchmark needs tiktoken")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "make_benchmark", ROOT / "scripts" / "make_benchmark.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "src"))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load_generator()


class TestBenchmarkIsReproducible:
    def test_schema_asset_matches_a_fresh_run(self, gen):
        committed = json.loads((ASSETS / "benchmark_schemas_repro.json").read_text("utf-8"))
        fresh = gen.measure(gen.build_corpus(gen.SEED))
        assert [r["tools"] for r in committed] == [r["tools"] for r in fresh]
        for c, f in zip(committed, fresh):
            assert c["json"] == f["json"], "corpus drifted from the committed asset"
            assert c["toon"] == f["toon"]
            assert c["toon_save"] == f["toon_save"]

    def test_result_asset_matches_a_fresh_run(self, gen):
        committed = json.loads((ASSETS / "benchmark_results.json").read_text("utf-8"))
        fresh = gen.measure_results(gen.build_result_corpus(gen.SEED))
        assert committed["json"] == fresh["json"]
        assert committed["toon"] == fresh["toon"]
        assert committed["toon_save"] == fresh["toon_save"]
        assert set(committed["by_shape"]) == {"record", "list", "records_table", "blob"}

    def test_the_generator_is_deterministic(self, gen):
        a = gen.measure(gen.build_corpus(gen.SEED))
        b = gen.measure(gen.build_corpus(gen.SEED))
        assert a == b, "same seed must give the same corpus; otherwise it is not reproducible"


class TestHistoricalBenchmarkIsNotOverwritten:
    """The 2026-08-18 table is a real measurement. Losing a corpus is not a licence to
    fabricate its replacement, and its compact figure (99.2%) is the flagship number in
    the README — a later synthetic corpus measures 98.4%, which is an artifact of that
    corpus, not a regression."""

    def test_historical_rows_are_intact(self):
        rows = json.loads(HISTORICAL.read_text("utf-8"))
        assert [r["tools"] for r in rows] == [5, 50, 255]
        assert rows[-1]["json"] == 71929
        assert rows[-1]["compact"] == 581
        assert rows[-1]["compact_save"] == 99.2

    def test_generator_never_targets_the_historical_file(self, gen):
        assert gen.OUT.name == "benchmark_schemas_repro.json"
        assert gen.OUT.resolve() != HISTORICAL.resolve()


class TestNoFlatPercentageClaimedForCallResults:
    """`--toon` encodes call results. A schema number must never be quoted as its
    saving — that conflation is what got our upstream PR closed."""

    SHIPPED = [
        "README.md", "README.zh-CN.md", "docs/TOON_SPEC.md", "docs/comparison.md",
        "docs/README-details.md", "src/mcptoon/cli.py", "src/mcptoon/output.py",
    ]

    # A line may still mention 34% when it is NOT claiming it: denying the flat figure,
    # explaining where it came from, or quoting the schema table it really belongs to.
    ALLOWED = (
        "benchmark_tiktoken.json",
        "not a flat 34%",
        "flat 34%:",
        "不是稳定的 34%",
        "quoted as if it were the result number",
        "71,929",
        "47,438",
    )

    @pytest.mark.parametrize("rel", SHIPPED)
    def test_no_bare_34_percent_attached_to_toon(self, rel):
        p = ROOT / rel
        for i, line in enumerate(p.read_text("utf-8").splitlines(), 1):
            if "34%" not in line:
                continue
            if any(a in line for a in self.ALLOWED):
                continue
            # A line may still mention 34% if it also gives the result-side range.
            if "1.8" in line or "48.6" in line or "5.7" in line:
                continue
            raise AssertionError(
                f"{rel}:{i} quotes a flat 34% for --toon: {line.strip()[:120]}")
