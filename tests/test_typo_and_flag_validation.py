# Copyright 2025-2026 activeing123
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

"""Mistyped commands and non-integer flags must fail loudly.

Reported 2026-10-18:
- `mcptoon listt` matched "list" inside the word and ran `manifest`;
  `mcptoon healthh` matched "health" and ran the health check — both exit 0.
- `--head abc` / `--head=xyz` was swallowed silently (head_n stayed 0 =
  unlimited), so a scripted `--head $N` with a bad value looked like it worked.
"""
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from mcptoon import cli
from mcptoon import manifest as manifest_mod


def _run(argv, search=None):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    patches = [patch.object(cli.sys, "argv", ["mcptoon", *argv])]
    if search is not None:
        patches.append(patch.object(manifest_mod, "search_tools", return_value=search))
    for p in patches:
        p.start()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                cli.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
    finally:
        for p in patches:
            p.stop()
    return out.getvalue(), err.getvalue(), code


# ── mistyped commands ────────────────────────────────────────────────────────

def test_listt_is_unknown_not_manifest():
    out, err, code = _run(["listt"])
    assert code == 1
    assert "unknown command 'listt'" in err
    assert "did you mean" in err
    assert "list" in err
    # Must NOT have run manifest/list (no server listing on stdout).
    assert "[stdio]" not in out and "[http]" not in out


def test_healthh_is_unknown_not_health_check():
    out, err, code = _run(["healthh"])
    assert code == 1
    assert "unknown command 'healthh'" in err
    assert "Health check" not in out


def test_real_command_still_works():
    # A real command with no args must still run (list has no sub-args).
    out, err, code = _run(["list"])
    assert "Configured servers" in out or "No servers configured" in out


def test_genuine_single_token_phrase_still_routes():
    # A lone phrase that is NOT close to a command still reaches keyword routing.
    out, err, code = _run(["有什么工具"])
    # It routes to manifest/list; the point is it is NOT rejected as unknown.
    assert "unknown command" not in err


# ── a flag in the command position ───────────────────────────────────────────

def test_flag_in_command_position_is_a_usage_error_not_another_command():
    # `--verbose`/`--sort`/`--top` are known to the global pre-pass but owned by
    # the command that defines them, so the pre-pass appends them and the first
    # one used to become `command`. The unknown-command path then keyword-matched
    # the whole line against a list containing bare command names, so
    # `mcptoon --verbose list` ran `manifest` and exited 0 (found 2026-11-12).
    out, err, code = _run(["--verbose", "list"])
    assert code == 2, f"expected a usage error, got exit {code}"
    assert "'--verbose' is an option, not a command" in err
    assert "No tools found" not in out, "it must not have run manifest"
    assert "No servers configured" not in out, "it must not have run list either"


def test_flag_with_a_value_in_command_position_errors_too():
    out, err, code = _run(["--sort", "alpha", "list"])
    assert code == 2
    assert "'--sort' is an option, not a command" in err
    assert "No tools found" not in out


def test_help_in_command_position_still_prints_help():
    # The exemption matters: `mcptoon --help` is the documented front door.
    out, err, code = _run(["--help"])
    assert code == 0
    assert "is an option, not a command" not in err
    assert out.strip(), "--help must still print the help page"


def test_typo_before_a_keyword_word_is_still_unknown():
    # Two tokens used to be enough to look like a phrase, so `mcptoon lst list`
    # keyword-matched "list" and ran `manifest` — exit 0 on a typo.
    out, err, code = _run(["lst", "list"])
    assert code == 1, f"a typo must not exit 0, got {code}"
    assert "unknown command 'lst'" in err
    assert "No tools found" not in out, "it must not have run manifest"


def test_a_keyword_after_a_garbage_word_does_not_route():
    # The keyword match used to run over the whole line, so any unknown first word
    # followed by a keyword routed and exited 0. `mcptoon whatever health` ran the
    # health check and reported success — the same defect class as `lst list`, one
    # token further out (found 2026-11-13 closing #41). Only the first token decides.
    for argv, forbidden in (
        (["whatever", "health"], "Health check"),
        (["foo", "bar", "health"], "Health check"),
        (["xyz", "check"], "Health check"),
        (["garbage", "tools"], "No tools found"),
        (["asdf", "search"], "routed"),
    ):
        out, err, code = _run(argv)
        assert code == 1, f"{argv} must exit 1, got {code}"
        assert f"unknown command '{argv[0]}'" in err
        assert forbidden not in out, f"{argv} must not have routed ({forbidden!r})"


