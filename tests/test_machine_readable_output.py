"""Machine-readable output must be machine-readable.

Two promises are pinned here:

1. **`--json` (and `--toon`) is never char-truncated by default.** A JSON document
   cut at 4,000 characters is not a shorter answer, it is *invalid JSON* — the exact
   opposite of what a machine-readable flag promises. The default cap belongs to the
   formats a human reads in a terminal. An explicit `--max-chars N` still truncates
   anything, because there the user asked.

2. **The global output flags (`--head`, `--max-chars`, `--full`) are not silently
   ignored.** Before this, `install --list --head 1` printed all three servers,
   `skills list --head 2` printed all 421 skills, and `install --list --json` was
   invalid. `head()` only understood lists, so every mapping-shaped payload ignored
   `--head`; and several handlers rendered through `json.dumps` or never received
   the flags at all.

The structural guard is deliberate: reading the code and reasoning about "which
handlers honour the flags" got the equivalent question wrong twice in this repo
(see `test_smart_reachability.py`). So the rule is checked by enumerating the call
sites, not by trusting a memory of them.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcptoon import output  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "src" / "mcptoon" / "cli.py"


# ─── 1. The default cap does not touch machine-readable formats ───────────────

def _big_payload():
    """A payload whose JSON form is comfortably past the 4,000-char default."""
    return [{"id": i, "path": f"src/module_{i}.py", "note": "x" * 60} for i in range(200)]


@pytest.mark.parametrize("fmt", ["json", "toon"])
def test_machine_readable_formats_are_not_char_truncated(fmt):
    payload = _big_payload()
    assert len(json.dumps(payload)) > output._DEFAULT_MAX_CHARS, "test payload is too small"

    out = output.render(payload, fmt=fmt)

    assert len(out) > output._DEFAULT_MAX_CHARS, (
        f"{fmt} was cut at the default cap — a truncated machine-readable document "
        f"is not a shorter answer, it is a broken one"
    )
    assert "use --full" not in out, f"{fmt} carries a human truncation notice"
    assert "[truncated" not in out


def test_json_output_parses_after_the_fix():
    payload = _big_payload()
    parsed = json.loads(output.render(payload, fmt="json"))
    assert parsed == payload, "the JSON that came back is not the payload that went in"


def test_toon_output_round_trips_after_the_fix():
    payload = _big_payload()
    out = output.render(payload, fmt="toon")
    assert output.toon_decode(out) == payload


@pytest.mark.parametrize("fmt", ["mcptoon", "compact", "slim"])
def test_human_readable_formats_are_still_capped(fmt):
    """The cap is not gone — it moved off the machine-readable formats only."""
    payload = _big_payload()
    out = output.render(payload, fmt=fmt)
    if len(out) > output._DEFAULT_MAX_CHARS:
        assert "use --full" in out, f"{fmt} is human-readable and should still cap"


def test_an_explicit_max_chars_still_truncates_json():
    """`--max-chars N` is the user asking; it wins over the machine-readable rule."""
    payload = _big_payload()
    out = output.render(payload, fmt="json", max_chars=500)
    assert len(out) < 600
    assert "use --full" in out


def test_full_is_still_the_documented_escape():
    payload = _big_payload()
    assert output.render(payload, fmt="json", full=True) == output.render(payload, fmt="json")


# ─── 2. `head()` understands a mapping of records, deterministically ─────────

def test_head_caps_a_list():
    assert output.head([1, 2, 3, 4, 5], 2) == [1, 2]


def test_head_caps_a_mapping_of_records():
    records = {"charlie": {"x": 1}, "alpha": {"y": 2}, "bravo": {"z": 3}}
    got = output.head(records, 2)
    assert len(got) == 2


def test_head_picks_mapping_keys_in_sorted_order_not_file_order():
    """Otherwise "the first N servers" means "whichever N were written first",
    and the same command run twice could keep different records."""
    records = {"charlie": {"x": 1}, "alpha": {"y": 2}, "bravo": {"z": 3}}
    assert list(output.head(records, 2)) == ["alpha", "bravo"]


def test_head_leaves_a_mapping_of_lists_alone_in_shape():
    """`manifest`'s tools-per-server payload keeps its older behaviour."""
    got = output.head({"items": [1, 2, 3, 4], "n": 9}, 2)
    assert got == {"items": [1, 2], "n": 9}


