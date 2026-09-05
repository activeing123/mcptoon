"""README hygiene guards.

Two real defects shipped and were fixed in the v0.7.4 window (2026-09-05):

1. Relative links in README.md. PyPI renders README.md as the project long
   description and resolves relative targets against the *project page*
   (https://pypi.org/project/mcptoon/DEVELOPERS.md/), so every relative link
   404s for PyPI visitors. README.md must use absolute URLs.
2. A Chinese-only chart (assets/token-savings.svg) embedded in the English
   README. Assets referenced by README.md must not contain CJK text.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

RELATIVE_LINK = re.compile(r"""\]\((?!https?://|#|mailto:|data:)[^)\s]+\)""")
RELATIVE_ATTR = re.compile(r'\b(?:src|href)="(?!https?://|data:|#)([^"]+)')
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_has_no_relative_markdown_links():
    offenders = [m.group(0) for m in RELATIVE_LINK.finditer(_readme_text())]
    assert not offenders, (
        "README.md links must be absolute: PyPI resolves relative targets "
        f"against the project page and 404s. Found: {offenders}"
    )


def test_readme_has_no_relative_src_or_href():
    offenders = [m.group(1) for m in RELATIVE_ATTR.finditer(_readme_text())]
    assert not offenders, f"README.md src/href must be absolute. Found: {offenders}"


def test_assets_referenced_by_english_readme_are_not_chinese():
    """Only text assets can be inspected; skip binary formats."""
    targets = set(re.findall(r'(?:src="|!\[[^\]]*\]\()(https?://[^)"]+)', _readme_text()))
    checked = 0
    for url in sorted(targets):
        head, _, tail = url.partition("/main/")
        if not tail or not tail.endswith((".svg", ".html", ".md")):
            continue
        local = ROOT / tail
        assert local.exists(), f"README.md points at {tail} which is not in the repo"
        text = local.read_text(encoding="utf-8", errors="replace")
        assert not CJK.search(text), (
            f"{tail} contains CJK text but is embedded in the English README; "
            "use a dedicated -en asset instead"
        )
        checked += 1
    assert checked >= 2, f"expected to inspect several text assets, inspected {checked}"