def test_the_cjk_phrase_that_motivated_routing_still_works():
    # The reason the router exists: a Chinese-speaking user typing the question in
    # their own words. CJK does not space its words, so the first token carries the
    # whole phrase and the first-token rule keeps it.
    out, err, code = _run(["有什么工具"])
    assert code == 0, f"a genuine phrase must still route, got exit {code}: {err}"
    assert "unknown command" not in err


def test_a_spaced_cjk_phrase_still_routes():
    # A CJK user who *does* space their words gets the whole-line match, because
    # the first token is non-ASCII. Without that exemption `列出 服务器` would be
    # an error even though every word is part of the question.
    out, err, code = _run(["列出", "服务器"])
    assert code == 0, f"a spaced CJK phrase must still route, got exit {code}: {err}"
    assert "unknown command" not in err


# ── non-integer flags ────────────────────────────────────────────────────────

def test_head_non_integer_errors():
    out, err, code = _run(["search", "file", "--head", "abc"], search=[{"server": "s", "name": "t", "description": "d", "params": "", "score": 1.0}])
    assert code == 1
    assert "--head needs an integer" in err


def test_head_equals_non_integer_errors():
    out, err, code = _run(["search", "file", "--head=xyz"], search=[])
    assert code == 1
    assert "--head needs an integer" in err


def test_max_chars_non_integer_errors():
    out, err, code = _run(["search", "file", "--max-chars", "nope"], search=[])
    assert code == 1
    assert "--max-chars needs an integer" in err


def test_head_valid_integer_still_works():
    rows = [{"server": "s", "name": f"t{i}", "description": "d", "params": "", "score": 1.0}
            for i in range(5)]
    out, err, code = _run(["search", "file", "--head", "2", "--json"], search=rows)
    assert code == 0
    assert len(json.loads(out)) == 2


def test_select_top_non_integer_errors():
    out, err, code = _run(["select", "file", "--top", "abc"])
    assert code == 1
    assert "--top needs an integer" in err


# ── a declared-but-unimplemented output flag ─────────────────────────────────

def test_the_unimplemented_yaml_flag_is_rejected_instead_of_ignored():
    """`--yaml` was registered for a YAML renderer that never existed (#49/#50).

    It was a known flag, so the pre-pass handed it to the command, which ignored
    it: `mcptoon list --yaml` printed human text and exited 0 while `list --json`
    printed data. Unregistered, it now fails loudly in either position.
    """
    for argv in (["list", "--yaml"], ["--yaml", "list"]):
        out, err, code = _run(argv)
        assert code == 2, f"{argv} must be a usage error, got {code}"
        assert "--yaml" in err, f"{argv} must name the offending flag"
        assert "No servers configured" not in out, f"{argv} must not have run the command"


def test_yaml_is_not_in_the_known_flag_registry():
    assert "--yaml" not in cli.KNOWN_FLAGS


# ── per-command flag ownership (issue #41) ───────────────────────────────────

def test_a_flag_the_command_does_not_own_is_a_usage_error():
    """`mcptoon list --verbose` printed the human server list and exited 0.

    The flag is real — it is `manifest`'s — so the pre-pass tolerated it and `list`
    dropped it, which made a correctly spelled wrong flag *quieter* than the typo
    `list --verbos` (exit 2). Commands with an explicit enumeration now reject what
    they do not own (found 2026-11-12 auditing #41).
    """
    out, err, code = _run(["list", "--verbose"])
    assert code == 2, f"a wrong flag must not exit 0, got {code}"
    assert "'--verbose' is not an option of 'list'" in err
    assert "'--verbose' is an option of: manifest" in err, "it should name the owner"
    assert out == "", "nothing may reach stdout"


def test_every_migrated_command_rejects_a_flag_it_does_not_own():
    for command, flag in (("inspect", "--verbose"), ("search", "--langs"),
                          ("manifest", "--langs")):
        out, err, code = _run([command, flag])
        assert code == 2, f"{command} {flag} must exit 2, got {code}"
        assert f"is not an option of '{command}'" in err


