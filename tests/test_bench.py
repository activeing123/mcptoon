# Copyright 2025-2026 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for `mcptoon bench` — the on-your-machine proof of both halves.

The load-bearing claim is the de-duplication: a machine whose agent skill folders
are junctions onto one real catalog is the *normal* multi-agent layout, and walking
each root naively inflates the number by the link count. A bench that over-reports
is worse than no bench, so that behaviour is pinned here.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import bench  # noqa: E402


def write_skill(root: Path, slug: str, body: str = "body text", *,
                layout: str = "flat") -> Path:
    base = root / "skills" if layout == "nested" else root
    d = base / slug
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(f"---\nname: {slug}\ndescription: does {slug} things\n---\n\n{body}\n",
                  encoding="utf-8")
    return md


def run_bench(argv, env=None):
    """Run bench with a sandboxed index/ledger so no developer state is touched."""
    buf = StringIO()
    sandbox = Path(tempfile.gettempdir()) / "mcptoon-bench-tests"
    base = dict(env or {})
    base.setdefault("MCPTOON_SKILLS_INDEX", str(sandbox / "no-index.json"))
    base.setdefault("MCPTOON_SKILLS_USAGE", str(sandbox / "no-usage.json"))
    fmt = "json" if "--json" in argv else "auto"
    with patch.dict(os.environ, base, clear=False), redirect_stdout(buf):
        bench.run_bench(argv, fmt)
    return buf.getvalue()


# ─── de-duplication: the whole reason this module is careful ───

def test_same_catalog_via_two_roots_counts_once(tmp_path):
    """Two roots pointing at the same real files must not double the catalog."""
    real = tmp_path / "real"
    write_skill(real, "alpha", "a" * 400)
    write_skill(real, "beta", "b" * 400)
    # A second "root" that is the same directory by another path (symlink or a
    # junction on Windows) — the layout that inflates a naive walk.
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        alias = real  # platform without symlink rights: same path, still one count

    files, dupes = bench._unique_skill_files([real, alias])
    slugs = sorted(s for s, _ in files)
    assert slugs == ["alpha", "beta"], f"catalog counted {len(files)} skills: {slugs}"


def test_duplicate_roots_are_reported_not_hidden(tmp_path):
    real = tmp_path / "real"
    write_skill(real, "alpha")
    files, dupes = bench._unique_skill_files([real, real])
    assert len(files) == 1
    assert dupes == 1, "a skipped duplicate must be counted so the note can be printed"


def test_nested_layout_is_found(tmp_path):
    """`<root>/skills/<slug>` counts too — the catalog manager accepts both."""
    write_skill(tmp_path, "nested-one", layout="nested")
    files, _ = bench._unique_skill_files([tmp_path])
    assert [s for s, _ in files] == ["nested-one"]


def test_skip_dirs_and_dotdirs_are_ignored(tmp_path):
    write_skill(tmp_path, "_index")          # the index's own meta-dir
    write_skill(tmp_path, "real")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "SKILL.md").write_text("x", encoding="utf-8")
    files, _ = bench._unique_skill_files([tmp_path])
    assert [s for s, _ in files] == ["real"]


def test_missing_root_is_not_an_error(tmp_path):
    files, dupes = bench._unique_skill_files([tmp_path / "nope"])
    assert files == [] and dupes == 0


# ─── caliber honesty ───

def test_pct_is_none_without_a_baseline():
    assert bench._pct(5, 0) is None


def test_pct_keeps_three_decimals():
    """Two decimals would round a tiny pointer to '100.0%', which reads as a typo."""
    assert bench._pct(39, 961164) == 99.996


def test_fallback_tokenizer_is_labelled_not_silent():
    """Without tiktoken the numbers must be flagged, never passed off as measured."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "tiktoken":
            raise ImportError("simulated: tiktoken not installed")
        return real_import(name, *a, **kw)

    with patch.object(builtins, "__import__", fake_import):
        encode, name, exact = bench._tokenizer()
    assert exact is False
    assert "estimate" in name.lower()
    assert encode("abcdefgh") == 2  # len//4, floored at 1


# ─── end-to-end ───

def test_bench_prints_both_halves(tmp_path, capsys):
    write_skill(tmp_path, "alpha", "x" * 800)
    write_skill(tmp_path, "beta", "y" * 800)
    out = run_bench(["--roots", str(tmp_path)])
    assert "MCP tools" in out or "Agent skills" in out
    assert "Agent skills" in out, "the skills half is the point of this command"
    assert "every SKILL.md, full text" in out
    assert "skills manifest (pointer)" in out


def test_bench_json_is_machine_readable(tmp_path):
    write_skill(tmp_path, "alpha", "x" * 800)
    out = run_bench(["--roots", str(tmp_path), "--json"], {"MCPTOON_SKILLS_USAGE": str(tmp_path / "u.json")})
    data = json.loads(out)
    assert data["skills"]["count"] == 1
    assert "exact" in data and "tokenizer" in data
    assert data["skills"]["query"] == "make a PDF"


def test_bench_reports_the_query_it_used(tmp_path):
    """The resolve row is query-dependent, so the query must be visible."""
    write_skill(tmp_path, "alpha", "x" * 800)
    out = run_bench(["--roots", str(tmp_path), "--query", "zzz"])
    assert "zzz" in out


def test_bench_says_what_to_run_when_nothing_is_measurable(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    with patch.object(bench, "_load_cached_tools", lambda: {}):
        out = run_bench(["--roots", str(empty)])
    assert "Nothing to measure" in out
    assert "mcptoon manifest" in out and "skills index" in out


def test_bench_does_not_write_the_usage_ledger(tmp_path):
    """A measurement must never mutate state — bench is read-only by design."""
    write_skill(tmp_path, "alpha", "x" * 800)
    usage = tmp_path / "usage.json"
    run_bench(["--roots", str(tmp_path), "--json"], {"MCPTOON_SKILLS_USAGE": str(usage)})
    assert not usage.exists(), "bench must not touch the usage ledger"
