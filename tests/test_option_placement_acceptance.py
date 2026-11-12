"""Issue #41 — the proposal's acceptance criteria, pinned as behaviour tests.

#41 proposes a per-command option parser. Whatever the internal shape ends up
being, these are the externally visible promises that must survive the refactor,
so they are pinned here rather than left as prose in the issue:

1. option placement is order-insensitive within one command's scope -> TestOptionOrder
2. `--help` is side-effect free                                    -> test_help_is_side_effect_free
3. unknown-option behaviour stays compatible (exit 2 + did-you-mean) -> TestUnknownOption
4. pass-through / opaque-tail commands keep their tail verbatim     -> TestOpaqueTail
   (criterion 5, "completion and help surfaces agree with dispatch", is covered by
   `test_cli_flags.py` / `test_doctor_arg_dispatch.py`)

Measured 2026-11-12 on main: the order matrix below finds **no** defect — every
command checked is already order-insensitive. The two defects the audit *did*
find (a flag in the command position became the command; a typo followed by a
keyword word was phrase-routed into another command) are pinned in
`test_typo_and_flag_validation.py`.

Two harness details worth keeping:

* stdout is compared, stderr is not: stdout is the command's answer, while
  stderr carries the presence line, whose call count changes between two runs
  inside one process.
* the one-time welcome card must be consumed before the matrix runs, or it
  appears in whichever ordering happens to go first and looks exactly like an
  order-sensitivity defect. That false positive is why the warm-up fixture
  exists.
"""
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from mcptoon import cli


