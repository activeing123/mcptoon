"""Every source file that exists on disk must also exist in git.

Added 2026-10-02, one day too late. `.gitignore` had `_*.py` under "Temp scripts"
(to throw away ad-hoc probe scripts), which also matched
`src/mcptoon/_toon/__init__.py`. The file was present in the working tree, so every
local test passed; `git status` showed nothing because the file was *ignored*, not
missing; and the wheel built locally was fine because it came from the working tree.
Only a clean checkout exposed it.

The cost was real: v0.8.6 shipped to PyPI without that file and `mcptoon --version`
died with an ImportError. The lesson generalizes past the underscore — any gitignore
rule that can match inside `src/` is a rule that can silently ship a broken wheel,
and "it works on my machine" is exactly the failure mode that hides it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _git(*args: str) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        pytest.skip(f"git unavailable ({p.stderr.strip()[:80]})")
    return p.stdout


pytestmark = pytest.mark.skipif(not (ROOT / ".git").exists(),
                                reason="not a git checkout")


class TestSourceFilesAreTracked:
    def test_no_python_file_under_src_is_untracked(self):
        tracked = set(_git("ls-files", "src/mcptoon").splitlines())
        on_disk = {
            p.relative_to(ROOT).as_posix()
            for p in SRC.rglob("*.py")
            if "__pycache__" not in p.parts
        }
        missing = sorted(on_disk - tracked)
        assert not missing, (
            "these files exist on disk but are not in git, so a clean checkout (CI, "
            f"a fresh clone, a published wheel) will not have them: {missing}. "
            "Check whether a .gitignore rule is eating them — `git check-ignore -v "
            "<path>` names the culprit rule.")

    def test_no_package_directory_is_missing_its_init(self):
        """A directory that looks like a package but has no __init__.py either ships
        as a namespace package (silently wrong) or gets skipped entirely."""
        bad = []
        for p in sorted(SRC.rglob("*")):
            if not p.is_dir() or "__pycache__" in p.parts:
                continue
            if not any(c.suffix == ".py" for c in p.iterdir() if c.is_file()):
                continue          # data-only directory, not a package
            if not (p / "__init__.py").exists():
                bad.append(p.relative_to(ROOT).as_posix())
        assert not bad, f"package directories without __init__.py: {bad}"

    def test_the_wheel_would_contain_every_module(self):
        """setuptools only ships what it can import as a package; this is the check
        that would have caught v0.8.6 before it was published."""
        import pkgutil

        import mcptoon

        pkg_dir = Path(mcptoon.__file__).parent
        importable = {m.name for m in pkgutil.iter_modules([str(pkg_dir)])}
        importable |= {
            d.name for d in pkg_dir.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()
        }
        assert "toon_vendored" in importable
        assert "_toon" in importable, (
            "_toon has no __init__.py, so it is a namespace package and "
            "`from ._toon import ...` will fail in an installed wheel")
