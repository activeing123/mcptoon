"""One compression entry point — enforced structurally, not by inspection.

On 2026-10-02 I stated the reachability of `fmt="smart"` twice from reading the code
and was wrong both times (first missed that `auto_smart_enabled()` makes `call`
default to smart, then missed the `elif fmt == "json"` branches). The third answer
came from enumerating all 21 `output.render` call sites with a script. This file is
that script, as a test: the enumeration is the durable form, because reasoning about
reachability is exactly what failed.

The rule it pins:

  A caller may pass `fmt` straight into `output.render` only if a `fmt` guard sits
  between the enclosing `def` and the call. Everything that can receive `"smart"`
  must go through `_render_result` instead, because that is the path that routes
  smart into `compressor.compress_with_ccr` and therefore carries a retrieve handle.

And the second half of the same rule: `output.render` itself must not compress.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mcptoon"
sys.path.insert(0, str(SRC))

from mcptoon import output  # noqa: E402

# A `fmt` guard: a branch on the format variable that keeps `smart` out of the call.
GUARD_RE = re.compile(r"fmt in \(|fmt == \"smart\"|if fmt ==|not in \(")


def _render_sites(path: Path):
    """Yield (lineno, enclosing_def, fmt_arg, guard_lines) for every render( call."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "render(" not in line or line.strip().startswith("#"):
            continue
        if not re.search(r"\brender\(", line):
            continue
        owner, head = "<module>", 0
        for j in range(i - 1, -1, -1):
            m = re.match(r"^def (\w+)", lines[j])
            if m:
                owner, head = m.group(1), j
                break
        m = re.search(r"fmt=([^,)]+)", line)
        fmt_arg = (m.group(1) if m else "-").strip()
        guards = [ln.strip() for ln in lines[head:i] if GUARD_RE.search(ln)]
        yield i + 1, owner, fmt_arg, guards


def test_the_scanner_itself_finds_the_call_sites():
    """A scanner that silently matches nothing would make every test below vacuous."""
    sites = [(p, s) for p in sorted(SRC.rglob("*.py")) for s in _render_sites(p)]
    assert len(sites) >= 15, f"only {len(sites)} render( sites found — scanner is broken"
    assert any(s[2] == "fmt" for _, s in sites), "no fmt=fmt site found"


def test_no_render_call_can_receive_smart_unfiltered():
    """The property: `fmt=fmt` is only allowed behind a `fmt` guard.

    Without a guard, `mcptoon <cmd> --smart` reaches a formatter that cannot hand
    back what it dropped. That was real for `install --list` (32,835 bytes on this
    machine, and it did compress).
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for lineno, owner, fmt_arg, guards in _render_sites(path):
            if fmt_arg == "fmt" and not guards:
                offenders.append(f"{path.name}:{lineno} in {owner}()")
    assert not offenders, (
        "these render() calls can receive 'smart' with no fmt guard — route them "
        "through _render_result so the compressed view carries a handle, or add a "
        "guard that keeps smart out: " + "; ".join(offenders)
    )


def test_the_install_command_goes_through_the_handle_carrying_path():
    """The specific regression, named.

    `_cmd_install` was the only handler with unguarded `fmt=fmt` render calls, so it
    is the one that printed a silently trimmed payload under `--smart`. It must use
    `_render_result` — the same path `mcptoon call` uses.
    """
    text = (SRC / "cli.py").read_text(encoding="utf-8")
    start = text.index("def _cmd_install(")
    end = text.index("\ndef ", start + 1)
    body = text[start:end]
    # Strip comment lines first: the fix's own explanatory comment mentions
    # `output.render(fmt="smart")` in prose, and the first version of this test
    # tripped on that — a check that fires on the explanation rather than the code.
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.strip().startswith("#"))
    assert "_render_result(" in code, "_cmd_install no longer routes through _render_result"
    assert "output.render(" not in code, (
        "_cmd_install calls output.render() directly again — that is the path that "
        "printed a compressed view with no retrieve handle"
    )


def test_output_render_is_not_a_compression_entry_point():
    """It has no `server:tool`, so it cannot key a handle, so it must not compress."""
    rows = [{"path": f"f{i}.py", "line": i, "score": 0.5,
             "snippet": "def f(): pass  # long context " * 8,
             "matched_terms": ["f"], "language": "python", "is_vendor": False,
             "extra": None} for i in range(50)]
    rendered = output.render(rows, fmt="smart")
    assert rendered == json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    assert len(json.loads(rendered)) == len(rows)
    assert "mcptoon_retrieve" not in rendered
    assert "nothing to retrieve" not in rendered


def test_compress_with_ccr_is_the_one_entry_point():
    """And it does carry a handle — otherwise the rule above would be pointless."""
    from mcptoon import compressor

    rows = [{"path": f"f{i}.py", "line": i, "score": 0.5,
             "snippet": "def f(): pass  # long context " * 8,
             "matched_terms": ["f"], "language": "python", "is_vendor": False,
             "extra": None} for i in range(50)]
    text, stats = compressor.compress_with_ccr(rows, server="t", tool="t")
    assert stats["applied"], "payload was not compressed — test is not exercising the path"
    assert text is not None
    assert "mcptoon_retrieve handle=" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