def test_head_is_a_noop_when_there_is_nothing_to_cap():
    assert output.head([1, 2], 5) == [1, 2]
    assert output.head({"a": {"x": 1}}, 5) == {"a": {"x": 1}}


# ─── 3. End to end: the CLI's JSON is valid, and the flags do something ──────

# In-process, with the data monkeypatched, rather than a subprocess: a subprocess
# inherits `conftest.py`'s isolated HOME and finds no servers and no skill index, so
# `install --list` printed `{}` and `skills list` exited with empty stdout — the
# tests passed for the wrong reason (nothing to measure). Injecting the payload
# makes them deterministic and actually exercise the render path.

_BIG_SERVERS = {
    f"server-{i:02d}": {"command": "npx", "args": ["-y", f"pkg-{i}"], "env": {"K": "V"}}
    for i in range(6)
}
_BIG_SKILLS = {"skills": [{"slug": f"skill-{i:03d}", "desc": f"fixture skill {i}"}
                          for i in range(200)]}


def test_install_json_output_is_valid_json(monkeypatch, capsys):
    from mcptoon import cli, installer

    monkeypatch.setattr(installer, "list_installed", lambda: _BIG_SERVERS)
    cli._cmd_install(["--list"], "json", head_n=0, max_chars=0, full=False)
    out = capsys.readouterr().out
    assert json.loads(out) == _BIG_SERVERS, "install --list --json is not valid JSON"


def test_install_head_flag_shrinks_the_json_payload(monkeypatch, capsys):
    from mcptoon import cli, installer

    monkeypatch.setattr(installer, "list_installed", lambda: _BIG_SERVERS)
    cli._cmd_install(["--list"], "json", head_n=0, max_chars=0, full=False)
    full = capsys.readouterr().out
    cli._cmd_install(["--list"], "json", head_n=1, max_chars=0, full=False)
    small = capsys.readouterr().out
    assert small != full, "`install --list --head 1` changed nothing"
    assert len(json.loads(small)) == 1


def test_install_max_chars_flag_shrinks_the_json_payload(monkeypatch, capsys):
    from mcptoon import cli, installer

    monkeypatch.setattr(installer, "list_installed", lambda: _BIG_SERVERS)
    cli._cmd_install(["--list"], "json", head_n=0, max_chars=0, full=False)
    full = capsys.readouterr().out
    cli._cmd_install(["--list"], "json", head_n=0, max_chars=300, full=False)
    small = capsys.readouterr().out
    assert small != full, "`install --list --max-chars 300` changed nothing"
    assert len(small) < len(full)


def test_skills_json_output_is_valid_json(monkeypatch, capsys):
    from mcptoon import skills

    monkeypatch.setattr(skills, "load_index", lambda: _BIG_SKILLS)
    skills._cmd_skills(["list"], "json", 0, 0, False)
    out = capsys.readouterr().out
    assert len(json.loads(out)) == len(_BIG_SKILLS["skills"])


def test_skills_head_flag_shrinks_the_json_payload(monkeypatch, capsys):
    from mcptoon import skills

    monkeypatch.setattr(skills, "load_index", lambda: _BIG_SKILLS)
    skills._cmd_skills(["list"], "json", 0, 0, False)
    full = capsys.readouterr().out
    skills._cmd_skills(["list"], "json", 2, 0, False)
    small = capsys.readouterr().out
    assert small != full, "`skills list --head 2` changed nothing"
    assert len(json.loads(small)) == 2


def test_skills_max_chars_flag_shrinks_the_json_payload(monkeypatch, capsys):
    from mcptoon import skills

    monkeypatch.setattr(skills, "load_index", lambda: _BIG_SKILLS)
    skills._cmd_skills(["list"], "json", 0, 0, False)
    full = capsys.readouterr().out
    skills._cmd_skills(["list"], "json", 0, 300, False)
    small = capsys.readouterr().out
    assert small != full, "`skills list --max-chars 300` changed nothing"
    assert len(small) < len(full)