def _run(argv):
    """Drive cli.main() end-to-end; return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with patch.object(sys, "argv", ["mcptoon", *argv]):
        try:
            with redirect_stdout(out), redirect_stderr(err):
                cli.main()
        except SystemExit as e:
            code = e.code if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module", autouse=True)
def _consume_first_run_card():
    """Run one real command first, so the one-time welcome card is already spent.

    The card is printed by the first real command on a machine. Without this,
    the first ordering in the matrix prints it and the second does not — a
    difference in stdout that has nothing to do with option placement.
    """
    _run(["manifest"])


# ── criterion 1: placement is order-insensitive ──────────────────────────────

# (label, positionals, options) — each option is exercised before *and* after
# the positionals. Read-only commands on an empty config, so the output is
# deterministic and nothing is written.
ORDER_CASES = [
    ("search", ["search", "foo"], ["--json", "--head 1", "--max-chars 20", "--full"]),
    ("inspect", ["inspect", "srv", "tool"], ["--json", "--head 1", "--max-chars 20", "--full"]),
    ("usage", ["usage"], ["--json", "--head 1"]),
    ("usage <server>", ["usage", "srv"], ["--json"]),
    ("stats", ["stats"], ["--json"]),
    ("activity", ["activity"], ["--json"]),
    ("status", ["status"], ["--json"]),
    ("savings", ["savings"], ["--json"]),
    ("report", ["report"], ["--json"]),
    ("manifest", ["manifest"], ["--json", "--sort alpha", "--top 1", "--verbose", "--full"]),
    ("list", ["list"], ["--json", "--head 1"]),
    ("skills list", ["skills", "list"], ["--json"]),
    ("skills resolve", ["skills", "resolve", "x"], ["--json"]),
    ("docs resolve", ["docs", "resolve", "x"], ["--json"]),
]


@pytest.mark.parametrize(
    "label,positionals,options", ORDER_CASES, ids=[c[0] for c in ORDER_CASES])
def test_option_placement_does_not_change_the_outcome(label, positionals, options):
    command, *rest = positionals
    for option in options:
        flags = option.split(" ")
        before = _run([command, *flags, *rest])
        after = _run([command, *rest, *flags])
        # Anti-vacuity: identical answers would also "pass" if the option were
        # rejected in both positions, so require that it was understood at all.
        assert "unknown option" not in before[2] + after[2], (
            f"`{label} {option}` is not accepted in one of the positions: "
            f"{(before[2] + after[2]).strip()[:150]!r}")
        assert (before[0], before[1]) == (after[0], after[1]), (
            f"`{label}` changed when {flags} moved: "
            f"exit {before[0]} vs {after[0]}, "
            f"stdout {before[1].strip()[:90]!r} vs {after[1].strip()[:90]!r}")


def test_a_flag_before_the_command_still_means_the_same_thing():
    """`--json list` and `list --json` are the same request.

    Only the pre-pass *owns* the shared output flags, so they are consumed
    wherever they appear; the command-scoped ones may not appear before the
    command at all (see test_typo_and_flag_validation.py)."""
    before = _run(["--json", "list"])
    after = _run(["list", "--json"])
    assert (before[0], before[1]) == (after[0], after[1])


# ── criterion 2: --help does not touch the machine ───────────────────────────

def _tree(root: Path):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("command", ["list", "search", "inspect", "call", "manifest",
                                     "doctor", "stats", "openapi", "skills"])
def test_help_is_side_effect_free(command):
    """`<command> --help` prints help, exits 0, and writes nothing.

    This is the criterion that used to fail in the other direction:
    `mcptoon quickstart --help` discovered servers and wrote them into config,
    and `mcptoon serve --help` opened a stdio bridge and hung.
    """
    root = Path(os.environ["MCPTOON_HOME"])
    before = _tree(root)
    code, out, err = _run([command, "--help"])
    assert code == 0, f"{command} --help exited {code}: {err.strip()[:200]}"
    assert out.strip(), f"{command} --help printed nothing"
    assert _tree(root) == before, f"{command} --help wrote under {root}"


# ── criterion 3: unknown options stay compatible ─────────────────────────────

@pytest.mark.parametrize("argv", [
    ["list", "--nope"],
    ["manifest", "--nope"],
    ["search", "foo", "--nope"],
    ["inspect", "a", "b", "--nope"],
    ["doctor", "--nope"],
    ["stats", "--nope"],
    ["usage", "--nope"],
    ["skills", "list", "--nope"],
])
def test_unknown_option_exits_two_with_a_did_you_mean(argv):
    code, out, err = _run(argv)
    assert code == 2, f"{argv} exited {code}"
    assert "unknown option '--nope'" in err
    assert "did you mean" in err, f"no suggestion for {argv}: {err.strip()[:200]}"
    assert "--nope" not in out


# ── criterion 4: opaque tails are handed over verbatim ───────────────────────

@pytest.mark.parametrize("command,module_name", [
    ("openapi", "openapi"), ("graphql", "graphql"), ("auth", "oauth"), ("bake", "bake")])
def test_opaque_tail_reaches_the_module_untouched(command, module_name, monkeypatch):
    """The pre-pass stops at these commands, so the module owns every later flag.

    `mcptoon openapi call <spec> <cmd> --upstream-flag` must not have
    `--upstream-flag` reinterpreted (or `--json`/`--head 5`, which mcptoon knows
    but the module may want for itself).
    """
    module = __import__(f"mcptoon.{module_name}", fromlist=["run"])
    seen = {}
    monkeypatch.setattr(module, "run", lambda rest, *a, **k: seen.update(rest=rest, fmt=a[0]))

    tail = ["call", "spec.json", "cmd", "--json", "--head", "5", "--upstream"]
    code, out, err = _run([command, *tail])
    assert code == 0, err.strip()[:200]
    assert seen["rest"] == tail, f"{command} received {seen['rest']!r}"
    assert seen["fmt"] == "auto", "no flag was consumed as mcptoon's own output format"


@pytest.mark.parametrize("command,module_name", [
    ("openapi", "openapi"), ("graphql", "graphql"), ("auth", "oauth"), ("bake", "bake")])
def test_a_flag_before_an_opaque_command_is_still_mcptoons_own(command, module_name, monkeypatch):
    """The documented split: before the command the flag is mcptoon's, after it
    the module's. Pinned so the boundary cannot drift unnoticed."""
    module = __import__(f"mcptoon.{module_name}", fromlist=["run"])
    seen = {}
    monkeypatch.setattr(module, "run", lambda rest, *a, **k: seen.update(rest=rest, fmt=a[0]))

    code, out, err = _run(["--json", command, "call", "spec.json", "cmd"])
    assert code == 0, err.strip()[:200]
    assert seen["rest"] == ["call", "spec.json", "cmd"]
    assert seen["fmt"] == "json", "mcptoon's own --json must be consumed before the command"