def test_the_owned_flags_still_work():
    out, err, code = _run(["manifest", "--sort", "alpha"])
    assert code == 0, err
    assert "is not an option of" not in err


def test_shared_output_flags_are_unaffected_by_the_ownership_check():
    out, err, code = _run(["list", "--json"])
    assert code == 0, err
    assert json.loads(out) == []


def test_commands_outside_the_registry_answer_for_themselves():
    """The opaque-tail commands stay out of `COMMAND_FLAGS` on purpose, so the
    ownership check must not claim them: `config`'s own action error answers first.

    Until the fifth batch (2026-11-13) this test used `usage`, which was simply not
    migrated yet. Every command that *can* be enumerated now is, so the leniency it
    asserted no longer exists anywhere — what remains is the deliberate exception, and
    that is what this pins. `config` takes `config set <key> <value>`, and a value may
    start with `--`, so enumerating its flags would reject working invocations.
    """
    out, err, code = _run(["config", "--roots"])
    assert "is not an option of" not in err, "config must not be in COMMAND_FLAGS"
    assert "Unknown config action" in err
    assert code == 1, "the command's own error, not our exit 2"


def test_an_alias_is_not_a_hole_in_the_ownership_check():
    """`servers` is `list`, so it must give `list`'s answer.

    Measured 2026-11-13 on 0.8.39: `mcptoon list --verbose` exited 2 while
    `mcptoon servers --verbose` — the same command — printed the server list and
    exited **0**, dropping the flag. `COMMAND_FLAGS` is keyed by canonical name and
    the check looked up the raw token, so every alias was unmigrated by accident.
    """
    out, err, code = _run(["list", "--verbose"])
    assert code == 2
    out, err, code = _run(["servers", "--verbose"])
    assert code == 2, f"the alias must reject too, got {code}: {err}"
    assert "'--verbose' is not an option of 'servers'" in err
    # ...and the did-you-mean hint is derived from the canonical set, not an empty one:
    # `tools` is `manifest`, so a near-miss of manifest's `--top` is suggested.
    out, err, code = _run(["tools", "--tool"])
    assert code == 2
    assert "did you mean: --top" in err, err


def test_every_alias_resolves_to_a_registered_command():
    """Guard the alias table: a typo in it would silently reopen the hole."""
    for alias, canonical in cli.COMMAND_ALIASES.items():
        assert canonical in cli.COMMAND_FLAGS, (
            f"alias {alias!r} points at {canonical!r}, which is not in COMMAND_FLAGS"
        )
        assert alias not in cli.COMMAND_FLAGS, (
            f"{alias!r} is registered on its own — the alias would shadow it"
        )


def test_strict_flags_zero_downgrades_the_ownership_error():
    with patch.dict(os.environ, {"MCPTOON_STRICT_FLAGS": "0"}):
        out, err, code = _run(["list", "--verbose"])
    assert code == 0
    assert "ignored: MCPTOON_STRICT_FLAGS=0" in err


# ── `--format` belongs to manifest (issue #50) ───────────────────────────────

def test_format_on_a_command_without_an_export_is_a_usage_error():
    """`list --format json` printed the human list and exited 0.

    Measured 2026-11-12 on 0.8.38: `list --format json`, `--format toon` and
    `--format bogus` produced the *same* 940-character human list, because `fmt` is
    set by `--json`/`--toon`/... and never by `--format`. The flag is manifest's
    export selector, so every other command must say so instead of dropping it.
    """
    out, err, code = _run(["list", "--format", "json"])
    assert code == 2, f"a no-op flag must not exit 0, got {code}"
    assert "'--format' is not an option of 'list'" in err
    assert "manifest" in err
    assert "--json" in err, "it should point at the flags that do set the format"
    assert "Configured servers" not in out and "No tools found" not in out, \
        "the command must not run"


def test_format_is_still_accepted_by_manifest_and_its_alias():
    """This home has no servers, so `manifest` returns "No tools found" before it can
    export anything — the claim here is only that the flag is *accepted*, in both
    spellings of the command and in both positions. That the export itself works was
    measured on the published 0.8.38 with a real config (`manifest --format openai`
    -> 1,067,298 bytes, exit 0)."""
    for argv in (["manifest", "--format", "json"], ["tools", "--format", "json"],
                 ["--format", "json", "manifest"]):
        out, err, code = _run(argv)
        assert code == 0, f"{argv}: exit {code} / {err}"
        assert "is not an option of" not in err