# ─── 4. Structural guard: no render site drops a global flag ─────────────────

# Handlers whose render payload is a single object, not a record collection, so
# `--head` has no defined target. Each needs a reason; "it was easier" is not one.
HEAD_EXEMPT = {
    "_cmd_retrieve": "returns one stored original, not a collection",
    "_cmd_footer_facts": "returns one facts mapping, not a collection",
    "_cmd_inspect": "returns one tool's schema, not a collection",
}

FLAGS = ("head_n", "max_chars", "full")


def _render_sites():
    """Every `output.render(` call in cli.py: line, enclosing def, call text.

    Comment lines are skipped: the fix's own explanatory comment quotes
    `output.render(fmt="smart")`, and a scanner that counts prose as a call site
    reports a defect that is not there (the same self-match that tripped
    `test_smart_reachability.py`).
    """
    lines = CLI.read_text(encoding="utf-8").splitlines()
    owner, owners = None, []
    for ln in lines:
        m = re.match(r"\s*def (\w+)", ln)
        if m:
            owner = m.group(1)
        owners.append(owner)

    sites = []
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("#"):
            continue
        if "output.render(" not in ln:
            continue
        chunk, j = ln, i
        while chunk.count("(") > chunk.count(")") and j < len(lines):
            chunk += " " + lines[j].strip()
            j += 1
        sites.append((i, owners[i - 1], chunk))
    return sites


def test_the_scanner_finds_the_render_sites():
    sites = _render_sites()
    assert len(sites) >= 15, f"only found {len(sites)} render sites — scanner is stale"


def test_every_render_site_forwards_the_global_output_flags():
    problems = []
    for lineno, handler, chunk in _render_sites():
        if handler in HEAD_EXEMPT:
            continue
        missing = [f for f in FLAGS if f not in chunk]
        if missing:
            problems.append(f"cli.py:{lineno} in {handler} does not pass {', '.join(missing)}")
    assert not problems, (
        "these render sites silently drop a documented global output flag:\n  "
        + "\n  ".join(problems)
    )


def test_the_head_exemptions_are_all_still_real():
    """An exemption for a handler that no longer renders is a stale claim."""
    handlers = {h for _, h, _ in _render_sites()}
    stale = [h for h in HEAD_EXEMPT if h not in handlers]
    assert not stale, f"HEAD_EXEMPT names handlers that no longer render: {stale}"


def test_the_record_rendering_handlers_accept_the_flags():
    """A handler that renders records must be *able* to receive the flags."""
    from mcptoon import cli

    for name in ("_cmd_install", "_cmd_health_check", "_cmd_usage", "_cmd_stats",
                 "_cmd_auto_discover", "_cmd_import", "_cmd_config", "_cmd_inspect"):
        params = inspect.signature(getattr(cli, name)).parameters
        assert "head_n" in params, f"{name} cannot receive --head"
        assert "max_chars" in params, f"{name} cannot receive --max-chars"
        assert "full" in params, f"{name} cannot receive --full"


def test_skills_list_accepts_the_flags():
    from mcptoon import skills

    params = inspect.signature(skills._cmd_skills).parameters
    for flag in ("head_n", "max_chars", "full"):
        assert flag in params, f"skills._cmd_skills cannot receive --{flag.replace('_', '-')}"


def test_record_payloads_are_not_dumped_raw():
    """`json.dumps` bypasses `render`, so a global flag cannot reach it.

    The three record payloads that used to be dumped raw — `config`'s values,
    `stats`' dashboard and `report`'s data — must go through `render` now.
    """
    text = CLI.read_text(encoding="utf-8")
    for needle in ("json.dumps(values", "json.dumps(data", "json.dumps(servers",
                   "json.dumps(f,", "json.dumps(f)"):
        assert needle not in text, f"a record payload is still dumped raw: {needle}"

    report_src = (CLI.parent / "report.py").read_text(encoding="utf-8")
    assert "json.dumps(data" not in report_src, "report's payload is still dumped raw"