def test_an_unknown_export_format_is_rejected_even_with_nothing_to_export():
    """`export_manifest` falls back to JSON for an unknown name (a library contract
    pinned by test_v02_features), so the CLI has to reject the typo itself — and it
    has to do so before the empty-manifest early return, not inside the handler."""
    out, err, code = _run(["manifest", "--format", "bogus"])
    assert code == 1, f"expected a bad-value error, got {code}"
    assert "needs one of" in err and "bogus" in err
    assert "No tools found" not in out, "a rejected value must not run the command"


# ── the second batch of owned flag sets (issue #41) ──────────────────────────

def test_the_second_batch_owns_what_its_own_source_parses():
    """`call`/`install`/`activity`/`sync` spell their flags out in cli.py; `skills`
    and `serve` parse theirs in their own module (`skills.py`, `serve.py`) — those
    sets were read from there, not guessed from the docs."""
    assert cli._unowned_command_flags("call", ["--auto", "--destructive"]) == []
    assert cli._unowned_command_flags("install", ["--pack", "--packs", "--url"]) == []
    assert cli._unowned_command_flags("skills", ["--tombstone", "--version-gate"]) == []
    assert cli._unowned_command_flags("serve", ["--background", "--listen"]) == []
    assert cli._unowned_command_flags("retrieve", ["--list"]) == []
    assert cli._unowned_command_flags("discover", ["--health", "--write"]) == []
    assert cli._unowned_command_flags("statusline", ["--install", "--guide"]) == []
    assert cli._unowned_command_flags("docs", ["--k", "--query"]) == []
    # Action-first commands: the flag follows the subcommand.
    assert cli._unowned_command_flags("plugin", ["--force", "--no-sync"]) == []
    assert cli._unowned_command_flags("kb", ["--ttl", "--source"]) == []
    # `--purge` goes through the helper on purpose: `_run(["session", "--purge"])`
    # deletes the caller's session logs, which is not a thing a test may do.
    assert cli._unowned_command_flags("session", ["--purge"]) == []
    for pillar in ("resources", "prompts", "complete"):
        assert cli._unowned_command_flags(pillar, ["--search"]) == []


def test_the_second_batch_rejects_a_flag_from_another_command():
    """Every flag below is a real, known flag — just not this command's. Before the
    registry existed each of these ran the command and exited 0."""
    for command, flag in (("call", "--verbose"), ("install", "--destructive"),
                          ("skills", "--sort"), ("sync", "--top"),
                          ("activity", "--envelope"), ("retrieve", "--sort"),
                          ("serve", "--sort"), ("discover", "--sort"),
                          ("statusline", "--sort"), ("docs", "--sort"),
                          ("plugin", "--destructive"), ("kb", "--envelope"),
                          ("session", "--sort"), ("resources", "--sort"),
                          ("prompts", "--sort"), ("complete", "--sort")):
        out, err, code = _run([command, flag])
        assert code == 2, f"{command} {flag} must exit 2, got {code}: {err}"
        assert f"is not an option of '{command}'" in err


def test_help_still_works_for_a_command_with_its_own_page():
    """`serve` is in `_COMMANDS_WITH_OWN_HELP`, so its `--help` is *not* consumed by
    the pre-pass and does reach the ownership check — asking for help must never be a
    usage error."""
    out, err, code = _run(["serve", "--help"])
    assert code == 0, err
    assert "is not an option of" not in err


def test_the_ownership_hint_is_a_name_not_a_python_list():
    """`_closest` returns a list; interpolating it whole printed
    `did you mean '['--envelope']'?` (found 2026-11-12 in the live check)."""
    for command, flag in (("call", "--verbose"), ("serve", "--sort"),
                          ("skills", "--sort")):
        out, err, code = _run([command, flag])
        assert code == 2, f"{command} {flag}: exit {code}"
        assert "['" not in err, f"{command}: the hint leaked a list repr: {err}"
        assert "did you mean: --" in err, f"{command}: expected a joined hint in {err}"
