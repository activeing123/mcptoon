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

"""
mcptoon cli — Command-line entry point

The user-facing command list lives in exactly one place: `_print_help()` below.
Do not restate it here. This module used to carry a second copy of the whole help
text, and by the time anyone looked it had drifted: it still advertised
`mcptoon uninstall` in its Usage block, listed `policy` twice, and never mentioned
`config`, `stats` or `toggle` — the three commands that exist to let a user turn
the per-turn savings line off. Two copies of a front door is one copy too many,
and the stale one is the one people end up reading.
"""

import json
import sys
import os
import re
import time
import difflib
import inspect
import textwrap
from pathlib import Path

from . import config as cfg
from . import manifest as manifest_mod
from . import output
from . import usage as usage_mod
from .router import call_tool
from .errors import is_error


# Every long option this CLI implements, global or per-subcommand — including the
# ones parsed inside demo.py / serve.py, which the central parser passes through
# untouched. tests/test_cli_flags.py scans the whole package for flag literals, so
# the list cannot drift from reality in either direction: forget one and a real
# flag gets warned as unknown; add a phantom and the dead-entry test fails.
KNOWN_FLAGS = frozenset(
    {
        "--agent", "--archive", "--auth", "--auto", "--all", "--check", "--compact", "--copy",
        "--derived", "--destructive", "--dir", "--dry",
        "--dry-run", "--endpoint", "--envelope", "--fallback-json", "--file", "--force", "--format",
        "--from",
        "--full", "--head", "--desc",
        "--header", "--health", "--help", "--http", "--input-responses", "--interval",
        "--json", "--keep", "--k", "--limit", "--list", "--listen", "--max-chars", "--mcptoon",
        "--no-keep-config", "--keep-history", "--guide",
        "--model",
        "--no-configs",
        "--no-env", "--no-local", "--no-network", "--no-self", "--no-sync", "--npm", "--pip",
        "--quiet", "--quick", "--query", "--raw", "--remove", "--request-state", "--roots", "--search",
        "--summary", "--clear", "--host", "--export", "--follow", "--since",
        "--failures", "--before", "--tool", "--search",
        "--self", "--pack", "--packs",
        "--slim", "--smart",
        "--stdin", "--stdio", "--takeover", "--timeout", "--tombstone", "--toon", "--tools-k", "--top",
        "--sort", "--verbose", "--base-url", "--cache-key", "--cache-ttl", "--register", "--client-name", "--bin", "--openapi", "--graphql", "--mcp", "--transport", "--complete",
        "--url", "--usage",
        "--version", "--version-gate", "--view", "--watch",
        "--allow-tracked-deletes",
        "--watch-mode", "--write", "--yes", "--engine",
        # `completion`-only flags. They are registered here for the same reason
        # `--npm`/`--pip`/`--url` are: the central parser must not reject them as
        # unknown; `_cmd_completion` consumes them out of `rest`.
        "--install", "--uninstall",
        # `openapi`-only. `mcptoon openapi ...` hands its tail to the adapter
        # verbatim, but the flag must still be known so a caller that puts it
        # before the verb is not rejected as a typo. `--no-check` opts out of
        # the response scan; `--pretty` is accepted as a no-op alias for --json.
        "--auth", "--auth-header", "--no-check", "--pretty", "--refresh",
        # `graphql`-only. `--fields` is the selection set; `--schema` reads a
        # saved introspection file. Registered for the same pass-through reason.
        "--fields", "--schema",
        # `auth`-only (OAuth login/creds). Registered so the central parser does
        # not reject them before the `auth` module sees them.
        "--auth-url", "--token-url", "--client-id", "--client-secret",
        "--scope", "--port", "--redirect-port", "--device", "--name",
        # `exec`-only. `--langs` lists the runtimes this machine can actually
        # run; `--code` is the inline-source form (`--file` and `--timeout`
        # already existed for other commands and are reused verbatim).
        # Registered here for the same reason `--npm` is: the central parser
        # must pass them through, and `_cmd_exec` consumes them out of `rest`.
        "--langs", "--code",
        # `kb`-only. `--ttl` and `--source` name cache lifetime and an index
        # label; `--purge` is `session`'s destructive reset.
        "--ttl", "--source", "--purge",
        # `serve --background` control surface. Registered so the central parser
        # passes them through to run_serve; `--daemon`/`--start` are accepted
        # aliases for `--background`. `--upgrade` is the upgrade command's alias
        # of `--check`+`--yes` intent handled in upgrade.run.
        "--background", "--status", "--stop", "--daemon", "--start", "--upgrade",
        "--install-autostart", "--uninstall-autostart",
        # `--user`/`--now` appear verbatim in the `serve --install-autostart`
        # help text (the systemctl hint). They are systemctl flags, not ours, but
        # the package-wide literal scan sees them; register so the typo-guard is
        # not tripped by our own documentation.
        "--user", "--now",
    }
)


# A routed call slower than this is flagged in `mcptoon activity`. 3000 ms is a
# deliberately high bar: normal MCP calls are tens to hundreds of ms, so crossing
# it means the user was actually kept waiting, not that the machine blinked.
_SLOW_CALL_MS = 3000


def _human_bytes(n: int) -> str:
    """A short human file size (e.g. '12.4 KB'). Plain, no locale, no deps."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


# Subcommands that print their own help text and therefore handle -h/--help
# themselves; every other command falls back to the general help. Adding a command
# here without a help handler in its own module silently loses that help — see
# tests/test_serve.py and tests/test_serve_perf.py, which pin serve's, and
# tests/test_help_shortcircuit.py, which pins this set's purpose.
_COMMANDS_WITH_OWN_HELP = frozenset({"demo", "demo-server", "serve", "openapi", "graphql", "auth", "resources", "prompts", "complete", "bake"})

# The verbs shell completion offers. This is the dispatch chain's canonical verbs
# plus the aliases it accepts (list|servers, manifest|tools, quickstart|qs,
# status|brief), so completion can suggest anything the CLI would actually run.
#
# It drifted: the four completion scripts each hardcoded their own copy and had
# gone stale — bench, config, footer-facts, off, plugin, report, restore, skills,
# stats, status, toggle, uninstall and update were all missing, so tab-completion
# could not suggest a third of the CLI. A test that only spot-checked five names
# let it pass. Keeping the list here, next to the dispatch table's other frozenset,
# makes the next verb a one-line addition; tests/test_completion.py derives the
# dispatch set from this file and fails if the two ever disagree.
_COMPLETION_COMMANDS = (
    "activity", "add", "bench", "call", "completion", "config", "demo", "demo-server",
    "discover", "docs", "doctor", "exec", "footer-facts", "health", "help", "import",
    "init", "inspect", "install", "kb", "list", "manifest", "mode", "off", "openapi", "graphql", "auth", "resources", "prompts", "complete", "bake", "plugin",
    "policy", "quickstart", "remove", "report", "savings", "restore", "retrieve", "search",
    "select", "serve", "session", "skills", "stats", "status", "statusline", "sync", "toggle", "credit",
    "uninstall", "update", "usage", "upgrade",
    # aliases the dispatch chain also accepts
    "servers", "tools", "qs", "brief",
)
_CMD_WORDS = " ".join(_COMPLETION_COMMANDS)
_CMD_PS_WORDS = ",".join("'" + c + "'" for c in _COMPLETION_COMMANDS)


def unknown_flag_warnings(args):
    """Return the long options in args that mcptoon does not implement.

    Unknown options used to be dropped silently, which let a flag that never
    existed ("--tokens") sit in the README as the documented way to reproduce
    the token numbers. The parse loop now *fails* on an unknown flag (exit 2)
    rather than warning and running on, so a typo like `--jsn` cannot silently
    produce default output; `MCPTOON_STRICT_FLAGS=0` downgrades that to a warning.
    This helper stays a pure query so tests and other callers can ask "which of
    these are unknown?" without side effects.
    """
    found = []
    for a in args:
        if a.startswith("--"):
            base = a.split("=", 1)[0]
            if base not in KNOWN_FLAGS:
                found.append(base)
    return found


def _closest(word, candidates, n=3, cutoff=0.6):
    """Return up to `n` near-matches for `word` from `candidates` (may be empty).

    One helper for both "unknown command" and "unknown option", so the two error
    paths suggest in the same way. `difflib.get_close_matches` uses the ratio of
    common characters, which is the right shape for typos like `notacommand` or
    `--jsn` -> `--json`. An empty list is a valid answer; callers fall back to the
    plain hint when there is nothing close.
    """
    try:
        return difflib.get_close_matches(word, list(candidates), n=n, cutoff=cutoff)
    except Exception:
        return []


def _err(*args, **kwargs):
    """Print an error / usage hint to STDERR.

    Error and "how to use this" messages used to go to stdout, so `mcptoon x >out
    2>err` mixed failures into `out` and left `err` empty — a script could not tell
    success text from a failure. Every message that is followed by a non-zero exit
    (a bad argument, a missing server, an unknown policy, a usage block) goes here;
    legitimate empty *results* ("no matches", an informational list) stay on stdout
    because they are the command's answer, not an error. Reported 2026-10-17.
    """
    print(*args, file=sys.stderr, **kwargs)



# The output-format flags are one mutually exclusive family: each sets `fmt`, and the
# last one on the command line wins. Last-wins is a fine convention, so the ordering is
# not itself the bug — the bug is that one member of the family loses *invisibly*.
# `--smart` is the flag people reach for to turn compression ON, and its whole effect is
# a size difference, so `mcptoon call s t --smart --json` looks like success: valid JSON,
# and no hint that nothing was compressed. The other flags lose visibly — ask for TOON
# after `--json` and you can see you got JSON. So only the `--smart` loss is reported,
# and only it: warning on every disagreeing pair would nag the *correct* order
# (`--json --smart`, which is how the gateway itself calls) about a flag that worked.
# Same silent-degradation class as `fmt="smart"` reaching `output.render` directly
# (see tests/test_smart_reachability.py).
_FORMAT_FLAGS = {
    "--json": "json",
    "--compact": "compact",
    "--toon": "toon",
    "--mcptoon": "mcptoon",
    "--slim": "slim",
    "--smart": "smart",
    "--raw": "raw",
}


def format_flag_override_note(previous, current):
    """Return the stderr note when a later format flag drops `--smart`, else "".

    ``previous``/``current`` are the spellings as typed (``--smart``, ``--json``, ...),
    in command-line order. Quiet unless ``--smart`` is the flag being superseded: that
    is the one loss the caller cannot see for themselves.
    """
    if previous != "--smart" or current == "--smart":
        return ""
    return (
        f"mcptoon: '{current}' overrides '--smart', so the result is NOT compressed "
        f"(format flags are last-wins; put '--smart' last) - see 'mcptoon --help'"
    )


# Commands whose whole job is to make noise already; the one-time welcome would
# only be in the way (and `serve` speaks over stdio, so stdout must stay clean).
# `off` and `uninstall` are here for a different reason: a farewell should not be
# preceded by "hi, here's what I configured for you" — greeting someone on the way
# out is the same obliviousness this release is about.
_WELCOME_EXEMPT = frozenset({"serve", "demo", "demo-server", "completion",
                             "help", "-h", "--help", "off", "restore", "uninstall",
                             # `savings` and `report` are the savings story itself —
                             # a first-run greeting in front of them is a card
                             # explaining what the screen is already showing.
                             "savings", "report",
                             # `retrieve` prints a payload on stdout, so the
                             # one-time greeting must not land in front of it —
                             # the same reason `serve` is here.
                             "retrieve",
                             # These two are consumed by a *machine*, not a person:
                             # `statusline` is rendered by a host's status bar and
                             # `footer-facts` is pasted verbatim into a chat by the
                             # model. A 16-line greeting in front of either is not
                             # noise, it is a broken badge (measured 2026-10-19: a
                             # fresh home printed the banner ahead of the badge, so
                             # the status bar showed box-drawing instead of a count).
                             "statusline", "footer-facts"})


def _maybe_welcome(command: str, fmt: str) -> None:
    """Introduce mcptoon once per machine — the answer to "it installed silently".

    A pip install cannot print anything, so a tool that never speaks looks like
    something that installed a trojan. The first real command therefore greets
    once — through `welcome.render()`, which owns the layout, the colour, the
    glyph fallback and the language — and the marker file means never again.
    Silent when: not the first run, `welcome off`, a machine-readable format was
    asked for (JSON/TOON/slim), or the command already prints its own noise.
    """
    if command in _WELCOME_EXEMPT:
        return
    if fmt != "auto":
        return
    try:
        if not cfg.welcome_enabled() or cfg.welcome_seen():
            return
    except Exception:
        return

    # Figures come from `footer.facts()`: cache-only (it never spawns a server),
    # one tokenizer, so the greeting and the per-turn footer cannot quote two
    # different numbers a second apart. A greeting that disagrees with the footer
    # is a bug report, not a decoration.
    try:
        from . import footer as footer_mod
        facts = footer_mod.facts()
    except Exception:
        facts = {}

    # The skills index is a file read; when it was never built the row is dropped
    # rather than shown as 0 — "0 skills" would be a claim, and a false one.
    skills_count: int | None = None
    try:
        from . import skills as skills_mod
        skills_count = len(skills_mod.load_index().get("skills") or []) or None
    except Exception:
        skills_count = None

    from . import welcome as welcome_mod
    try:
        _wmode = footer_mod.current_mode()
    except Exception:
        _wmode = None
    print(welcome_mod.render(facts, skills=skills_count, lng=cfg.resolve_lang(),
                             mode=_wmode))

    cfg.mark_welcome_seen()


def _bare_greeting() -> None:
    """Greet on a bare `mcptoon` — the answer to "I opened it and nothing happened".

    `mcptoon` with no arguments is the most natural way to open the tool, and it
    used to print the help page with no sign mcptoon was even installed. This
    prepends a greeting: the full once-per-machine card on a first run, a one-line
    `welcome.hint()` afterwards, then the help page follows as before.

    Best-effort throughout: the help page must still print even if the greeting
    cannot be built, and `welcome off` silences it like every other surface.
    """
    try:
        from . import config as cfg

        if not cfg.welcome_enabled():
            return
        from . import welcome as welcome_mod

        if cfg.welcome_seen():
            print(welcome_mod.hint(lng=cfg.resolve_lang()))
            return

        from . import footer as footer_mod
        try:
            facts = footer_mod.facts()
        except Exception:
            facts = {}
        skills_count: int | None = None
        try:
            from . import skills as skills_mod
            skills_count = len(skills_mod.load_index().get("skills") or []) or None
        except Exception:
            skills_count = None
        print(welcome_mod.render(facts, skills=skills_count, lng=cfg.resolve_lang(),
                                 mode=footer_mod.current_mode()))
        cfg.mark_welcome_seen()
    except Exception:
        return


# Commands that must never self-heal: `serve` speaks JSON-RPC over stdio (stdout
# must stay clean, and it is spawned per host connection, so a write there would
# be a write on every reconnect); `off`/`restore`/`uninstall` are taking things away
# (and `restore` in particular must not immediately re-add a skill right after the
# user asked to go back to the pre-mcptoon state).
_SELF_HEAL_EXEMPT = frozenset({"serve", "off", "restore", "uninstall", "demo",
                               "demo-server", "completion", "help",
                               # Machine-consumed output, same reason as the welcome
                               # list: the self-heal prints install lines on stdout,
                               # and a host's status bar would render them as the
                               # badge. They run on every prompt, so silence matters.
                               "statusline", "footer-facts"})


def _first_run_self_heal() -> None:
    """On a machine's very first command, finish the install that pip could not.

    A `pip install` cannot run code, so it lands the *package* and nothing else:
    the skill sits in site-packages where no agent reads it, and no skill index
    exists, so `mcptoon skills resolve` answers from an empty catalog until
    `quickstart` happens to run. The fix is one write, once per machine, on the
    first real command — so a user who never runs `quickstart` still ends up with
    the agent-visible skill the docs promise ("pip install, then just use it").

    Why this is allowed to write where a normal command is read-only: it is an
    *addition* — copy one file into a folder that lacks it, refresh our own stale
    copy, build an index if none exists — and additions are the silent, reversible
    half of the write-consent rule (CONTEXT.md). It only ever writes *our* file: a
    `<view>/mcptoon` that declares a different `name` (another manager's skill, or
    a user's) is left alone, and `ensure_index` leaves a current index alone.
    Bounded exactly like the welcome: once per machine, off for pipes and machine
    formats, never inside `serve`. Best-effort throughout — a read-only home must
    not turn a normal command into a crash.
    """
    try:
        if os.environ.get("MCPTOON_SKIP_SELF_HEAL"):
            return
        # Hermetic by default under pytest: a test that runs a command in-process
        # would otherwise write into whatever `_view_roots()` / `_default_roots()`
        # resolve to. The dedicated self-heal tests opt back in with
        # MCPTOON_FORCE_SELF_HEAL and redirect every path they can touch.
        if "pytest" in sys.modules and not os.environ.get("MCPTOON_FORCE_SELF_HEAL"):
            return
        from . import config as cfg

        # Own marker, not the welcome's: the self-heal must run once even when the
        # welcome is turned off, and the welcome must still show on a machine where
        # the self-heal already ran. Cleared by `uninstall`, so a clean reinstall
        # self-heals again — right, since the skill views may have been cleaned too.
        # The marker carries the skill's fingerprint, so a release that ships a new
        # skill heals once more (the views hold a stale copy); otherwise an upgrade
        # would be a no-op and the agent would keep reading the old explanation.
        from . import skills as skills_mod

        fingerprint = skills_mod.self_fingerprint()
        if cfg.selfheal_done(fingerprint) and not skills_mod.views_missing_our_skill():
            return

        rows = skills_mod.install_self()
        wrote = [r for r in rows if r.get("written")]
        refreshed = [r for r in wrote if r.get("updated")]
        fresh = len(wrote) - len(refreshed)
        if fresh:
            print(f"  ✓ mcptoon skill installed for {fresh} agent folder(s) — "
                  f"they can read what the defaults are")
        if refreshed:
            print(f"  ✓ mcptoon skill updated for {len(refreshed)} agent folder(s) — "
                  f"they now read the current defaults")
        if not rows:
            print("  · no known agent skill folder here yet — for any agent mcptoon "
                  "does not know about, run: mcptoon skills install-self "
                  "--view <that agent's skills folder>")
        if skills_mod.ensure_index():
            n = len(skills_mod.load_index().get("skills") or [])
            if n:
                print(f"  ✓ Skill catalog indexed: {n} skill(s) routable "
                      f"via `mcptoon skills resolve`")
        cfg.mark_selfheal_done(fingerprint)
    except Exception:
        return


def _run(state: dict) -> None:
    args = sys.argv[1:]

    # One command per process, so the "did this run compress anything?" flag must
    # start clear. The footer reads it to decide whether to add the recovery hint;
    # an embedding process that reuses this module (a REPL, a test harness) would
    # otherwise inherit the previous run's True and print the hint unprompted.
    try:
        from . import compressor as _comp

        _comp.reset_compressed_this_run()
    except Exception:
        pass

    if not args:
        _bare_greeting()
        _print_help()
        sys.exit(0)

    if args[0] in ("--version", "-V"):
        # `--version --json` gives CI/scripts a machine-readable answer instead of
        # a line they must grep. The plain form is byte-for-byte unchanged.
        if "--json" in args:
            import platform
            print(json.dumps({
                "version": __import__("mcptoon").__version__,
                "python": platform.python_version(),
                "platform": platform.platform(),
            }, ensure_ascii=False))
        else:
            print(f"mcptoon {__import__('mcptoon').__version__}")
        return

    # ─── Parse global output flags ───
    fmt = "auto"
    fmt_flag = ""
    head_n = 0
    max_chars = 0
    full = False
    export_format = ""
    use_stdin = False
    fallback_json = False
    cmd_args = []

    i = 0
    while i < len(args):
        a = args[i]
        if a in _FORMAT_FLAGS:
            note = format_flag_override_note(fmt_flag, a)
            if note:
                print(note, file=sys.stderr)
            fmt = _FORMAT_FLAGS[a]
            fmt_flag = a
        elif a == "--full":
            full = True
        elif a == "--transport" and i + 1 < len(args):
            # Global preference for how HTTP MCP servers are negotiated.
            # Applied process-wide (see client.set_http_transport); a
            # per-server `http_transport` in config.json still wins.
            from . import client as client_mod
            try:
                client_mod.set_http_transport(args[i + 1])
            except ValueError as exc:
                _err(f"Error: {exc}")
                sys.exit(1)
            i += 1
        elif a.startswith("--transport="):
            from . import client as client_mod
            try:
                client_mod.set_http_transport(a.split("=", 1)[1])
            except ValueError as exc:
                _err(f"Error: {exc}")
                sys.exit(1)
        elif a == "--stdin":
            use_stdin = True
        elif a == "--fallback-json":
            fallback_json = True
        elif a == "--head" and i + 1 < len(args):
            try:
                head_n = int(args[i + 1])
            except ValueError:
                # A non-integer used to be swallowed silently, so `--head abc`
                # (or `--head=xyz`) left head_n at 0 = "unlimited" and printed
                # every result. A scripted `search q --head $N` with a bad $N then
                # looked like it worked (reported 2026-10-18). Fail loudly instead.
                _err(f"Error: --head needs an integer, got {args[i + 1]!r}")
                sys.exit(1)
            i += 1
        elif a == "--max-chars" and i + 1 < len(args):
            try:
                max_chars = int(args[i + 1])
            except ValueError:
                _err(f"Error: --max-chars needs an integer, got {args[i + 1]!r}")
                sys.exit(1)
            i += 1
        elif a.startswith("--head="):
            try:
                head_n = int(a.split("=", 1)[1])
            except ValueError:
                _err(f"Error: --head needs an integer, got {a.split('=', 1)[1]!r}")
                sys.exit(1)
        elif a.startswith("--max-chars="):
            try:
                max_chars = int(a.split("=", 1)[1])
            except ValueError:
                _err(f"Error: --max-chars needs an integer, got {a.split('=', 1)[1]!r}")
                sys.exit(1)
        elif a == "--dir" and i + 1 < len(args):
            # Already applied by `_apply_dir_flag` before dispatch; consumed here
            # only so it is not mistaken for the command name.
            i += 1
        elif a.startswith("--dir="):
            pass
        elif a == "--format" and i + 1 < len(args):
            export_format = args[i + 1]
            i += 1
        elif a.startswith("--format="):
            export_format = a.split("=", 1)[1]
        else:
            bad = unknown_flag_warnings([a])
            if bad:
                # A typo'd flag used to be printed as "... ignored" and the command
                # ran on with default behaviour — so `--jsn`/`--tooon` silently gave
                # the default format and a benchmark number that could not be
                # reproduced (reported 2026-10-17: `serve --nonsense` printed
                # "ignored" and then "serve started"). Fail instead of pretending.
                # `MCPTOON_STRICT_FLAGS=0` restores the old warn-and-continue for a
                # caller that pipes a future flag through an older CLI.
                msg = (f"mcptoon: unknown option '{bad[0]}' - see 'mcptoon --help' "
                       f"for the flags this version accepts")
                near = _closest(bad[0], KNOWN_FLAGS)
                if near:
                    msg += f"\n  did you mean: {', '.join(near)}?"
                if os.environ.get("MCPTOON_STRICT_FLAGS", "1") != "0":
                    print(msg, file=sys.stderr)
                    sys.exit(2)
                print(msg + " (ignored: MCPTOON_STRICT_FLAGS=0)", file=sys.stderr)
            cmd_args.append(a)
            # `openapi`/`graphql`/`auth`/`bake` pass their own flags through to
            # the module (e.g. `mcptoon openapi call <spec> <cmd> <param>=<value>`,
            # `mcptoon bake create <name> --openapi <spec>`). Those flags are
            # unknown to the global parser, which would reject them with exit 2.
            # Stop parsing here and hand the remainder over verbatim.
            if a in ("openapi", "graphql", "auth", "bake") and len(cmd_args) == 1:
                cmd_args.extend(args[i + 1:])
                break
        i += 1

    if not cmd_args:
        _print_help()
        sys.exit(0)

    command = cmd_args[0]
    rest = cmd_args[1:]
    state["command"] = command

    # Asking for help must never run the command you asked about: `mcptoon
    # quickstart --help` used to discover servers and write them into config, and
    # `mcptoon serve --help` used to open a stdio bridge and hang until timeout.
    # For a command with its own help page, that page runs and returns; otherwise
    # we print the command's own usage (its handler docstring) followed by the
    # full reference — `skills --help`, `docs --help`, `quickstart --help` used to
    # print the *general* help byte-for-byte, so there was no way to learn a
    # subcommand's own flags (reported 2026-10-17).
    if command not in _COMMANDS_WITH_OWN_HELP and any(a in ("-h", "--help") for a in rest):
        _print_command_help(command)
        return

    # First real command on this machine introduces mcptoon once (see _maybe_welcome).
    _maybe_welcome(command, fmt)

    # ...and, on that same first command, finishes the install pip could not: the
    # agent-visible skill + a skill index. Once per machine; additions only.
    if fmt == "auto" and command not in _SELF_HEAL_EXEMPT:
        _first_run_self_heal()

    # ─── Dispatch ───
    if command in ("list", "servers"):
        _cmd_list(rest, fmt, head_n, max_chars, full)
    elif command in ("manifest", "tools"):
        _cmd_manifest(rest, fmt, head_n, max_chars, full, export_format)
    elif command == "inspect":
        _cmd_inspect(rest, fmt, max_chars, full, head_n)
    elif command == "search":
        _cmd_search(rest, fmt, head_n, max_chars, full)
    elif command == "select":
        _cmd_select(rest, fmt, head_n, max_chars, full)
    elif command == "call":
        _cmd_call(rest, fmt, head_n, max_chars, full, use_stdin, fallback_json)
    elif command == "exec":
        _cmd_exec(rest, fmt, full)
    elif command in ("quickstart", "qs"):
        _cmd_quickstart(rest, fmt)
    elif command == "init":
        _cmd_init(rest, fmt)
    elif command == "add":
        _cmd_add(rest)
    elif command == "remove":
        _cmd_remove(rest)
    elif command == "usage":
        _cmd_usage(rest, fmt, head_n, max_chars, full)
    elif command in ("status", "brief"):
        _cmd_status(rest, fmt)
    elif command == "stats":
        _cmd_stats(rest, fmt, head_n, max_chars, full)
    elif command == "activity":
        _cmd_activity(rest, fmt, head_n, max_chars, full)
    elif command == "report":
        from . import report as report_mod
        report_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "savings":
        from . import savings as savings_mod
        savings_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "mode":
        from . import mode as mode_mod
        mode_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "credit":
        _cmd_credit(rest, fmt, head_n, max_chars, full)
    elif command == "statusline":
        from . import mode as mode_mod
        mode_mod.run_statusline(rest, fmt, head_n, max_chars, full)
    elif command == "docs":
        from . import docs as docs_mod
        docs_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "kb":
        from . import kb as kb_mod
        kb_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "openapi":
        from . import openapi as openapi_mod
        openapi_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "graphql":
        from . import graphql as graphql_mod
        graphql_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "auth":
        from . import oauth as oauth_mod
        oauth_mod.run(rest, fmt, head_n, max_chars, full)
    elif command in ("resources", "prompts", "complete"):
        from . import mcp_extras as extras_mod
        # Prepend the pillar so the module knows which one was invoked.
        extras_mod.run([command] + rest, fmt, head_n, max_chars, full)
    elif command == "bake":
        from . import bake as bake_mod
        bake_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "session":
        from . import session_log as session_mod
        session_mod.run(rest, fmt, head_n, max_chars, full)
    elif command == "retrieve":
        _cmd_retrieve(rest, fmt, max_chars)
    elif command == "footer-facts":
        _cmd_footer_facts(rest, fmt, max_chars)
    elif command == "toggle":
        _cmd_toggle(rest, fmt, head_n, max_chars, full)
    elif command == "policy":
        _cmd_policy(rest, fmt, head_n, max_chars, full)
    elif command == "discover":
        if "--health" in rest:
            # Legacy health-check mode
            health_args = [a for a in rest if a != "--health"]
            _cmd_health_check(health_args, fmt, head_n, max_chars, full)
        else:
            _cmd_auto_discover(rest, fmt, head_n, max_chars, full)
    elif command == "import":
        _cmd_import(rest, fmt, head_n, max_chars, full)
    elif command == "doctor":
        _cmd_doctor(rest, fmt)
    elif command == "install":
        _cmd_install(rest, fmt, full, head_n, max_chars)
    elif command == "update":
        from . import update as update_mod
        update_mod.run(rest, fmt)
    elif command == "upgrade":
        from . import upgrade as upgrade_mod
        upgrade_mod.run(rest, fmt)
    elif command == "completion":
        _cmd_completion(rest)
    elif command == "serve":
        _cmd_serve(rest)
    elif command == "demo":
        _cmd_demo(rest)
    elif command == "demo-server":
        _cmd_demo_server(rest)
    elif command == "sync":
        _cmd_sync(rest, fmt)
    elif command == "off":
        _cmd_off(rest, fmt)
    elif command == "restore":
        _cmd_restore(rest, fmt)
    elif command == "uninstall":
        _cmd_uninstall(rest, fmt)
    elif command == "health":
        _cmd_health(rest, fmt)
    elif command == "plugin":
        _cmd_plugin(rest, fmt)
    elif command == "skills":
        from .skills import _cmd_skills
        _cmd_skills(rest, fmt, head_n, max_chars, full)
    elif command == "bench":
        from .bench import run_bench
        run_bench(rest, fmt)
    elif command == "config":
        _cmd_config(rest, fmt, head_n, max_chars, full)
    elif command in ("help", "-h", "--help"):
        # `mcptoon help <command>` shows that command's own page, exactly like
        # `mcptoon <command> --help`. It used to ignore the argument and always
        # print the global page, so the two documented routes to a command's help
        # disagreed (reported 2026-10-17). No argument (or an unknown one) still
        # prints the global reference — `_print_command_help` falls back for us.
        if rest and rest[0].lower() not in ("help", "-h", "--help"):
            _print_command_help(rest[0].lower())
        else:
            _print_help()
    else:
        # Try natural language: "mcptoon 有什么工具"
        _try_natural(command, rest, fmt, head_n, max_chars, full)


def _apply_dir_flag(argv: list) -> None:
    """Honour `--dir <path>` / `--dir=<path>` before anything reads a path.

    Deliberately tolerant: a bare `--dir` with no value, or `--dir` followed by
    another flag, is left alone for the normal parser to reject with its own
    message. Doing the validation here would mean two places deciding what a
    missing argument means.
    """
    for i, a in enumerate(argv):
        if a == "--dir" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            cfg.apply_home(argv[i + 1])
            return
        if a.startswith("--dir=") and a[6:]:
            cfg.apply_home(a[6:])
            return


def _harden_stream_encoding() -> None:
    """Keep every command from crashing on a non-UTF-8 console.

    mcptoon prints box-drawing and status glyphs (`✓ 🎉 ⚠ ❌ →`). A plain Chinese
    Windows console is cp936/GBK by default (Python's *legacy* mode, `utf8_mode`
    off), and `print("✓ ...")` there raises `UnicodeEncodeError: 'gbk' codec can't
    encode character '\\u2713'` — a raw traceback, exit 1. Measured on 0.8.29: with
    `PYTHONUTF8=0 PYTHONIOENCODING=gbk`, `status`, `doctor`, `footer-facts`,
    `quickstart`, `demo`, `sync` and `off` all crashed this way; only pure-ASCII
    commands survived. The CI `cp936` job only exercised stdin decoding, so it never
    saw the stdout side.

    The fix is one seam at startup: for each of stdout/stderr, *keep the console's
    own encoding* (so Chinese text stays readable in the user's terminal) but add
    `errors="replace"`, and when the stream is NOT a tty (piped into an agent,
    redirected to a file — mcptoon's main use) switch to UTF-8 with
    `errors="replace"`. Either way a glyph that the codec cannot represent becomes
    a placeholder instead of a crash, and nothing a command prints can kill it.

    Never raises: a stream that cannot be reconfigured (already detached, a
    wrapper) is left as-is; this is a safety net, not a dependency.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is None:
                continue
            is_tty = False
            try:
                is_tty = stream.isatty()
            except Exception:
                is_tty = False
            if is_tty:
                # Keep the console's encoding (localized text readable); only stop
                # it from raising on a glyph the codec lacks.
                reconfigure(errors="replace")
            else:
                # Piped / redirected: a byte stream with no console to render into.
                # UTF-8 is what agents, files and downstream tools expect.
                reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> None:
    """Entry point: run the CLI, then emit the savings footer.

    The footer cannot sit at the end of `_run`, because 41 places in this module
    leave through `sys.exit()` — `mcptoon manifest` among them — and a raised
    `SystemExit` skips everything written after the dispatch. Catching it here is
    the one seam that sees every exit path.

    Emitted only on success (`code` falsy): after a failed command the terminal
    already carries a diagnostic and one more line is noise. `_run` records the
    resolved command in `state`; the paths that never resolve one — `mcptoon
    --version`, or no arguments at all — leave it empty and stay silent, which
    keeps the version string parseable by scripts.

    Deliberately not `atexit`: that would also fire after an unhandled traceback
    and for any other caller of `_run`, and it could not tell success from
    failure.
    """
    state: dict = {}
    # Make printing glyph-safe before any command can emit one (GBK console crash —
    # see _harden_stream_encoding). Runs on the raw process streams, once.
    _harden_stream_encoding()
    # `--dir` must land before any command reads a path, and it has to survive
    # the 41 `sys.exit()` paths inside `_run` — so it is applied here, once, on
    # the raw argv. See config.apply_home for why the flag cannot simply set an
    # environment variable.
    _apply_dir_flag(sys.argv[1:])
    try:
        _run(state)
    except SystemExit as exc:
        if not exc.code:
            _emit_presence(state.get("command", ""))
            _emit_footer(state.get("command", ""))
        raise
    _emit_presence(state.get("command", ""))
    _emit_footer(state.get("command", ""))


# Commands whose streams are a protocol, not a human terminal, plus the one
# command that has already printed the same block.
_FOOTER_SILENT_COMMANDS = frozenset({"serve", "demo-server", "footer-facts", "report", "statusline", "savings"})


def _emit_presence(command: str) -> None:
    """Print the short "mcptoon routed N calls" line to stderr — the presence channel.

    The savings footer says how much was *saved*; this says mcptoon was *used at
    all*, which is the thing a person who installed it and forgot is actually
    asking ("is this even doing anything?"). It fires only when this command
    really routed at least one call (`usage.take_session_calls`), so an ordinary
    `mcptoon status` stays silent — there is nothing to announce.

    stderr, never stdout: the same rule as the footer — stdout is machine output.
    Its own switch (`presence`, default on) so it can be kept while the savings
    card is turned off, and its own dedupe via `footer.changed`/`remember` under a
    distinct key so a repeated line is not re-printed turn after turn.

    Never raises: presence is a courtesy and must not fail a command.
    """
    if not command or command.startswith("-") or command in _FOOTER_SILENT_COMMANDS:
        return
    try:
        from . import config as cfg
        from . import footer as footer_mod
        from . import usage as usage_mod

        if not cfg.presence_enabled():
            return
        n = usage_mod.take_session_calls()
        if n <= 0:
            return
        host = usage_mod.get_host()
        # "brief" only speaks when the fuller ledger has not been seen lately;
        # without a cheap recency signal it behaves like "on" for the call count
        # but skips the host clause. Kept simple on purpose — the win is being
        # noticed, not tuning verbosity per turn.
        if cfg.presence_mode() == "brief":
            host = None
        calls = "1 call" if n == 1 else f"{n} calls"
        via = f" for {host}" if host else ""
        line = f"▸ mcptoon routed {calls}{via} this command — see `mcptoon activity`"
        if not footer_mod.changed("presence:" + line):
            return
        print(line, file=sys.stderr)
        footer_mod.remember("presence:" + line)
    except Exception:
        return


def _emit_footer(command: str) -> None:
    """Print the savings line to stderr after a command finishes.

    The CLI half of the universal-surface design described in the `footer`
    module: every agent that can run a shell sees command output, so a tail here
    reaches Codex, DSH, Gemini CLI, Aider and everything else that has a
    terminal — no per-agent configuration, no reliance on the model remembering
    a directive.

    stderr rather than stdout, deliberately. stdout is machine-readable for
    `--json`, `--toon` and piped output, and a courtesy line that corrupts
    `mcptoon status --json | jq` would be a worse bug than the invisibility it
    fixes. Terminals and agent tool surfaces both display stderr.

    Silent for the MCP stdio servers (`serve`, `demo-server`), where one stray
    write can desynchronise the JSON-RPC stream, and for `footer-facts`, which
    already printed this exact block on stdout.

    A byte-identical repeat is skipped (`footer.changed`/`remember`): the line
    exists to be read, and a badge that says the same thing every turn is not
    read. On a normal terminal this rarely fires — each command is its own
    process and usually follows a different one — but an agent that runs mcptoon
    in a loop is exactly the reader this saves.

    Never raises: a footer is a courtesy, and a command must not fail because
    its footer could not be built.
    """
    if not command or command.startswith("-") or command in _FOOTER_SILENT_COMMANDS:
        return
    try:
        from . import footer as footer_mod

        if not footer_mod.enabled():
            return
        text = footer_mod.block()
        if not footer_mod.changed(text):
            return
        print(text, file=sys.stderr)
        footer_mod.remember(text)
    except Exception:
        return


def _cli_receipt_data(server: str, tool: str, result) -> dict | None:
    """The machine-readable CLI credit for one call, or None when nothing applies.

    One source for both the human stderr line and the `call --json` field, so the
    two can never quote different numbers. None when: the mode is not `cli` (a
    serve user's truth is different and smaller), the call failed (a receipt on a
    broken call lies about what was saved), or there is no catalog to measure.
    ``server`` may be empty on the `--auto` path — then only the catalog figure is
    reported, never a guessed per-schema one.
    """
    try:
        from . import footer as footer_mod

        if _tool_result_failed(result):
            return None
        f = footer_mod.facts()
        credit = footer_mod.cli_credit(f)
        if credit is None:
            return None
        return {
            "mode": "cli",
            "resident_avoided": int(credit["resident_avoided"]),
            "schema_tokens": footer_mod.tool_schema_tokens(server, tool) if server else 0,
            "caliber": credit.get("caliber") or "",
        }
    except Exception:
        return None


def _cli_call_receipt(server: str, tool: str, result) -> str | None:
    """The per-call CLI credit line, or None when this call has nothing to claim.

    This is the answer to "CLI mode never shows its 功劳": the *footer* is a
    cumulative block shown after every command, but a single `mcptoon call` had no
    line of its own saying what it just did for the user. Under CLI delivery the
    claim is concrete and one-shot — the call pulled one schema and never loaded
    the catalog — so it is stated here, at the call, in the caller's language.

    Never raises — a receipt is a courtesy.
    """
    try:
        data = _cli_receipt_data(server, tool, result)
        if data is None:
            return None
        from . import footer as footer_mod

        resident = footer_mod._human_tokens(data["resident_avoided"])
        pulled = data["schema_tokens"]
        if footer_mod.lang() == "zh":
            if pulled:
                return (f"▸ 本次只拉了 1 个 schema（{pulled:,} token），"
                        f"全量 {resident} token 没进上下文")
            return f"▸ 本次按需只取 1 个 schema，全量 {resident} token 没进上下文"
        if pulled:
            return (f"▸ pulled 1 schema this call ({pulled:,} tok); "
                    f"{resident} tokens kept out of context")
        return (f"▸ fetched 1 schema on demand; "
                f"{resident} tokens kept out of context")
    except Exception:
        return None


def _emit_cli_receipt(server: str, tool: str, result, machine: bool = False) -> None:
    """Print the per-call receipt to stderr, plus a one-time first-call 'aha'.

    stderr, never stdout — the same rule as the footer: stdout is the tool result
    and must stay parseable. Gated by `receipt` (default on) and only meaningful
    on the CLI path (`_cli_call_receipt` returns None otherwise). The first CLI
    call on a machine gets one extra explanatory line, then never again (its own
    marker), because the point is to make the very first saving legible — not to
    recite the explainer every call.

    ``machine`` (set when the caller asked for `--json`) prints the receipt as a
    single JSON object on stderr instead of prose, so a script can read "how much
    did this call save" without parsing the tool result or corrupting it — the
    result on stdout stays exactly what the server returned.
    """
    try:
        from . import config as cfg

        if not cfg.receipt_enabled():
            return
        data = _cli_receipt_data(server, tool, result)
        if data is None:
            return
        if machine:
            print(json.dumps({"_mcptoon_receipt": data}, ensure_ascii=False),
                  file=sys.stderr)
            return
        line = _cli_call_receipt(server, tool, result)
        if not line:
            return
        print(line, file=sys.stderr)
        if not cfg.cli_aha_seen():
            from . import footer as footer_mod

            resident = footer_mod._human_tokens(data.get("resident_avoided", 0))
            if footer_mod.lang() == "zh":
                print(f"  （第一次用 CLI 调用：直连会先把全量 {resident} token 的 schema "
                      f"塞进上下文；CLI 只取要用的那一个。以后不再提示。）",
                      file=sys.stderr)
            else:
                print(f"  (First CLI call: a direct connection would load all {resident} "
                      f"tokens of schemas into context; CLI fetched only the one it used. "
                      f"Shown once.)", file=sys.stderr)
            cfg.mark_cli_aha_seen()
    except Exception:
        return

_FIX_SUGGESTIONS = {
    "SERVER_NOT_FOUND": "Try: mcptoon list    | mcptoon add <name> --stdio npx -y <package>    | mcptoon doctor",
    # `quickstart` leads, not `init`: it is the designed entry point (the one the
    # README, the welcome card and `status` all push), and an error hint that
    # names a *different* first command than every other surface sends a new user
    # down a fork on their very first failure. `init --auto` stays as the explicit
    # alternative. (2026-09-26 polish pass.)
    "CONFIG_MISSING": "Try: mcptoon quickstart    | mcptoon init --auto",
    "TOOL_NOT_FOUND": "Try: mcptoon manifest    | mcptoon inspect <server>",
    "UNKNOWN_TOOL": "Try: mcptoon inspect <server>    | mcptoon manifest --slim",
    "CONNECTION_FAILED": "Try: mcptoon doctor    | check if npx/node is installed and in PATH",
    "TIMEOUT": "Try: mcptoon doctor    | the server may be slow to start (first npx download)",
    "DANGEROUS_OP": "Add --destructive flag to confirm: mcptoon call <server> <tool> '{...}' --destructive",
    "CREDENTIAL_LEAK": "Result blocked for safety. If this is a false positive, use --raw to bypass",
    "TOOL_POISONING": "Result blocked for safety. If this is a false positive, use --raw to bypass",
    "PARSE_ERROR": "Try: mcptoon inspect <server> <tool>    | check required parameters and types",
}


def _fix_suggestion(code: str, server: str = "", tool: str = "") -> str:
    """Return a fix suggestion string for a given error code."""
    suggestion = _FIX_SUGGESTIONS.get(code, "")
    if suggestion and server:
        suggestion = suggestion.replace("<server>", server)
    if suggestion and tool:
        suggestion = suggestion.replace("<tool>", tool)
    return suggestion


# ═══════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════

def _cmd_list(rest, fmt="auto", head_n=0, max_chars=0, full=False):
    """List configured servers.

    Usage:
        mcptoon list                  # human-readable list
        mcptoon list --json           # structured [{name, transport, command/url}]
        mcptoon list --head 5         # first 5 servers only

    `--json`/`--head`/`--max-chars` were ignored: `list` had no access to the
    global flags, so a script could not get the server list as data and `--head`
    did nothing (reported 2026-10-18). Now honoured.
    """
    servers = cfg.list_servers()
    if not servers:
        if fmt == "json":
            print(output.render([], fmt="json", head_n=head_n, max_chars=max_chars, full=full))
        else:
            print("No servers configured. Run: mcptoon quickstart")
        return

    records = []
    for name in servers:
        s_cfg = cfg.get_server_config(name) or {}
        transport = s_cfg.get("transport", "stdio")
        if transport == "stdio":
            cmd = s_cfg.get("command", [])
            cmd_list = cmd if isinstance(cmd, list) else [cmd]
            records.append({
                "name": name, "transport": "stdio",
                "command": cmd_list + s_cfg.get("args", []),
            })
        else:
            records.append({"name": name, "transport": "http",
                            "url": s_cfg.get("url", "?")})

    if fmt in ("json", "toon", "slim", "compact", "mcptoon"):
        print(output.render(records, fmt=("json" if fmt == "auto" else fmt),
                            head_n=head_n, max_chars=max_chars, full=full))
        return

    total = len(records)
    if head_n and head_n > 0:
        records = records[:head_n]
    shown = f"{len(records)} of {total}" if len(records) < total else f"{len(records)}"
    print(f"Configured servers ({shown}):")
    for r in records:
        if r["transport"] == "stdio":
            print(f"  {r['name']:20s} [stdio]  {' '.join(r['command'])}")
        else:
            print(f"  {r['name']:20s} [http]   {r['url']}")


def _cmd_manifest(rest, fmt, head_n, max_chars, full, export_format=""):
    """List all tools."""
    full_mode = "--full" in rest or full

    # --sort / --top / --verbose (mcp2cli parity). Parsed here rather than in
    # the global loop because they only mean something to `manifest`.
    sort_order = "default"
    top_n = 0
    verbose = "--verbose" in rest
    for i, a in enumerate(rest):
        if a == "--sort" and i + 1 < len(rest):
            sort_order = rest[i + 1]
        elif a.startswith("--sort="):
            sort_order = a.split("=", 1)[1]
        elif a == "--top" and i + 1 < len(rest):
            try:
                top_n = int(rest[i + 1])
            except ValueError:
                _err(f"  --top needs a number, got {rest[i + 1]!r}")
                sys.exit(1)
        elif a.startswith("--top="):
            try:
                top_n = int(a.split("=", 1)[1])
            except ValueError:
                _err(f"  --top needs a number, got {a.split('=', 1)[1]!r}")
                sys.exit(1)
    if sort_order not in ("default", "alpha", "usage", "recent"):
        _err(f"  --sort must be one of default|alpha|usage|recent, got {sort_order!r}")
        sys.exit(1)

    manifest = manifest_mod.get_manifest(use_cache=True)
    if not manifest:
        print("No tools found. Run: mcptoon quickstart")
        return

    # Order and cap before any renderer sees it, so every format agrees.
    manifest = manifest_mod.sort_manifest(manifest, sort_order)
    manifest = manifest_mod.cap_tools_per_server(manifest, top_n)

    # Export format takes priority
    if export_format:
        exported = manifest_mod.export_manifest(manifest, export_format)
        print(exported)
        # An exported manifest is almost always headed for a file or a pipe; when
        # this is going to a terminal (not redirected, no --json), point at the
        # save step so the user is not left to invent a redirect. Guarded by
        # isatty so a scripted `manifest --format openai > tools.json` gets clean
        # data on stdout with no hint appended.
        try:
            to_tty = sys.stdout.isatty()
        except Exception:
            to_tty = False
        if to_tty and fmt in ("auto", "human"):
            _err(f"  Save to a file: mcptoon manifest --format {export_format} > tools.json")
        return

    # `--head N` limits the number of SERVERS shown (manifest is keyed by server).
    # It used to be ignored in the human/compact/toon paths, so `manifest --head 2`
    # printed all servers (reported 2026-10-18). The slim path is tool-oriented and
    # already caps tool count through output.render, so it is left to that.
    if head_n and head_n > 0 and fmt != "slim":
        manifest = dict(list(manifest.items())[:head_n])

    if fmt == "slim":
        # For slim, output ultra-compact tool schemas
        all_tools = []
        for server, tools in manifest.items():
            for t in tools:
                if "error" not in t:
                    all_tools.append(t)
        print(output.render(all_tools, fmt="slim", head_n=head_n, max_chars=max_chars, full=full))
    elif fmt in ("toon", "mcptoon", "compact"):
        # For toon/mcptoon/compact, output just the tool names
        result = {}
        for server, tools in manifest.items():
            names = [t.get("name", "?") for t in tools if "error" not in t]
            if names:
                result[server] = names
        print(output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
    else:
        # Human-readable or JSON
        if fmt == "json":
            print(output.render(manifest, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
        else:
            # --verbose shows each tool's full description (wrapped); without
            # it, the name-only index stays the cheap default. --verbose implies
            # the same per-tool layout as --full but without the schema dump.
            text = manifest_mod.format_manifest(manifest, full=full_mode or verbose)
            if max_chars > 0:
                text = output._truncate(text, max_chars)
            print(text)
            # The name index IS what a CLI call loads to pick a tool — name its
            # size so "one cheap lookup" has a number. Human mode, stderr, CLI
            # only (off the CLI path the manifest size is not a per-call cost).
            if fmt in ("auto", "human"):
                try:
                    from . import footer as footer_mod
                    _f = footer_mod.facts()
                    _idx = _f.get("name_index_tokens") or 0
                    if footer_mod.cli_credit(_f) and _idx:
                        if cfg.resolve_lang() == "zh":
                            _err(f"这份名字索引 ≈ {_idx:,} token —— "
                                 f"一次 CLI 调用就取这么多来挑工具")
                        else:
                            _err(f"this name index ≈ {_idx:,} tokens — what a CLI "
                                 f"call loads to pick a tool")
                except Exception:
                    pass


def _cmd_inspect(rest, fmt, max_chars, full, head_n=0):
    """Show tool schema.

    `head_n` is the global `--head` flag. `inspect`'s payload is a single tool's
    schema — a mapping, not a record collection — so `--head` has nothing to cap
    here; it is accepted and forwarded for uniformity, not because it shrinks
    anything. See `_cmd_install` for why the flags travel together.
    """
    if not rest:
        _err("Usage: mcptoon inspect <server> <tool>")
        _err("       mcptoon inspect <server>           (list all tools)")
        sys.exit(1)

    server = rest[0]

    # `inspect <server>` with no tool lists that server's tools. The usage block
    # has always advertised this form, but the code required two args and exited 1
    # on one — the documented "list all tools" path was simply dead (reported
    # 2026-10-17). Honour it: same fetch `get_server_tools` uses for the not-found
    # fallback below, rendered through the normal output formatter.
    if len(rest) < 2:
        tools = manifest_mod.get_server_tools(server)
        errs = [t for t in tools if isinstance(t, dict) and "error" in t]
        if not tools or errs:
            raw = str(errs[0].get("error", "")) if errs else ""
            if raw:
                reason, next_step = manifest_mod.explain_error(raw)
                _err(f"Could not reach {server}: {reason}.")
                _err(f"  → {next_step}")
            else:
                _err(f"Server not found: {server}")
            sys.exit(1)
        print(output.render(tools, fmt=fmt if fmt != "auto" else "json", head_n=head_n,
                            max_chars=max_chars, full=full))
        # The list is the whole per-server schema set — the thing a CLI call does
        # NOT load (it fetches one). Say how big the set is, so "one at a time" has
        # a denominator. Human mode only, to stderr, so the data channel is pure.
        if fmt in ("auto", "human"):
            try:
                from .bench import _tokenizer
                from . import footer as footer_mod
                encode, _cal, _exact = _tokenizer()
                good = [t for t in tools if isinstance(t, dict) and "error" not in t]
                total = sum(max(1, int(encode(json.dumps(t, ensure_ascii=False))))
                            for t in good)
                credit = footer_mod.cli_credit(footer_mod.facts())
                if credit and cfg.resolve_lang() == "zh":
                    _err(f"这 {len(good)} 个 schema 共 ≈ {total:,} token —— CLI 一次只取其中 1 个")
                elif credit:
                    _err(f"{len(good)} schemas ≈ {total:,} tokens total — a CLI call "
                         f"fetches just one of them")
            except Exception:
                pass
        return

    tool = rest[1]

    info = manifest_mod.inspect_tool(server, tool)
    if not info:
        # Fuzzy match: "Did you mean?"
        suggestions = manifest_mod.fuzzy_match_tool(server, tool)
        if suggestions:
            _err(f"Tool not found: {server}:{tool}")
            _err(f"Did you mean: {', '.join(suggestions)}")
        else:
            _err(f"Tool not found: {server}:{tool}")
            # Show all tools for this server
            tools = manifest_mod.get_server_tools(server)
            # `get_server_tools` returns an error entry (not `[]`) when the server
            # never answered; name that instead of printing a bare "?" for it.
            errs = [t for t in tools if isinstance(t, dict) and "error" in t]
            names = [t.get("name", "?") for t in tools
                     if isinstance(t, dict) and "error" not in t]
            if names:
                _err(f"Available tools: {' '.join(names)}")
            elif errs:
                # The server never answered. Say why in plain words and what to do
                # next, instead of echoing a protocol string — this is the moment a
                # user is most likely to conclude "mcptoon is broken" when the real
                # cause is their server.
                raw = str(errs[0].get("error", ""))
                reason, next_step = manifest_mod.explain_error(raw)
                _err(f"Could not reach {server}: {reason}.")
                _err(f"  → {next_step}")
                _err(f"  (raw: {raw[:120]})")
        sys.exit(1)

    print(output.render(info, fmt=fmt if fmt != "auto" else "json", head_n=head_n,
                        max_chars=max_chars, full=full))
    # `inspect` printed the schema and stopped, leaving the reader to turn
    # `required`/`properties` into an argument object. Show the ready-to-edit call.
    # To stderr and only in human mode, so `inspect ... > schema.json` and every
    # machine format (json/toon/slim/compact) stay pure data.
    if fmt in ("auto", "human"):
        _err(_call_example_from_schema(server, tool, info))
        # On a CLI machine this is the schema a call pulls *on demand* — the whole
        # point of the CLI caliber is that it fetches exactly this one, not the
        # catalog. Say how big "this one" is so the abstract "one schema at a time"
        # has a number. Gated to CLI so a serve user's output is byte-unchanged
        # (serve does not fetch individual schemas this way).
        try:
            from .bench import _tokenizer
            from . import footer as footer_mod
            credit = footer_mod.cli_credit(footer_mod.facts())
            if credit:
                encode, _cal, _exact = _tokenizer()
                tok = max(1, int(encode(json.dumps(info, ensure_ascii=False))))
                if cfg.resolve_lang() == "zh":
                    _err(f"这一个 schema ≈ {tok:,} token —— CLI 按需只取这一份，"
                         f"全量 {credit['resident_avoided']:,} token 不进上下文")
                else:
                    _err(f"this one schema ≈ {tok:,} tokens — a CLI call fetches "
                         f"just this, keeping the full "
                         f"{credit['resident_avoided']:,} out of context")
        except Exception:
            pass


def _call_json_error_hint(server, tool):
    """The lines to print after a JSON-arguments parse error in `call`.

    A raw `Expecting property name enclosed in double quotes` is a Python
    traceback fragment, not an instruction: it tells the user their JSON is bad
    but not what good looks like for *this* tool. `call` now follows it with a
    correct invocation. When the tool's schema is available we fill the required
    arguments in, so the line is directly runnable; otherwise we fall back to the
    generic shape plus the `inspect` pointer. The JSON is wrapped in single quotes,
    matching every other `call` example in this CLI — both POSIX shells and
    PowerShell keep the inner double quotes literal inside single quotes.
    """
    example_args = '{"arg":"value"}'
    if server and tool:
        try:
            info = manifest_mod.inspect_tool(server, tool)
        except Exception:
            info = None
        schema = (info or {}).get("inputSchema") or {}
        if schema.get("required"):
            example_args = json.dumps(_schema_args_skeleton(schema), ensure_ascii=False)

    lines = []
    if server and tool:
        lines.append(f"  Correct form: mcptoon call {server} {tool} '{example_args}'")
    else:
        lines.append(f"  Correct form: mcptoon call <server> <tool> '{example_args}'")
    if server and tool:
        lines.append(f"  See required args: mcptoon inspect {server} {tool}")
    else:
        lines.append("  See required args: mcptoon inspect <server> <tool>")
    return lines


def _cached_tool_schema(server, tool):
    """A tool's `inputSchema` from the on-disk cache, or {} when not cached.

    Cache-only on purpose: callers use this to *add* a hint to an otherwise-fine
    command, and must never spawn a server (or a second one) to do it. An uncached
    server simply yields no hint.
    """
    if not (server and tool):
        return {}
    try:
        from . import cache as _cache
        cached, _age = _cache.get_cached_tools_any_age(server)
    except Exception:
        return {}
    if not cached:
        return {}
    for t in cached:
        if isinstance(t, dict) and t.get("name") == tool:
            return t.get("inputSchema") or {}
    return {}


def _missing_required_args(server, tool, args):
    """Required arguments the caller left out, from the CACHED tool schema.

    A tool that is *called* with a required argument missing fails at the server
    in its own words — the echo test server dies with `KeyError: 'b'`, a real
    server returns its own validation text — and none of that names the argument
    in a way the user can act on. When the schema is already cached we can name
    the missing argument *before* the call. Deliberately cache-only (the same
    offline rule `policy set`/`toggle` use): a `call` must never spawn a second
    server just to pre-check its arguments, and an uncached server is never
    blocked by a guess. Returns [] when the schema is not cached.
    """
    schema = _cached_tool_schema(server, tool)
    required = schema.get("required") or []
    if not required:
        return []
    given = set(args.keys()) if isinstance(args, dict) else set()
    return [name for name in required if name not in given]


def _warn_missing_args(server, tool, args):
    """Print a one-line warning for required args the caller omitted (stderr).

    A warning, not a refusal: the server is the authority on what it accepts, and
    a schema that over-declares `required` would otherwise block a call that would
    have worked. But a call that is *going* to fail at the server should say why
    up front, in the argument's own name, instead of surfacing a downstream
    `KeyError` or a server-specific validation message. Silent when the schema is
    not cached or nothing is missing.
    """
    missing = _missing_required_args(server, tool, args)
    if not missing:
        return
    names = ", ".join(missing)
    hint = f"  See required args: mcptoon inspect {server} {tool}" if server \
        else "  See required args: mcptoon inspect <server> <tool>"
    _err(f"Warning: missing required argument(s) for {tool}: {names}")
    _err(hint)


def _read_stdin_text():
    """Read a `--stdin` payload as UTF-8 instead of as the console code page.

    Windows binds ``sys.stdin`` to the active code page (cp936 on a Chinese UI, cp1252
    elsewhere), so a JSON argument containing non-ASCII is silently re-decoded on the way
    in and the tool sends mojibake that no client asked for. `demo_server.py` already
    reconfigures its stdio for exactly this reason; the CLI's two `--stdin` readers were
    missed. Read the bytes and decode deliberately: UTF-8 first, because that is what
    every MCP client and `--stdin` example produces, falling back to the stream's own
    encoding so a legacy console-piped payload still arrives unchanged.
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()          # StringIO under tests, or a replaced stream
    raw = buffer.read()
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(sys.stdin.encoding or "utf-8", errors="replace")


def _cmd_call(rest, fmt, head_n, max_chars, full, use_stdin=False, fallback_json=False):
    """Call a tool."""
    # Check for --envelope mode (complete MCP result envelope, new-protocol servers)
    return_envelope = "--envelope" in rest
    if return_envelope:
        rest = [a for a in rest if a != "--envelope"]

    # Check for --input-responses '<json>' (MCP 2026-07-28 MRTR retry)
    input_responses = None
    request_state = None
    for i, a in enumerate(rest):
        if a == "--input-responses" and i + 1 < len(rest):
            try:
                input_responses = json.loads(rest[i + 1])
            except json.JSONDecodeError as e:
                print(f"Error parsing --input-responses JSON: {e}", file=sys.stderr)
                sys.exit(1)
            rest = rest[:i] + rest[i + 2:]
            break

    # Check for --request-state '<token>' (MCP 2026-07-28 MRTR correlation)
    for i, a in enumerate(rest):
        if a == "--request-state" and i + 1 < len(rest):
            request_state = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
            break

    # `--destructive` is a call-level flag like the four above, so it is stripped
    # here with them. It used to be recognised only *after* the positionals were
    # read (`server = rest[0]`), so `mcptoon call --destructive <server> <tool>`
    # handed the flag in as the server name and died with UNKNOWN_SERVER, while
    # the identical flag *after* the positionals worked — the order sensitivity
    # in issue #37. Stripping before the length check below also means
    # `call --destructive <server>` now reports usage instead of reading the
    # server name as the tool name. `inspect` and `list` were never affected.
    is_destructive = "--destructive" in rest
    if is_destructive:
        rest = [a for a in rest if a != "--destructive"]

    # A JSON object given positionally AND --stdin are two answers to the same
    # question ("what are the arguments?"). --stdin silently won, so
    # `echo '{...A}' | mcptoon call s t '{...B}' --stdin` used A and threw B away
    # with no warning — a script's intended args vanished (reported 2026-10-17).
    # Refuse the ambiguity instead of picking one behind the user's back.
    if use_stdin and any(a.startswith("{") for a in rest):
        _err("Error: pass tool arguments either as a JSON argument or via --stdin, "
             "not both.")
        sys.exit(1)

    # Check for --auto mode
    is_auto = "--auto" in rest
    if is_auto:
        rest = [a for a in rest if a != "--auto"]
        if len(rest) < 1:
            _err("Usage: mcptoon call --auto <tool> [JSON_ARGS] [--destructive] [--stdin]")
            _err("")
            _err("Examples:")
            _err('  mcptoon call --auto search \'{"query":"AI"}\' --toon')
            _err('  mcptoon call --auto fetch \'{"url":"https://example.com"}\'')
            sys.exit(1)

        tool = rest[0]

        # Parse args (same logic as below)
        args = {}
        if use_stdin:
            stdin_data = _read_stdin_text()
            if stdin_data.strip():
                try:
                    args = json.loads(stdin_data)
                except json.JSONDecodeError as e:
                    print(f"Error parsing stdin JSON: {e}", file=sys.stderr)
                    sys.exit(1)
        else:
            for item in rest[1:]:
                if item.startswith("{"):
                    try:
                        args = json.loads(item)
                        break
                    except json.JSONDecodeError as e:
                        _err(f"Error parsing JSON args: {e}")
                        for line in _call_json_error_hint("", tool):
                            _err(line)
                        sys.exit(1)
                if "=" in item:
                    k, v = item.split("=", 1)
                    try:
                        v = json.loads(v)
                    except json.JSONDecodeError:
                        pass
                    args[k] = v

        from .router import call_tool_auto
        _warn_missing_args("", tool, args)
        result, _auto_server = call_tool_auto(tool, args, is_destructive=is_destructive,
                                              return_envelope=return_envelope,
                                              skip_poisoning_check=(fmt == "raw"),
                                              return_server=True)

        if is_error(result):
            err = result["_error"]
            print(f"Error [{err['code']}]: {err['message']}", file=sys.stderr)
            if result.get("suggestions"):
                servers_list = ", ".join(result["suggestions"])
                print(f"  Available on servers: {servers_list}", file=sys.stderr)
                print(f"  Try: mcptoon call <server> {tool} ...", file=sys.stderr)
            sys.exit(1)

        # Render with fallback-json if needed. Route through the SAME per-tool
        # policy path the explicit `call <server> <tool>` uses, and carry the
        # server/tool keys so a `policy set <tool> raw` is honoured and the smart
        # compressor's CCR handle keeps its `server:tool` identity.
        _render_result(result, _effective_fmt(_auto_server, tool, fmt),
                       head_n, max_chars, full, fallback_json,
                       server=_auto_server, tool=tool)
        # Machine receipt on stderr for every machine format (json AND toon), so a
        # --toon script gets the same numbers a --json one does; stdout stays pure.
        _emit_cli_receipt(_auto_server, tool, result, machine=(fmt in ("json", "toon")))
        if _tool_result_failed(result):
            sys.exit(1)
        return

    if len(rest) < 2:
        _err("Usage: mcptoon call <server> <tool> [JSON_ARGS] [--destructive] [--stdin] [--envelope] [--input-responses JSON] [--request-state TOKEN]")
        _err("       mcptoon call --auto <tool> [JSON_ARGS] [--destructive] [--stdin] [--envelope]")
        _err("")
        _err("Examples:")
        _err('  mcptoon call fetch fetch \'{"url":"https://example.com"}\' --toon')
        _err('  mcptoon call exa search \'{"query":"AI"}\' --json')
        _err('  mcptoon call --auto search \'{"query":"AI"}\'  # auto-find server')
        _err('  mcptoon call db query \'{"sql":"SELECT 1"}\' --envelope  # full MCP result envelope')
        _err("  mcptoon call db query '{}' --input-responses '{\"answer\": 42}' --request-state 'st-42'  # MRTR retry (2026-07-28)")
        _err('  echo \'{"huge":"payload"}\' | mcptoon call server tool --stdin --toon')
        sys.exit(1)

    server = rest[0]
    tool = rest[1]

    # Parse args
    args = {}

    if use_stdin:
        # Read JSON args from stdin (for large payloads >32767 chars)
        stdin_data = _read_stdin_text()
        if stdin_data.strip():
            try:
                args = json.loads(stdin_data)
            except json.JSONDecodeError as e:
                print(f"Error parsing stdin JSON: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        for item in rest[2:]:
            # Try JSON
            if item.startswith("{"):
                try:
                    args = json.loads(item)
                    break
                except json.JSONDecodeError as e:
                    _err(f"Error parsing JSON args: {e}")
                    for line in _call_json_error_hint(server, tool):
                        _err(line)
                    sys.exit(1)
            # key=value
            if "=" in item:
                k, v = item.split("=", 1)
                # Try to parse value as JSON
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    pass
                args[k] = v

    _warn_missing_args(server, tool, args)
    result = call_tool(server, tool, args, is_destructive=is_destructive,
                       return_envelope=return_envelope,
                       input_responses=input_responses,
                       request_state=request_state,
                       # `--raw` is the documented way past the safety screen — the
                       # CREDENTIAL_LEAK/TOOL_POISONING fix hint says so verbatim.
                       # It was never wired: `--raw` only set the *output* format, so
                       # the screen still blocked the result and the advertised escape
                       # hatch did nothing. A hint that names a flag the code does not
                       # read is worse than no hint — the user already failed once.
                       skip_poisoning_check=(fmt == "raw"))
    if is_error(result):
        err = result["_error"]
        print(f"Error [{err['code']}]: {err['message']}", file=sys.stderr)
        if err.get("retry"):
            print("  (retryable)", file=sys.stderr)
        # MRTR (MCP 2026-07-28): the tool asked for more input — show the
        # requests and how to answer them.
        if err["code"] == "INPUT_REQUIRED" and result.get("input_requests"):
            print("  The tool needs more input (multi round-trip request):", file=sys.stderr)
            for req in result["input_requests"]:
                name = req.get("method", "?") if isinstance(req, dict) else str(req)
                print(f"    - {name}", file=sys.stderr)
            state_hint = ""
            if result.get("request_state"):
                state_hint = f" --request-state '{result['request_state']}'"
            print(f'  Answer them and retry: mcptoon call ... --input-responses \'{{"method": "value"}}\'{state_hint}',
                  file=sys.stderr)
        # Fuzzy match suggestions for unknown tools
        if err["code"] == "UNKNOWN_TOOL" and result.get("suggestions"):
            print(f"Did you mean: {', '.join(result['suggestions'])}", file=sys.stderr)
        # Fix suggestions for common errors
        fix = _fix_suggestion(err["code"], server, tool)
        if fix:
            print(f"  Fix: {fix}", file=sys.stderr)
        sys.exit(1)

    _render_result(result, _effective_fmt(server, tool, fmt),
                   head_n, max_chars, full, fallback_json, server=server, tool=tool)
    # Machine receipt on stderr for json AND toon; human prose otherwise.
    _emit_cli_receipt(server, tool, result, machine=(fmt in ("json", "toon")))
    if _tool_result_failed(result):
        sys.exit(1)


def _cmd_exec(rest, fmt, full):
    """Run code so only its stdout reaches the context.

    Usage:
        mcptoon exec <lang> "<code>"
        mcptoon exec <lang> --file <path>
        mcptoon exec <lang> --file -            # read the program from stdin
        mcptoon exec --langs                    # what this machine can run

    Options:
        --file <path>    Run a script file instead of inline code ("-" = stdin)
        --timeout <s>    Kill the child after this many seconds (default 120)
        --max-chars <n>  Bytes of stdout the context may see (default 8192;
                         over that, head/tail + a retrieve handle)
        --langs          List runnable languages and exit
        --json           Machine-readable result object
        --full           Show all of stdout, even over budget (still retrievable)

    Only stdout is the answer. stderr comes back as a short tail because a
    traceback is diagnostic, not output. A non-zero exit sets exit code 1.

    The name says sandbox but it is a *context* sandbox: the child has your
    shell's filesystem and network access. What it keeps out is the data.
    """
    from . import exec_sandbox as _exec

    if "--langs" in rest:
        langs = _exec.languages()
        if fmt == "json":
            print(json.dumps(langs, ensure_ascii=False, indent=2))
        else:
            print("Runtimes available on this machine:")
            for item in langs:
                print(f"  {item['name']:<12} {item['exe']}")
        return

    file_path = None
    timeout = _exec.DEFAULT_TIMEOUT
    max_output = _exec.DEFAULT_MAX_OUTPUT
    code = None
    lang = None

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--file" and i + 1 < len(rest):
            file_path = rest[i + 1]
            i += 2
        elif a == "--timeout" and i + 1 < len(rest):
            try:
                timeout = int(rest[i + 1])
            except ValueError:
                _err(f"Error: --timeout expects an integer number of seconds, got {rest[i + 1]!r}")
                sys.exit(1)
            i += 2
        elif a == "--max-chars" and i + 1 < len(rest):
            try:
                max_output = int(rest[i + 1])
            except ValueError:
                _err(f"Error: --max-chars expects an integer, got {rest[i + 1]!r}")
                sys.exit(1)
            i += 2
        elif a == "--code" and i + 1 < len(rest):
            code = rest[i + 1]
            i += 2
        elif a == "--json":
            i += 1  # already captured in fmt upstream
        elif a.startswith("-") and a not in ("-",):
            _err(f"Error: unknown option for exec: {a}")
            _err("Run 'mcptoon exec --help' for usage.")
            sys.exit(1)
        elif lang is None:
            lang = a
            i += 1
        elif code is None and file_path is None:
            code = a
            i += 1
        else:
            _err(f"Error: unexpected extra argument: {a!r}")
            _err("Run 'mcptoon exec --help' for usage.")
            sys.exit(1)

    if lang is None:
        _err("Usage: mcptoon exec <lang> \"<code>\"  |  mcptoon exec <lang> --file <path>")
        _err("       mcptoon exec --langs")
        sys.exit(1)

    if file_path == "-":
        file_path = None
        code = _read_stdin_text()

    try:
        result = _exec.run(lang, code, file_path=file_path,
                           timeout=timeout, max_output=(0 if full else max_output))
    except _exec.ExecError as exc:
        _err(f"Error: {exc}")
        sys.exit(1)

    if fmt == "json":
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.truncated:
            if result.handle:
                _err(f"[exec] stdout was {result.stdout_bytes} bytes; the rest is at "
                     f"mcptoon retrieve {result.handle}")
            else:
                _err(f"[exec] stdout was {result.stdout_bytes} bytes; it could not be "
                     f"stored for retrieval (store unavailable)")
        if result.stderr_tail:
            _err("--- stderr (tail) ---")
            _err(result.stderr_tail)
        if result.failure:
            _err(f"[exec] {result.failure}")
        _err(f"[exec] {result.lang} · {result.elapsed_ms} ms · "
             f"exit {result.exit_code}")

    if not result.ok:
        sys.exit(1)


def _render_result(result, fmt, head_n, max_chars, full, fallback_json=False,
                   server="", tool=""):
    """Render tool call result with optional fallback-json.

    If fallback_json is True and the chosen format (toon/mcptoon/slim) fails
    to encode the result, automatically fall back to JSON output.

    ``smart`` goes through the shared compressor pipeline so the CLI and the MCP
    bridge agree: the result is compressed *and* its original is stored, with a
    retrieve handle in the tail — otherwise a CLI caller would see a lossy
    summary with no way back.
    """
    if fmt == "smart":
        from . import compressor as _compressor
        text, _stats = _compressor.compress_with_ccr(result, server=server, tool=tool)
        if text is not None:
            print(text)
            return
        fmt = "json"  # nothing to compress — show it whole rather than a stub

    if not fallback_json or fmt in ("json", "auto", "raw"):
        print(output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
        return

    # Try the requested format, fall back to JSON on error
    try:
        rendered = output.render(result, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full)
        # Check for encoding issues
        if rendered and "Error" in rendered[:50] and "encode" in rendered.lower():
            raise ValueError(f"Encoding failed with {fmt}")
        print(rendered)
    except (ValueError, TypeError, KeyError) as e:
        print(f"# fallback-json: {fmt} encoding failed ({e}), falling back to JSON", file=sys.stderr)
        print(output.render(result, fmt="json", head_n=head_n, max_chars=max_chars, full=full))


def _tool_result_failed(result) -> bool:
    """True when a tool *ran* but reported failure (the MCP ``isError: true`` case).

    Distinct from ``is_error`` (a routing/protocol failure envelope). A tool that
    executed and returned an error comes back from the client as
    ``{"error": True, "message": ...}`` — or, under ``--envelope``, as the raw MCP
    result ``{"isError": true, "content": [...]}``. ``call`` used to print either and
    exit 0, so ``mcptoon call ... && next`` ran the next step on a failed tool — a
    script could not tell success from failure by exit code (reported 2026-10-17).
    The ``"message"`` requirement keeps a legitimate tool payload that merely has an
    ``"error"`` field from being misread as a failure.
    """
    if not isinstance(result, dict):
        return False
    if result.get("error") is True and "message" in result:
        return True
    # --envelope returns the full MCP result, which carries `isError` instead.
    if result.get("isError") is True:
        return True
    return False


# ═══════════════════════════════════════════════════
# Policy command — per-tool compression overrides
# ═══════════════════════════════════════════════════

def _effective_fmt(server, tool, fmt):
    """Per-tool compression policy applies only when no format flag was given.

    Explicit flags (--json/--toon/...) always win; the policy is the
    *default* for tools whose results need special handling.
    """
    if fmt != "auto":
        return fmt
    try:
        return cfg.resolve_output_format(server, tool, fmt)
    except Exception:
        return fmt


def _cmd_policy(rest, fmt, head_n=0, max_chars=0, full=False):
    """Per-tool compression policy: pin how a tool's results are compressed.

    Usage:
        mcptoon policy                                list configured policies
        mcptoon policy set <server> <tool> <policy>   pin one tool's format
        mcptoon policy set <server> * <policy>        server-wide default
        mcptoon policy clear <server> <tool>          remove a policy

    Policies:
        raw|json              never compress (images, base64, binary)
        toon|compact|slim     force this format regardless of the default
        smart                 structure-aware compression (keep keys, cut payload)
        auto                  remove the policy (back to default)
    """
    if not rest or rest[0] in ("--list", "list"):
        policies = cfg.list_policies()
        # `--json` gives scripts the policy map as data. It used to print human
        # text regardless of format (reported 2026-10-18).
        if fmt == "json":
            print(output.render(dict(policies or {}), fmt="json", head_n=head_n,
                                max_chars=max_chars, full=full))
            return
        if not policies:
            print("No compression policies configured - default behaviour applies everywhere.")
            print("")
            print("Set one:")
            print("  mcptoon policy set <server> <tool> raw   # never compress (images, base64)")
            print("  mcptoon policy set <server> <tool> toon  # always render as TOON")
            print("  mcptoon policy set <server> <tool> smart # structure-aware compression")
            return
        print("Per-tool compression policies:")
        for key, policy in policies.items():
            print(f"  {key:40s} -> {policy}")
        return

    sub = rest[0]
    if sub == "set":
        if len(rest) < 4:
            _err("Usage: mcptoon policy set <server> <tool-or-*> <raw|json|auto|toon|compact|slim|smart>")
            sys.exit(1)
        server, tool, policy = rest[1], rest[2], rest[3]
        # A policy names a server and a tool; writing one for a typo'd server or
        # tool silently stored a dead entry that never matched anything, and
        # `mcptoon policy` then showed a rule the user could not reconcile with
        # any real server (reported 2026-10-17 — `policy set zzz zzz raw` exited
        # 0 and persisted). Validate against config + the tool cache. A tool check
        # is only made when the server has a cached manifest; otherwise we cannot
        # verify offline and accept it (a slow fetch to police a config write is
        # not worth it), printing a note instead.
        servers = cfg.load_config()
        if server not in servers:
            _err(f"Server '{server}' not found. Available: {', '.join(sorted(servers.keys())) or '(none)'}")
            sys.exit(1)
        if tool != "*":
            from . import cache as _cache
            cached, _age = _cache.get_cached_tools_any_age(server)
            if cached is not None:
                names = {t.get("name") for t in cached if isinstance(t, dict) and "error" not in t}
                if tool not in names:
                    _err(f"Tool '{tool}' not found on '{server}'.")
                    _err(f"See its tools: mcptoon inspect {server}")
                    sys.exit(1)
        if cfg.set_compression_policy(server, tool, policy):
            if policy == "auto":
                print(f"Cleared: {server}:{tool} uses the default behaviour again.")
            else:
                meaning = ("never compressed" if policy in ("raw", "json")
                           else f"always rendered as {policy}")
                print(f"Policy set: {server}:{tool} -> {policy} ({meaning})")
                # Say *what this applies to*, because `tool` can be the wildcard
                # `*`. "Policy set: exa:* -> raw" leaves a first-time user unsure
                # whether that covers every current tool or every future one too;
                # name the scope in plain words.
                if tool == "*":
                    print(f"  Scope: every tool on '{server}' (current and future).")
                else:
                    print(f"  Scope: only '{server}:{tool}'.")
        else:
            _err(f"Unknown policy '{policy}'. Valid: {', '.join(cfg.VALID_POLICIES)}")
            sys.exit(1)
    elif sub == "clear":
        if len(rest) < 3:
            _err("Usage: mcptoon policy clear <server> <tool-or-*>")
            sys.exit(1)
        key = f"{rest[1]}:{rest[2]}"
        # `policy clear` printed "Cleared: X uses the default behaviour" and exited
        # 0 even when no policy existed for X — a false report of an action that
        # never happened, so `mcptoon policy clear s t && echo done` lied. A miss
        # is an error here, matching `remove` / `update` (reported 2026-10-18).
        if key not in cfg.list_policies():
            _err(f"No policy set for {key} — already using the default behaviour.")
            sys.exit(1)
        cfg.set_compression_policy(rest[1], rest[2], None)
        print(f"Cleared: {key} uses the default behaviour.")
    else:
        _err(f"Unknown subcommand '{sub}'. Use: list | set | clear")
        sys.exit(1)


# ═══════════════════════════════════════════════════
# Search command
# ═══════════════════════════════════════════════════

def _placeholder_for_type(ptype):
    """A sample value for one argument type, used to build a copyable call.

    Only the *shape* matters here — the point is that `mcptoon call ... '{"path":
    "..."}'` is syntactically valid so the user can paste and edit it. A number is
    `0` and a boolean is `false` because those are valid JSON; a string is `"..."`
    so it is obvious what to replace.
    """
    if ptype in ("number", "integer", "int", "float"):
        return 0
    if ptype == "boolean":
        return False
    if ptype == "array":
        return []
    if ptype == "object":
        return {}
    return "..."


def _call_example(server, name, params):
    """Build a copy-pasteable `mcptoon call` line from a search hit's params.

    `search` used to stop at `params: message:string*`, leaving the user to
    hand-assemble the JSON arguments and to remember which of them were required
    (the `*` marker is easy to miss). This renders the required arguments as a
    JSON skeleton so the next step is a copy, not a construction. Optional
    arguments are omitted on purpose: the goal is the smallest *valid* call, not
    an exhaustive template. Returns "" when nothing is required (a `{}` call is
    still shown, because "this tool takes no arguments" is useful to see).
    """
    example = {}
    for part in (params or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        pname, ptype = part.split(":", 1)
        if not ptype.endswith("*"):
            continue  # only required params are needed for a valid call
        example[pname] = _placeholder_for_type(ptype[:-1])
    args = json.dumps(example, ensure_ascii=False)
    return f"  → mcptoon call {server} {name} '{args}'"


def _schema_args_skeleton(schema):
    """A minimal JSON-args dict from a tool's `inputSchema`.

    Only the `required` list is filled — the goal is the smallest *valid* call,
    not an exhaustive template — and each value is a placeholder of the right JSON
    type so the printed example parses. Shared by the `inspect` call hint and the
    `call` JSON-error hint so both build the skeleton the same way (one source of
    truth; the two used to be written twice).
    """
    schema = schema or {}
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    example = {}
    for pname in required:
        ptype = (props.get(pname) or {}).get("type", "string")
        if isinstance(ptype, list):
            ptype = ptype[0] if ptype else "string"
        example[pname] = _placeholder_for_type(ptype)
    return example


def _call_example_from_schema(server, name, info):
    """A copyable `mcptoon call` line built from a tool's full schema.

    `inspect <server> <tool>` prints the schema and then stops; the reader still
    has to turn `required`/`properties` into an argument object. This closes that
    last gap the same way `search` does — the schema is already in hand here, so
    there is no reason to make the user reassemble it.
    """
    schema = (info or {}).get("inputSchema") or {}
    args = json.dumps(_schema_args_skeleton(schema), ensure_ascii=False)
    return f"  → mcptoon call {server} {name} '{args}'"


def _cmd_search(rest, fmt, head_n, max_chars, full):
    """Search tools across all configured servers.

    Usage:
        mcptoon search <query>          # search by keyword
        mcptoon search "git commit"     # multi-word query
        mcptoon search web --slim       # slim format output
        mcptoon search fetch --json     # JSON output
        mcptoon search fetch --head 5   # limit to 5 results
    """
    if not rest:
        print("Usage: mcptoon search <query>")
        print("")
        print("Examples:")
        print('  mcptoon search "search web"')
        print("  mcptoon search git")
        print("  mcptoon search fetch --slim")
        print("  mcptoon search url --json --head 5")
        sys.exit(1)

    query = " ".join(rest)

    from . import manifest as manifest_mod

    results = manifest_mod.search_tools(query, limit=20)

    if not results:
        # A machine consumer (`mcptoon search q --json | jq`) must always get
        # parseable output. The empty branch printed human text + tips for EVERY
        # format, so a zero-match `--json` emitted prose and the pipe crashed
        # (reported 2026-10-18). Emit an empty structure for machine formats and
        # keep the friendly tips for humans.
        if fmt in ("json", "toon", "slim", "compact"):
            print(output.render([], fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
            sys.exit(0)
        print(f"No tools found matching '{query}'.")
        print("")
        print("Tips:")
        print("  - Check if your servers are configured: mcptoon list")
        print("  - See all available tools: mcptoon manifest")
        # `search` only looks at servers you already have; a miss is the moment a
        # new user would give up. Point them at the live registries instead of
        # leaving them with a dead end (issue: the 17,000+ path was discoverable
        # only if you already knew `install --search`).
        print(f"  - Not installed yet? Search the live registries "
              f"(17,000+ MCP servers): mcptoon install --search '{query}'")
        sys.exit(0)

    # `--head N` caps the result list for every output mode. It used to be honoured
    # only by the json/toon renderers; slim/compact/human ignored it and printed all
    # 20 hits, so `search file --head 5` (documented "limit to 5 results") showed
    # 20 (reported 2026-10-17). Cap once, up front, so the count line and every
    # format agree.
    total = len(results)
    if head_n and head_n > 0:
        results = results[:head_n]

    if fmt == "slim":
        # Ultra-compact: server/tool_name|params
        lines = []
        for r in results:
            lines.append(f"{r['server']}/{r['name']}|{r['params']}|score:{r['score']}")
        print("\n".join(lines))
    elif fmt == "compact":
        # Names only
        names = [f"{r['server']}/{r['name']}" for r in results]
        print(" ".join(names))
    elif fmt == "json":
        # Add the copyable next step as data too, so an agent driving the CLI (not
        # a human reading a terminal) can reach the call without reassembling the
        # JSON from `params`. It is an extra key, so existing consumers that read
        # server/name/description/params/score are unaffected.
        rows = [{**r, "call_hint": _call_example(r["server"], r["name"], r["params"]).strip()}
                for r in results]
        print(output.render(rows, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
    elif fmt == "toon":
        print(output.render(results, fmt="toon", head_n=head_n, max_chars=max_chars, full=full))
    else:
        # Human-readable
        shown = f"{len(results)} of {total}" if len(results) < total else f"{len(results)}"
        print(f"Found {shown} tool(s) matching '{query}':")
        print("")
        for r in results:
            server = r["server"]
            name = r["name"]
            desc = r["description"]
            params = r["params"]
            score = r["score"]
            print(f"  {server}/{name}  (score: {score})")
            if desc:
                print(f"    {desc}")
            if params:
                print(f"    params: {params}")
            # The copyable next step. `search` used to stop at `params:` and leave
            # the user to assemble the call by hand (and to spot the `*` that marks
            # a required argument). One ready-to-edit line closes that gap.
            print(_call_example(server, name, params))
            print("")


def _cmd_select(rest, fmt="auto", head_n=0, max_chars=0, full=False):
    """Pick the few tools worth showing an agent for a task.

    Why this is separate from `search`: `search` answers "which tools match this
    keyword?" and returns up to 20. `select` answers the question that actually
    decides whether an agent succeeds — "out of everything installed, which 3
    should I look at for *this* task?" — because past roughly 40-50 tools the
    model's choice degrades even when the catalog is compressed.

    The engine is configurable (`mcptoon config set select.engine lexical|command`).
    `lexical` is the built-in pure-stdlib scorer. `command` shells out to a ranker
    the user supplies, so a machine that already runs embeddings can rank
    semantically without mcptoon taking a dependency. Whichever engine answers is
    named in the output, including when a configured `command` engine failed and
    the built-in one took over — a silent fallback would hide a broken ranker.

    Usage:
        mcptoon select "find the cheapest flight to Tokyo"
        mcptoon select "..." --top 3 --json
        mcptoon select --engine            # show which engine is configured
    """
    if "--engine" in rest:
        from .config import load_settings
        s = load_settings()
        print(f"select.engine  = {s.get('select.engine', 'lexical')}")
        if s.get("select.engine") == "command":
            cmd = s.get("select.command", "")
            print(f"select.command = {cmd or '(not set — lexical will be used)'}")
        return

    top = 3
    args = list(rest)
    if "--top" in args:
        i = args.index("--top")
        if i + 1 < len(args):
            try:
                top = max(1, int(args[i + 1]))
            except ValueError:
                # A non-integer was swallowed, so `--top abc` silently fell back to
                # the default 3 and a scripted `--top $N` with a bad value looked
                # like it worked (reported 2026-10-18). Fail loudly, like --head.
                _err(f"Error: --top needs an integer, got {args[i + 1]!r}")
                sys.exit(1)
            del args[i:i + 2]
        else:
            del args[i]
    args = [a for a in args if a not in ("--json", "--slim", "--compact", "--toon")]

    if not args:
        print("Usage: mcptoon select <task description>")
        print("")
        print('  mcptoon select "find the cheapest flight to Tokyo"')
        print('  mcptoon select "..." --top 5 --json')
        print("  mcptoon select --engine     # show the configured engine")
        sys.exit(1)

    query = " ".join(args)

    from . import manifest as manifest_mod

    # Flatten the manifest into the shape both engines rank.
    manifest = manifest_mod.get_manifest(use_cache=True)
    flat = []
    for server, tools in sorted(manifest.items()):
        for t in tools:
            if not isinstance(t, dict) or "error" in t:
                continue
            flat.append({"server": server, "name": t.get("name", ""),
                         "description": t.get("description", "")})

    if not flat:
        if fmt in ("json", "toon", "slim", "compact"):
            print(output.render([], fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
            sys.exit(0)
        print("No tools to choose from.")
        print("  - Check your servers are configured: mcptoon list")
        sys.exit(0)

    ranked, engine = manifest_mod.rank_tools(query, flat)
    ranked = ranked[:top]
    # `--head N` caps how many of the top picks are shown in the human output.
    # It used to be ignored here (only the json branch forwarded it to the
    # renderer), so `select ... --head 1` still printed all `--top` results
    # (reported 2026-10-18). Cap once, up front, so both branches agree.
    if head_n and head_n > 0:
        ranked = ranked[:head_n]

    if not ranked:
        # The engine's contract is "always succeeds, may return []" (manifest.py).
        # An empty ranking is a normal zero-match, not an impossible state — the
        # old code went straight to `ranked[0]` and raised IndexError with a
        # traceback. Mirror `search`'s empty branch (same tips, exit 0) and add
        # the registry exit, because `select` is the "help me pick" command and a
        # miss is exactly when a user needs to know they can install more.
        #
        # Machine formats must stay parseable: a zero-match `--json` used to emit
        # prose and break `... | jq` (reported 2026-10-18). Emit an empty
        # structure for machine formats, keep the tips for humans.
        if fmt in ("json", "toon", "slim", "compact"):
            print(output.render([], fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
            sys.exit(0)
        print(f"No tools found matching '{query}'.")
        print("")
        print("Tips:")
        print("  - Check your servers are configured: mcptoon list")
        print("  - See all available tools: mcptoon manifest")
        print(f"  - Not installed yet? Search the live registries "
              f"(17,000+ MCP servers): mcptoon install --search '{query}'")
        sys.exit(0)

    # Look the description back up for display; the engines only carry the keys
    # they need to score, and inventing a description here would be a second
    # source of truth for the same tool.
    by_key = {(t["server"], t["name"]): t for t in flat}

    if fmt == "json":
        rows = [{**r, "description": by_key.get((r["server"], r["name"]), {}).get("description", "")}
                for r in ranked]
        print(output.render(rows, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
        return

    print(f"Top {len(ranked)} tool(s) for: {query}")
    print(f"  engine: {engine}")
    print("")
    for r in ranked:
        desc = by_key.get((r["server"], r["name"]), {}).get("description", "")
        print(f"  {r['server']}/{r['name']}  (score: {round(r['score'], 3)})")
        if desc:
            print(f"    {desc[:120]}")
    print("")
    print(f"  Inspect one: mcptoon inspect {ranked[0]['server']} {ranked[0]['name']}")
    # `select` told the user which tool to inspect but not how to call it; the
    # top pick's schema is one cache lookup away, so show the call line too (same
    # shape as `search`). Cache-only and best-effort: a ranker payload without a
    # cached schema must not crash the whole command or spawn a server.
    try:
        schema = _cached_tool_schema(ranked[0]["server"], ranked[0]["name"])
        if schema:
            args = json.dumps(_schema_args_skeleton(schema), ensure_ascii=False)
            print(f"  → mcptoon call {ranked[0]['server']} {ranked[0]['name']} '{args}'")
    except Exception:
        pass


def _cmd_quickstart(rest, fmt="auto"):
    """One-command onboarding: discover + configure + show tools.

    This is the "aha moment" command. Designed for first-time users.
    Replaces the old 4-step flow (init → add → manifest → call) with one command.

    Usage:
        mcptoon quickstart              # discover + configure + sync + show slim manifest
        mcptoon qs                      # alias
        mcptoon quickstart --http URL    # include HTTP MCP endpoint
        mcptoon quickstart --dry        # don't write config, just show
        mcptoon quickstart --no-self    # sync servers only, don't register the gateway
        mcptoon quickstart --takeover   # route servers through the gateway (scripted; no prompt)
    """
    is_dry = "--dry" in rest
    include_self = "--no-self" not in rest
    http_url = ""
    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    from . import discover as disc

    print("mcptoon quickstart — discovering your MCP servers...")
    print("")

    # Step 1: Auto-discover
    result = disc.auto_discover()

    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            # `tools_count` is None when `tools/list` could not be read (see
            # `probe_http_endpoint`); "0 tools" would be a different, wrong claim.
            if probe_info.get("tools_known", True):
                tool_count = probe_info.get("tools_count") or 0
                result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} ({tool_count} tools)"
            else:
                result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} (reachable; tool list unreadable)"
        else:
            print(f"  ! {http_url} did not answer an MCP initialize — skipping it.")

    if result.count == 0:
        # Discovery reads *other* agents' configs (Claude Desktop, Cursor, env, …),
        # never mcptoon's own. So a second `quickstart` on a machine that already
        # manages servers found nothing new and said "No MCP servers found on this
        # machine" — while `mcptoon list` printed them (reproduced 2026-10-02). Say
        # what is true: you already have servers, here is where to see them.
        already = cfg.list_servers()
        if already:
            n = len(already)
            print(f"  Nothing new to discover — you already have {n} "
                  f"server{'s' if n != 1 else ''} configured.")
            print("")
            print("  See them:      mcptoon list")
            print("  Their cost:    mcptoon status")
            print("  Push to agents: mcptoon sync --self")
            print("")
            print("  Add another:   mcptoon add <name> --stdio npx -y <package>")
            print("                 mcptoon install --search <query>   # search 17,000+")
            return
        print("  No MCP servers found on this machine.")
        print("")
        print("  Don't worry — here's how to get started:")
        print("")
        print("    # Add the built-in demo server (zero config, no Node, no network):")
        print("    mcptoon add demo --stdio python -m mcptoon demo-server")
        print("")
        print("    # Then see your tools:")
        print("    mcptoon manifest --slim")
        print("")
        print("    # Call a tool:")
        print("    mcptoon call demo echo_message '{\"message\":\"hi\"}'")
        print("")
        print("    # Want the reference 'everything' server instead? It needs Node, and in")
        print("    # some minimal Python images it lists zero tools:")
        print("    #   mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything")
        print("")
        # The takeover warning at the end of a successful run never fires here
        # (there is nothing to take over), so on this path the token story would
        # otherwise never be told at all — the one thing a new user is deciding
        # about. One line, pointing at the command that shows the real numbers
        # (2026-09-26 polish pass).
        print("  Once you add servers: routing them through mcptoon is what saves")
        print("  tokens (not just listing them). `mcptoon status` shows both numbers.")
        print("")
        print("  Or browse MCP servers:")
        print("    https://github.com/modelcontextprotocol/servers")
        return

    # Step 2: Write config (unless dry)
    if not is_dry:
        # Gate on EITHER config format. `cfg.CONFIG_FILE.exists()` saw only JSON,
        # so a user whose servers lived in `config.toml` fell into the else branch
        # below and `save_config` rewrote the TOML file with just the discovered
        # servers — silently deleting their list (2026-10-02).
        if cfg.has_config_file():
            added, skipped, _ = cfg.merge_servers(result.servers, overwrite=False)
            if added > 0:
                print(f"  ✓ {added} new server(s) added to config")
            if skipped > 0:
                print(f"  = {skipped} existing server(s) kept (use 'mcptoon init --auto --force' to overwrite)")
        else:
            cfg.save_config(result.servers)
            print(f"  ✓ Config created: {cfg.CONFIG_FILE}")
    else:
        # `--dry` means "don't change your server list or your agents", not "touch
        # nothing on disk": the once-per-machine self-heal (copy our skill into the
        # agent views, build the skill index) runs before command dispatch, so it
        # still writes. Saying just "config not written" was technically true of the
        # server config and misleading about everything else (2026-09-26 polish pass).
        print("  (--dry mode: no config written, no agent touched)")
        print("  (the one-time skill install/index still runs — it is an addition, "
              "not a change to your servers)")

    print("")

    # Step 3: Sync into every detected agent — including mcptoon itself.
    #
    # This is the step that turns "installed" into "visible". Without it the
    # gateway's `mcptoon serve` entry is never written anywhere, so the MCP
    # `instructions` handshake that announces mcptoon to the model never fires
    # and the install leaves no trace. Registering it here (and in `sync`) is
    # what a user actually notices.
    if not is_dry:
        from .sync import sync_to_all, format_sync_report
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  Registering mcptoon in your agents...")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        try:
            results = sync_to_all(dry_run=False, include_self=include_self)
            print(format_sync_report(results, dry_run=False))
            written = sum(1 for r in results if r.get("written"))
            if written and include_self:
                # Name the hosts, not just "your agents": "installed" is only
                # believable when the user can see *which* app now carries mcptoon,
                # and the next line tells them where to watch it work.
                names = [r.get("agent_name") or r.get("agent")
                         for r in results if r.get("written")]
                names = [n for n in names if n]
                shown = ", ".join(names[:4]) + (" …" if len(names) > 4 else "")
                print("")
                print(f"  ✓ {shown} can now see mcptoon itself (`mcptoon serve`).")
                print("    As it routes tools and skills for them, `mcptoon activity`"
                      " records every call.")
                # "Installed" is only half the story; the other half is "you can
                # SEE it working". Claude Code is the one host with a status bar
                # mcptoon can wire automatically — name it here, at the moment the
                # user is deciding whether this tool is real, so the badge is not
                # a feature they only discover by reading the docs.
                print("    Want the savings badge always visible? "
                      "`mcptoon statusline --install` (Claude Code).")
            elif written:
                print("")
                print("  ✓ Your agents can now see mcptoon itself (`mcptoon serve`).")
        except Exception as e:  # never let a sync failure abort onboarding
            print(f"  Could not sync to agents yet: {e}")
            print("  Run 'mcptoon sync --self' when ready")
        print("")

    # Step 4: Show summary
    print(result.summary())

    # Step 4b: Build the skill index now, so the catalog is answerable the moment
    # onboarding ends. `resolve` would build it lazily on first use anyway, but
    # doing it here means the very next command — including one an agent runs —
    # has a catalog to answer from, and it puts the skill count in front of the
    # user instead of leaving it a surprise. Best-effort: a machine with no skill
    # roots is not an onboarding failure.
    if not is_dry:
        try:
            from . import skills as skills_mod
            if skills_mod.ensure_index():
                n_skills = len(skills_mod.load_index().get("skills") or [])
                print(f"  ✓ Skill catalog indexed: {n_skills} skill(s) routable "
                      f"via `mcptoon skills resolve`")
            # Step 4c: give the agents mcptoon's own skill. Indexing makes the
            # catalog answerable; this is what lets the *agent* learn what the
            # defaults are and how to switch presets when a tool panel looks
            # empty. Best-effort, and it only ever writes our own file — a missing
            # entry is created, and our own stale copy is refreshed; an entry that
            # declares a different `name` (another manager's, or a user's) is left
            # alone.
            installed = skills_mod.install_self()
            wrote = [r for r in installed if r.get("written")]
            refreshed = [r for r in wrote if r.get("updated")]
            fresh = len(wrote) - len(refreshed)
            if fresh:
                print(f"  ✓ mcptoon skill installed for {fresh} agent folder(s) — "
                      f"they can read what the defaults are")
            if refreshed:
                print(f"  ✓ mcptoon skill updated for {len(refreshed)} agent folder(s) — "
                      f"they now read the current defaults")
            if not installed:
                print("  · no known agent skill folder here yet — run "
                      "`mcptoon skills install-self --view <your agent's skills folder>` "
                      "to place it for an agent mcptoon does not know about")
            # Record the same marker the first-run self-heal uses, so onboarding
            # does not leave a machine that heals all over again on the next
            # command. Best-effort like the rest of this block.
            try:
                from . import config as _cfg
                _cfg.mark_selfheal_done(skills_mod.self_fingerprint())
            except Exception:
                pass
        except Exception:
            pass

    # Step 5: The "aha moment" — show slim manifest
    tool_count = None
    unreachable = 0
    if not is_dry:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  Your tools (names only \u2014 the default manifest tier):")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        try:
            manifest = manifest_mod.get_manifest(use_cache=False)
            tool_count = _manifest_tool_count(manifest)
            unreachable = _manifest_unreachable_count(manifest)
            slim_output = manifest_mod.format_manifest(manifest, full=False)
            if slim_output.strip():
                print(slim_output)
            else:
                print("  (tools will appear after servers are started)")
        except Exception as e:
            print(f"  Could not fetch tools yet: {e}")
            print("  Run 'mcptoon manifest --slim' after servers are started")

    print("")
    if not is_dry:
        _quickstart_celebration(tool_count, result.count, unreachable)
        # The one moment the token tradeoff is legible: the servers were just
        # registered, the user can still say no for free, and the warning is about
        # a number they care about. Off for --dry, machine formats and --no-self.
        #
        # `--takeover` is the scripted form of the same choice: it skips the prompt
        # and applies takeover directly, for CI/automation that cannot answer.
        if "--takeover" in rest:
            _cmd_sync(["--takeover", "--yes"], fmt)
        else:
            _maybe_offer_takeover(rest, fmt)
        # Onboarding ends without ever saying whether the machine is now SAVING
        # anything. A fresh install often stops at `direct` (installed, not wired),
        # where the big 99% is not being realised. Name the mode and the one
        # command that shows the truth, at the moment the user is asking "is it on?".
        _post_onboard_mode_hint(fmt)
    else:
        print("Next steps (once you write the config):")
        print("  mcptoon quickstart          # write config + celebrate")
        print("  mcptoon manifest --slim     # see all available tools")
        print("  mcptoon doctor              # check connectivity")


def _manifest_tool_count(manifest) -> int:
    """Best-effort **tool** count from a `get_manifest()` result.

    `get_manifest()` returns ``{server_name: [tool, ...]}``, so counting the top
    level counts *servers*. The quickstart celebration printed that as "N tools
    ready" right above a slim manifest that named the real tools — two numbers
    for one machine on one screen (12 vs 96 on the author's, found in the
    2026-09-26 audit). Sum the per-server lists, skipping error entries, to match
    every other surface.
    """
    try:
        if isinstance(manifest, dict):
            tools = manifest.get("tools")
            if isinstance(tools, list):
                # A pre-summarised shape (kept for callers that pass one).
                return len(tools)
            total = 0
            for value in manifest.values():
                if not isinstance(value, list):
                    continue
                for t in value:
                    if isinstance(t, dict) and "error" in t:
                        continue
                    total += 1
            return total
        if isinstance(manifest, list):
            return len(manifest)
    except Exception:
        pass
    return 0


def _manifest_unreachable_count(manifest) -> int:
    """Servers in a `get_manifest()` result that never answered.

    A server that could not be started caches a single ``{"error": ...}`` entry
    (see `_manifest_tool_count`). Reproduced 2026-10-02 on a simulated clean box
    with one working server and one whose binary is absent: the celebration said
    **"11 tools ready across 2 servers"** when one of those two servers was dead.
    The tool count was already honest (errors are skipped); the *server* count was
    not. This is what lets the payoff line tell the truth.
    """
    if not isinstance(manifest, dict):
        return 0
    dead = 0
    for value in manifest.values():
        if not isinstance(value, list) or not value:
            continue
        if all(isinstance(t, dict) and "error" in t for t in value):
            dead += 1
    return dead


def _quickstart_celebration(tool_count, server_count, unreachable=0):
    """A1: the payoff block after a successful quickstart.

    Zero-config feel: big number, one-line status, one clear next action.
    ``unreachable`` is how many of ``server_count`` never started; when any did,
    the line names it instead of implying every server is usable (2026-10-02).
    """
    line = "━" * 54
    ready = max(0, server_count - unreachable)
    tail = f" ({unreachable} could not start)" if unreachable else ""
    noun = "server" if ready == 1 else "servers"
    if tool_count:
        print(line)
        print(f"  🎉  {tool_count} tools ready across {ready} {noun}{tail}!")
        print(line)
    else:
        print(line)
        print(f"  🎉  {ready} MCP {noun} configured — you're set{tail}!")
        print(line)
    print("")
    print("  Now you can:")
    print("    mcptoon status  # what's here, and what it saves")
    print("    mcptoon serve   # or expose ALL servers as ONE stdio server")
    print("")
    print("  Next steps:")
    print("  mcptoon manifest --slim     # see all available tools")
    print("  mcptoon call <server> <tool> '{...}'   # call a tool")
    print("  mcptoon doctor             # check connectivity")
    print("  mcptoon statusline --install   # keep the savings badge in Claude Code's bar")
    if server_count <= 3:
        print("")
        print("  Want more servers?")
        print("  mcptoon add github --stdio npx -y @modelcontextprotocol/server-github")
        print("  mcptoon add memory --stdio npx -y @modelcontextprotocol/server-memory")


def _maybe_offer_takeover(rest, fmt):
    """Offer to route the just-discovered servers through the gateway.

    Why this exists: registering the gateway *alongside* the user's direct entries
    (the old safe default) saves almost nothing — the host still loads every upstream
    schema, and the gateway's own copy is added on top. Measured on a 12-server /
    96-tool machine, tiktoken cl100k_base: alongside ≈ 39,500 tokens per turn,
    takeover ≈ 2,607. So the install that is supposed to save tokens can save
    ~0 unless the gateway *replaces* the direct entries. Takeover does that, but
    it is a subtraction — it removes server entries the user wrote into a host
    config — and Write Consent (CONTEXT.md) says a subtraction is listed and
    confirmed once, never silent. So this is an offer, not a silent flip: the
    entries it will drop are listed right above the prompt, and the prompt
    defaults to YES because the subtraction is legible and the undo is real
    (`mcptoon restore` drops the gateway and puts the servers back). Only an
    explicit "n" keeps the alongside-mount.

    Bounded like every other prompt in this CLI: skipped for `--dry`, machine
    formats, `--yes`-less non-interactive stdin, an empty removal plan (nothing to
    ask), and `--no-self` (the user asked for servers-only). The warning is red
    when a console is attached and plain text otherwise — the same rule
    `welcome.render` follows, so a captured transcript carries no escape codes.
    """
    if fmt != "auto" or "--dry" in rest or "--no-self" in rest:
        return
    # An explicit opt-out for scripted/CI onboarding: the offer is interactive by
    # nature and a caller that cannot answer should not see the warning at all.
    if os.environ.get("MCPTOON_NO_TAKEOVER_OFFER"):
        return
    try:
        from .sync import takeover_plan
        plan = takeover_plan()
    except Exception:
        return
    if not plan:
        return  # nothing mcptoon manages is registered directly — nothing to ask

    from . import welcome as welcome_mod

    n_servers = sum(len(row["servers"]) for row in plan)
    n_agents = len(plan)

    def _warn(text=""):
        print(welcome_mod.paint(text, "warn") if text else "")

    print("")
    _warn("━" * 54)
    _warn("  ⚠  mcptoon is not saving tokens yet")
    _warn("━" * 54)
    print("  mcptoon just registered its gateway *alongside* your servers.")
    print(f"  Your agents still load all {n_servers} of them directly, so the")
    print("  compressed schema never lands — the tool list costs about the same")
    print("  as before, plus mcptoon's own copy.")
    print("")
    print("  Routing them through the gateway instead removes their direct entries")
    print(f"  from {n_agents} agent config(s) and is the mode that actually saves.")
    print("  It is reversible: a `<config>.bak` is written first, and")
    print("  `mcptoon restore` puts your original servers back.")
    print("")
    for row in plan:
        print(f"    · {row['agent_name']}: {', '.join(row['servers'])}")
    print("")

    if not sys.stdin.isatty():
        # Cannot ask, so cannot subtract (CONTEXT.md). Point at the explicit
        # command instead of failing: the offer is a convenience, not a gate.
        print("  (Non-interactive input — not asking.) To switch later, run:")
        print("    mcptoon sync --takeover")
        print("")
        return
    try:
        answer = input("  Route them through the gateway now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        # No answer is not a yes: a subtraction must never be applied on an
        # interrupt or a closed stdin. (Windows reports NUL stdin as a tty, so a
        # scripted run reaches this prompt and hits EOF here — it must decline.)
        print("")
        print("  Kept your servers as they are — nothing was removed.")
        print("  Switch any time: mcptoon sync --takeover")
        print("")
        return
    # Default is YES: the offer is the one moment the tradeoff is legible, the
    # subtraction is listed right above, and the undo (`mcptoon restore`) is real.
    # Only an explicit "n"/"no" keeps the alongside-mount.
    if answer in ("n", "no"):
        print("  Kept your servers as they are — nothing was removed.")
        print("  Switch any time: mcptoon sync --takeover")
        print("")
        return
    print("")
    _cmd_sync(["--takeover", "--yes"], fmt)


def _cmd_health_check(rest, fmt, head_n=0, max_chars=0, full=False):
    """Health check for configured servers (legacy discover behavior).

    `head_n`/`max_chars`/`full` are the global output flags, threaded through so
    `--head`, `--max-chars` and `--full` do not silently do nothing here. See
    `_cmd_install` for why all three travel together.

    Usage:
        mcptoon discover --health           # check all servers
        mcptoon discover --health exa       # filter by name
    """
    servers = cfg.list_servers()
    if not servers:
        print("No servers configured. Run: mcptoon quickstart")
        return

    filter_name = rest[0] if rest else None

    results = []
    for name in servers:
        if filter_name and filter_name not in name:
            continue
        s_cfg = cfg.get_server_config(name)
        transport = s_cfg.get("transport", "stdio") if s_cfg else "?"
        tool_count = 0
        status = "ok"
        error_msg = ""

        try:
            tools = manifest_mod.get_server_tools(name, use_cache=True)
            errs = [t for t in tools if isinstance(t, dict) and "error" in t]
            if errs:
                # `get_server_tools` returns an error entry, not `[]`, when the
                # server never answered (2026-10-02) — so a failure is reported as
                # one here instead of reading as "answered, but exposes nothing".
                status = "error"
                error_msg = str(errs[0].get("error", ""))[:80]
            else:
                tool_count = len(tools)
                if tool_count == 0:
                    status = "no-tools"
        except Exception as e:
            status = "error"
            error_msg = str(e)[:80]

        results.append({
            "server": name,
            "transport": transport,
            "tools": tool_count,
            "status": status,
            "error": error_msg,
        })

    if fmt in ("toon", "mcptoon", "compact"):
        print(output.render(results, fmt=fmt, head_n=head_n, max_chars=max_chars, full=full))
    elif fmt == "json":
        print(output.render(results, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
    else:
        print(f"Health check: {len(results)} server(s)")
        print()
        for r in results:
            icon = "+" if r["status"] == "ok" else "x"
            print(f"  {icon} {r['server']:20s} [{r['transport']:5s}] {r['tools']:3d} tools  {r['status']}")
            if r["error"]:
                print(f"    -> {r['error']}")


def _cmd_init(rest, fmt="auto"):
    """Create sample config or auto-discover servers.

    Usage:
        mcptoon init                  # Create sample config (2 servers)
        mcptoon init --auto           # Auto-discover all MCP servers
        mcptoon init --auto --dry     # Discover, print only, don't write
        mcptoon init --auto --force   # Overwrite existing config with discovered
        mcptoon init --auto --http http://localhost:8080/mcp  # Add HTTP MCP endpoint
    """
    is_auto = "--auto" in rest
    is_dry = "--dry" in rest or "--dry-run" in rest
    is_force = "--force" in rest

    # Check for --http URL
    http_url = ""
    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    if not is_auto:
        # Legacy: create sample config
        if cfg.init_sample_config():
            print(f"Sample config created: {cfg.CONFIG_FILE}")
            print("Edit it to add your MCP servers, then run: mcptoon manifest")
            print("")
            print("Tip: Run 'mcptoon init --auto' to auto-discover all your MCP servers.")
        else:
            print(f"Config already exists: {cfg.CONFIG_FILE}")
            print("Run 'mcptoon init --auto' to discover more servers.")
        return

    # ─── Auto-discover mode ───
    from . import discover as disc

    print("Auto-discovering MCP servers...")
    print("")

    result = disc.auto_discover()

    # Add explicit HTTP endpoint if specified
    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            if probe_info.get("tools_known", True):
                tool_count = probe_info.get("tools_count") or 0
                result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} ({tool_count} tools)"
                print(f"  [Manual] http-endpoint: {http_url} ({tool_count} tools)")
            else:
                # Reachable, but its tool list could not be read — "0 tools" would
                # be a different (and wrong) claim (2026-10-02).
                result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} (reachable; tool list unreadable)"
                print(f"  [Manual] http-endpoint: {http_url} — reachable, tool list unreadable")
        else:
            # The user named this URL explicitly, so it is added anyway — but say
            # plainly that it did not answer, so the count is not mistaken for
            # "one working endpoint".
            print(f"  [Manual] http-endpoint: {http_url} — NOT responding (added anyway)")
            result.servers["http-endpoint"] = disc.make_http_config(http_url)
            result.sources["http-endpoint"] = ["manual"]
            result.reasons["http-endpoint"] = f"HTTP MCP endpoint at {http_url} (not responding)"

    print("")
    print(result.summary())

    if is_dry:
        print("(--dry mode: config not written. Run without --dry to save.)")
        return

    if result.count == 0:
        print("No servers discovered. Try: mcptoon init (creates sample config)")
        return

    # Write config
    # EITHER format counts as "a config exists" — see `config.has_config_file`.
    if cfg.has_config_file() and not is_force:
        added, skipped, overwritten = cfg.merge_servers(result.servers, overwrite=False)
        print(f"Config updated: {cfg.CONFIG_FILE}")
        print(f"  +{added} new servers added")
        print(f"  ={skipped} existing servers skipped (use --force to overwrite)")
    else:
        cfg.save_config(result.servers)
        print(f"Config written: {cfg.CONFIG_FILE} ({result.count} servers)")

    print("")
    print("Next steps:")
    print("  mcptoon manifest --slim    # see all available tools")
    print("  mcptoon doctor             # verify connectivity")


def _http_url_problem(url: str) -> str:
    """Why `url` is not a usable MCP HTTP endpoint, or "" if it looks usable.

    Deliberately narrow: it rejects only what cannot work (wrong scheme, no host)
    so a typo in the path or an unusual-but-real host still passes. Returns a
    human-readable reason, phrased to follow "Error: --http ".
    """
    from urllib.parse import urlsplit

    text = (url or "").strip()
    if not text:
        return "needs a URL"
    parsed = urlsplit(text)
    if parsed.scheme not in ("http", "https"):
        got = parsed.scheme or text
        return f"must be an http(s) URL, not {got!r}"
    if not parsed.netloc:
        return f"is missing a host: {text!r}"
    return ""


def _command_check(cmd: str) -> str:
    """Classify whether `cmd` can be launched as-is. Returns one of:

    - ``"ok"``           — an existing file, or a name found on PATH.
    - ``"missing_path"`` — the user wrote an explicit path (absolute, or with a
      separator) that does not exist. Unambiguously a typo → caller hard-errors.
    - ``"missing_name"`` — a bare command name not found on PATH. It might be
      installed later or live outside PATH, so the caller only warns.

    `add --stdio <cmd>` stores `cmd` and spawns it directly (no shell) at start
    time, resolving bare names against PATH. 0.8.29 printed "Added server 'broken'"
    and exited 0 for a non-existent exe, surfacing the breakage only on the next
    `manifest` as `[WinError 2] 系统找不到指定的文件` (which does not name the file).
    Checking now turns a silent later failure into an immediate, named message.
    """
    import shutil

    if not cmd:
        return "missing_path"
    has_sep = os.sep in cmd or (os.altsep is not None and os.altsep in cmd)
    if os.path.isabs(cmd) or has_sep:
        return "ok" if Path(cmd).exists() else "missing_path"
    # Bare name: resolve against PATH (honours PATHEXT on Windows, so `npx` → npx.cmd).
    return "ok" if shutil.which(cmd) is not None else "missing_name"


def _cmd_add(rest):
    """Add a server to config."""
    if not rest:
        _err("Usage: mcptoon add <name> --stdio <command> [args...]")
        _err("       mcptoon add <name> --http <url> [--header 'Key: Value']")
        sys.exit(1)

    name = rest[0]
    flags = rest[1:]

    # Refuse to clobber an existing server silently. `add foo --stdio python -m a`
    # then `add foo --stdio python -m b` used to just overwrite a with b and print
    # "Added server 'foo'" — a typo'd name or a re-run silently replaced a working
    # server definition (reported 2026-10-17). `--force` opts in to the overwrite.
    force = "--force" in flags
    if force:
        flags = [f for f in flags if f != "--force"]
    if not force and name in cfg.list_servers():
        _err(f"Server '{name}' already exists. Use --force to overwrite, "
             f"or 'mcptoon remove {name}' first.")
        sys.exit(1)

    if "--stdio" in flags:
        idx = flags.index("--stdio")
        cmd_parts = flags[idx + 1:]
        if not cmd_parts:
            _err("Error: --stdio requires a command")
            sys.exit(1)
        # Catch "added, but can never launch" at the keyboard. A path the user wrote
        # that does not exist is an unambiguous typo → hard error. A bare name not
        # on PATH might still be valid (installed later, or outside PATH), so only
        # warn — the server is still added. Either way the failure is named here
        # instead of surfacing later as an opaque WinError 2 that never names it.
        if not force:
            _check = _command_check(cmd_parts[0])
            if _check == "missing_path":
                _err(f"Error: '{cmd_parts[0]}' does not exist.")
                _err("  The server would be added but could never start.")
                _err("  Fix the path, or pass --force to add it anyway.")
                sys.exit(1)
            if _check == "missing_name":
                print(f"  ⚠ '{cmd_parts[0]}' is not on PATH right now — the server was "
                      f"added but may not start until it is installed.",
                      file=sys.stderr)
        # First part is command, rest are args
        server_cfg = {
            "transport": "stdio",
            "command": [cmd_parts[0]] + (cmd_parts[1:2] if len(cmd_parts) > 1 else []),
            "args": cmd_parts[2:] if len(cmd_parts) > 2 else [],
        }
        cfg.add_server(name, server_cfg)
        print(f"Added server '{name}' [stdio]: {' '.join(cmd_parts)}")

    elif "--http" in flags:
        idx = flags.index("--http")
        if idx + 1 >= len(flags):
            _err("Error: --http requires a URL")
            sys.exit(1)
        url = flags[idx + 1]
        # Refuse a value that cannot be an MCP endpoint. `add` used to accept any
        # string — `javascript:alert(1)`, `ftp://x`, `not a url`, or a bare
        # `http://` — and wrote it to config, so the breakage surfaced later as a
        # confusing connection error instead of at the keyboard. (A wrong host is
        # still the user's to make; this only rejects non-http(s) and host-less.)
        problem = _http_url_problem(url)
        if problem:
            _err(f"Error: --http {problem}")
            sys.exit(1)
        server_cfg = {"transport": "http", "url": url}

        # Parse headers
        headers = {}
        for j, f in enumerate(flags):
            if f == "--header" and j + 1 < len(flags):
                h = flags[j + 1]
                if ":" not in h:
                    # A header without a colon used to be dropped silently: `add
                    # svc --http URL --header "Bearer abc"` wrote the server with
                    # NO Authorization header and printed a cheerful "Added" — the
                    # auth then failed at call time with no clue why (reported
                    # 2026-10-17). Refuse it at the keyboard instead.
                    _err(f"Error: --header must be 'Key: Value', got {h!r} "
                         f"(no ':' to split on).")
                    sys.exit(1)
                k, v = h.split(":", 1)
                k, v = k.strip(), v.strip()
                if not k:
                    _err(f"Error: --header has an empty name: {h!r}")
                    sys.exit(1)
                headers[k] = v
        if headers:
            server_cfg["headers"] = headers

        cfg.add_server(name, server_cfg)
        print(f"Added server '{name}' [http]: {url}")

    else:
        _err("Error: must specify --stdio or --http")
        sys.exit(1)


def _cmd_remove(rest):
    """Remove one or more servers.

    Usage:
        mcptoon remove <name> [<name> ...]
    """
    if not rest:
        _err("Usage: mcptoon remove <name> [<name> ...]")
        sys.exit(1)
    # Remove EVERY name given. `remove a b` used to delete only `a` and silently
    # ignore the rest, so a script that removed several servers left some behind
    # while reporting success (reported 2026-10-18). All names are attempted; a
    # missing one is an error, and any missing name makes the whole call exit 1.
    from . import cache as cache_mod
    missing = []
    removed = []
    for name in rest:
        if cfg.remove_server(name):
            # Drop the server's schema cache too. Removing the config left the
            # per-server cache file behind forever — `add demo; manifest; remove
            # demo` still showed 1 cache file on disk (measured 2026-10-17).
            try:
                cache_mod.clear_server_cache(name)
            except Exception:
                pass
            removed.append(name)
        else:
            missing.append(name)
    for name in removed:
        print(f"Removed server: {name}")
    if missing:
        # A miss is an error, not a no-op: `mcptoon remove foo && echo done` must
        # not report success when nothing was removed. Matches `update` and the
        # other not-found paths.
        for name in missing:
            _err(f"Server not found: {name}")
        sys.exit(1)


def _cmd_usage(_rest, fmt, head_n=0, max_chars=0, full=False):
    """Show usage stats.

    `head_n`/`max_chars`/`full` are the global output flags. `--usage`'s JSON view
    is the one machine-readable output long enough to matter here; without them
    `--max-chars` was a no-op on it (found by the flag-coverage probe).
    """
    stats = usage_mod.get_usage_stats()
    # `--json` used to fall through to the human branch (only toon/mcptoon/compact
    # were routed), so `mcptoon usage --json` printed "Total calls: ..." instead of
    # JSON — a real hole for the one script-facing view of usage (reported
    # 2026-10-17). Route every machine format, and stamp the schema envelope.
    if fmt in ("toon", "mcptoon", "compact", "json"):
        # Additive delivery-mode + cli_credit so a script reading usage gets the
        # same mode truth status/footer-facts carry (cli_credit is None off CLI).
        try:
            from . import footer as footer_mod
            stats = dict(stats)
            stats["delivery_mode"] = footer_mod.current_mode()
            stats["cli_credit"] = footer_mod.cli_credit(footer_mod.facts())
        except Exception:
            pass
        print(output.render(output.stamp_schema(stats), fmt=fmt, head_n=head_n,
                            max_chars=max_chars, full=full))
    else:
        calls = int(stats.get("total_calls") or 0)
        print(f"Total calls: {calls}")
        # On a machine that has not routed anything yet, "0/0" reads as a broken
        # metric rather than an empty one. Show a dash until there is a call to
        # divide by. (2026-09-26 polish pass.)
        rate = stats.get("success_rate") or ""
        print(f"Success rate: {rate}" if calls else "Success rate: —")
        print(f"Tokens (est): {stats['total_tokens_est']}")
        # `usage` only knows *result* tokens and call counts — it never named what
        # a CLI call keeps out of context, which is the CLI user's real saving. Add
        # that line (only on the CLI path) so this surface is not the one place a
        # CLI user reads and sees no CLI credit.
        try:
            from . import footer as footer_mod
            credit = footer_mod.cli_credit(footer_mod.facts())
        except Exception:
            credit = None
        if credit:
            if cfg.resolve_lang() == "zh":
                print(f"CLI 模式：每次调用都跳过全量 {credit['resident_avoided']:,} "
                      f"token 的 schema，累计 {calls:,} 次")
            else:
                print(f"CLI mode: each call skipped the full "
                      f"{credit['resident_avoided']:,}-token schema set · "
                      f"{calls:,} calls")
        # By agent, from the ledger — the counter alone never knew the host. Only
        # shown once a ledger exists, so a pre-ledger machine looks unchanged.
        by_host = stats.get("by_host") or {}
        if by_host:
            print("\nBy host:")
            for h, c in by_host.items():
                print(f"  {h:20s} {c}")
        if stats["by_server"]:
            print("\nBy server:")
            for s, c in stats["by_server"].items():
                print(f"  {s:20s} {c}")
        if stats["top_tools"]:
            print("\nTop tools:")
            for t, c in stats["top_tools"].items():
                print(f"  {t:30s} {c}")


def _parse_since(arg: str):
    """Turn a `--since` argument into a cutoff timestamp (epoch seconds), or None.

    Accepts a relative span (``1h``, ``30m``, ``7d``, ``24h``), the words ``today``
    (local midnight) and ``all`` (no cutoff, i.e. everything), or an explicit date
    ``YYYY-MM-DD`` (local midnight of that day). Returns None when the argument is
    not understood, so the caller can say so rather than silently ignoring it.
    """
    if not arg:
        return None
    s = arg.strip().lower()
    if s in ("all", "any", "forever"):
        return 0
    if s == "today":
        lt = time.localtime()
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    # Relative: <number><unit>, unit in m(inute)/h(our)/d(ay)/w(eek).
    m = re.match(r"^(\d+)\s*([mhdw])$", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        secs = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}[unit]
        return time.time() - n * secs
    # Explicit date YYYY-MM-DD (local midnight).
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        try:
            return time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                0, 0, 0, 0, 0, -1))
        except (ValueError, OverflowError):
            return None
    return None


def _activity_filter(entries, since_ts=None, failures_only=False,
                     tool_filter=None, search_arg=None):
    """Apply the shared narrowing filters to a list of ledger entries.

    One place for --since / --failures / --tool / --search so the list view,
    export, top, and follow can never disagree about what "matching" means.
    Order-independent; each filter is a pure predicate.
    """
    out = entries
    if since_ts is not None:
        out = [e for e in out
               if isinstance(e.get("ts"), (int, float)) and e["ts"] >= since_ts]
    if failures_only:
        out = [e for e in out if not e.get("ok")]
    if tool_filter:
        want = tool_filter.strip()
        if ":" in want:
            srv, tl = want.split(":", 1)
            out = [e for e in out
                   if e.get("server") == srv and e.get("tool") == tl]
        else:
            out = [e for e in out if e.get("tool") == want]
    if search_arg:
        needle = search_arg.lower()
        def _hit(e):
            hay = " ".join(str(e.get(k, "")) for k in
                           ("host", "server", "tool", "detail", "err"))
            return needle in hay.lower()
        out = [e for e in out if _hit(e)]
    return out


def _activity_export(export_fmt: str, host_filter=None, since_ts=None,
                     failures_only=False, tool_filter=None, search_arg=None) -> None:
    """Dump the whole activity ledger as json or csv on stdout. Never raises.

    The on-screen `activity` view is a tail; an audit or a pasted bug report wants
    every line in a form `jq` or a spreadsheet can read. ``read_activity(limit=0)``
    returns the full file (newest first); export reverses to oldest-first so a csv
    reads chronologically. Honours ``--since`` and ``--failures``. The ledger is a
    local file — this prints it, uploads nothing.
    """
    entries = usage_mod.read_activity(limit=0, host=host_filter)
    entries = _activity_filter(entries, since_ts=since_ts, failures_only=failures_only,
                               tool_filter=tool_filter, search_arg=search_arg)
    entries = list(reversed(entries))  # chronological for humans and spreadsheets
    if export_fmt == "csv":
        import csv as _csv
        cols = ["ts", "iso", "host", "server", "tool", "ok", "tokens", "ms",
                "detail", "err"]
        writer = _csv.writer(sys.stdout)
        writer.writerow(cols)
        for e in entries:
            ts = e.get("ts")
            iso = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                   if isinstance(ts, (int, float)) else "")
            writer.writerow([
                ts if isinstance(ts, (int, float)) else "",
                iso,
                e.get("host") or "CLI",
                e.get("server", ""),
                e.get("tool", ""),
                "ok" if e.get("ok") else "error",
                e.get("tokens") or 0,
                # `ms` was in json but missing from csv, so an export to a
                # spreadsheet silently dropped every call's duration. Empty when
                # the call was not timed, never a fake 0.
                e.get("ms") if isinstance(e.get("ms"), int) else "",
                e.get("detail", ""),
                e.get("err", ""),
            ])
        return
    # json: a flat array of the ledger objects, plus a small envelope for context.
    payload = {
        "count": len(entries),
        "ledger": str(usage_mod._activity_file()),
        "entries": entries,
    }
    if host_filter:
        payload["host"] = host_filter
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_activity(rest, fmt, head_n=0, max_chars=0, full=False):
    """Show the activity ledger — who used mcptoon, when, and on what.

    The readable counterpart to `mcptoon usage`'s counters. `usage` answers "how
    many, which servers" and is deliberately lossy (its window caps at 1000). This
    answers the different question a person who installed mcptoon and forgot asks:
    "is it even doing anything, and for which agent?" — one line per routed call
    (time, host, server:tool, ok, tokens), newest first.

    `head_n`/`max_chars`/`full` are the global output flags, forwarded so
    `activity --json` honours them like every other record view.

    Usage:
        mcptoon activity                 # last 20 routed calls
        mcptoon activity --head 50       # last 50 (global --head)
        mcptoon activity --json          # machine-readable
        mcptoon activity --summary       # totals: today, last host, by host
        mcptoon activity --host Cursor   # only one agent's calls
        mcptoon activity --since today   # only calls since a point in time
        mcptoon activity --failures      # only calls that failed
        mcptoon activity --export csv    # dump the whole ledger as csv/json
        mcptoon activity --clear         # wipe the ledger (usage counters stay)
    """
    rest = rest or []
    if rest and rest[0] in ("-h", "--help"):
        print("Usage: mcptoon activity [--head N] [--json] [--summary] [--host H] [--since WHEN] [--failures] [--export json|csv] [--follow] [--clear]")
        print("")
        print("  One line per tool call mcptoon routed: time, host, tool, tokens.")
        print("  Answers \"is mcptoon being used, and by which agent?\"")
        print("      mcptoon activity              last 20 routed calls")
        print("      mcptoon activity --summary    totals: today, last host, by host")
        print("      mcptoon activity --host H     only calls from agent H (e.g. Cursor)")
        print("      mcptoon activity --since W    only calls since W: today, 1h, 24h,")
        print("                                    or a date like 2026-10-18")
        print("      mcptoon activity --failures   only calls that failed")
        print("      mcptoon activity --tool T     only calls to tool T (server:tool or tool)")
        print("      mcptoon activity --search K   only calls mentioning keyword K")
        print("      mcptoon activity --top [N]    rank by host and by tool (default 10)")
        print("      mcptoon activity --export csv dump the WHOLE ledger as csv (or json)")
        print("      mcptoon activity --follow     stream new calls live (Ctrl-C to stop)")
        print("      mcptoon activity --clear      wipe the ledger (usage stays)")
        print("      mcptoon activity --clear --before 7d   drop only entries older than 7d")
        print("  The ledger is a local file on this machine; nothing is uploaded anywhere.")
        return

    # `--host <name>` / `--host=<name>`: the ledger already stores the driving
    # client, and `read_activity(host=)` already filters, but the CLI never
    # exposed it — so "was it Cursor or Claude just now?" had no answer short of
    # reading JSON by hand.
    host_filter = None
    for i, a in enumerate(rest):
        if a == "--host" and i + 1 < len(rest):
            host_filter = rest[i + 1]
            break
        if a.startswith("--host="):
            host_filter = a.split("=", 1)[1]
            break

    # `--since <when>`: "today / 1h / 24h / 7d / 2026-10-18". A cutoff timestamp;
    # entries older than it are dropped. Parsed here so the list, export, and
    # failures views all honour it the same way.
    since_arg = None
    for i, a in enumerate(rest):
        if a == "--since" and i + 1 < len(rest):
            since_arg = rest[i + 1]
            break
        if a.startswith("--since="):
            since_arg = a.split("=", 1)[1]
            break
    since_ts = None
    if since_arg is not None:
        since_ts = _parse_since(since_arg)
        if since_ts is None:
            print(f"mcptoon activity: could not understand --since {since_arg!r}",
                  file=sys.stderr)
            print("  Try: --since today | 1h | 24h | 7d | 2026-10-18", file=sys.stderr)
            sys.exit(2)

    # `--failures`: only the red lines. Debugging does not want to scroll past
    # hundreds of ok calls to find the ones that broke.
    failures_only = "--failures" in rest

    # `--tool <name>`: only calls to one tool. Accepts `server:tool` or a bare
    # `tool` (matches on the tool half). Debugging one integration should not mean
    # eyeballing every other server's lines.
    tool_filter = None
    for i, a in enumerate(rest):
        if a == "--tool" and i + 1 < len(rest):
            tool_filter = rest[i + 1]
            break
        if a.startswith("--tool="):
            tool_filter = a.split("=", 1)[1]
            break

    # `--search <keyword>`: a free-text filter over host/server/tool/detail/err.
    # "when did that METHOD_NOT_FOUND happen?" is a substring question the per-line
    # view answers only by eye. Case-insensitive.
    search_arg = None
    for i, a in enumerate(rest):
        if a == "--search" and i + 1 < len(rest):
            search_arg = rest[i + 1]
            break
        if a.startswith("--search="):
            search_arg = a.split("=", 1)[1]
            break

    # `--top [N]`: rank by host and by tool instead of listing lines. "Which agent
    # leans on me most, and which capability?" is a counting question the per-line
    # tail cannot answer. Bare `--top` defaults to 10; honours --since/--host.
    top_n = None
    for i, a in enumerate(rest):
        if a == "--top":
            nxt = rest[i + 1] if i + 1 < len(rest) else ""
            top_n = max(1, int(nxt)) if nxt.isdigit() else 10
            break
        if a.startswith("--top="):
            v = a.split("=", 1)[1]
            top_n = max(1, int(v)) if v.isdigit() else 10
            break

    # `--export json|csv`: the whole ledger, not the on-screen tail. The default
    # view shows the last 20; an audit or a bug report wants all of it in a form a
    # spreadsheet or `jq` can take. Bare `--export` defaults to json.
    export_fmt = None
    for i, a in enumerate(rest):
        if a == "--export":
            nxt = rest[i + 1] if i + 1 < len(rest) else ""
            export_fmt = nxt if nxt in ("json", "csv") else "json"
            break
        if a.startswith("--export="):
            v = a.split("=", 1)[1]
            export_fmt = v if v in ("json", "csv") else "json"
            break

    if export_fmt:
        return _activity_export(export_fmt, host_filter, since_ts=since_ts,
                                failures_only=failures_only, tool_filter=tool_filter,
                                search_arg=search_arg)

    # `--follow`: block and stream new calls (tail -f). Handled before the
    # snapshot views so it never falls through to a one-shot print.
    if "--follow" in rest:
        return _activity_follow(host_filter, failures_only=failures_only)

    if "--clear" in rest:
        path = usage_mod._activity_file()
        # `--clear --before <when>`: prune only entries older than a cutoff,
        # keeping recent history. A plain `--clear` wipes everything, which is the
        # only option there used to be — someone who wants to keep the last week
        # but drop the rest had no way to say so.
        before_arg = None
        for i, a in enumerate(rest):
            if a == "--before" and i + 1 < len(rest):
                before_arg = rest[i + 1]
                break
            if a.startswith("--before="):
                before_arg = a.split("=", 1)[1]
                break
        if before_arg is not None:
            cutoff = _parse_since(before_arg)
            if cutoff is None:
                print(f"mcptoon activity: could not understand --before {before_arg!r}",
                      file=sys.stderr)
                print("  Try: --before 2026-10-01 | 7d | 24h", file=sys.stderr)
                sys.exit(2)
            removed, kept, ok = _activity_prune_before(path, cutoff)
            if fmt == "json":
                print(json.dumps({"pruned": removed, "kept": kept, "ok": ok,
                                  "path": str(path)}, ensure_ascii=False))
                return
            if not ok:
                print(f"Could not prune the ledger at {path}", file=sys.stderr)
                sys.exit(1)
            print(f"Pruned {removed:,} old call{'' if removed == 1 else 's'} "
                  f"before {before_arg}; kept {kept:,}.")
            return
        try:
            path.unlink(missing_ok=True)
            removed = True
        except OSError:
            removed = False
        if fmt == "json":
            print(json.dumps({"cleared": removed, "path": str(path)},
                             ensure_ascii=False))
            return
        if removed:
            print(f"Cleared the activity ledger: {path}")
            print("  (the `usage` counters are separate and were not touched)")
        else:
            print(f"Could not clear the ledger at {path}", file=sys.stderr)
            sys.exit(1)
        return

    if top_n is not None:
        return _activity_top(top_n, fmt, host_filter=host_filter, since_ts=since_ts,
                             failures_only=failures_only, tool_filter=tool_filter,
                             search_arg=search_arg, head_n=head_n,
                             max_chars=max_chars, full=full)

    if "--summary" in rest:
        summary = usage_mod.activity_summary()
        if fmt in ("toon", "mcptoon", "compact", "json"):
            try:
                from . import footer as footer_mod
                summary = dict(summary)
                summary["delivery_mode"] = footer_mod.current_mode()
                summary["cli_credit"] = footer_mod.cli_credit(footer_mod.facts())
            except Exception:
                pass
            print(output.render(output.stamp_schema(summary), fmt=fmt,
                                head_n=head_n, max_chars=max_chars, full=full))
            return
        n = summary["entries"]
        if not n:
            print("No routed calls recorded yet.")
            return
        print("mcptoon activity — summary")
        print(f"  Calls recorded  : {n}")
        print(f"  Today           : {summary['today_calls']}")
        # Reliability: success vs failure over this window, plus how slow the timed
        # calls were. "Was it reliable?" used to be unanswerable from the tail.
        ok_c = summary.get("ok_count", 0)
        fail_c = summary.get("fail_count", 0)
        if n:
            rate = ok_c / n * 100
            print(f"  Success         : {ok_c}/{n} ({rate:.1f}%)"
                  + (f"  ·  {fail_c} failed" if fail_c else ""))
        slow_c = summary.get("slow_count", 0)
        avg_ms = summary.get("avg_ms")
        if avg_ms is not None:
            slow_tail = f"  ·  {slow_c} slow (>{_SLOW_CALL_MS} ms)" if slow_c else ""
            print(f"  Latency         : avg {avg_ms:,} ms{slow_tail}")
            # p50/p90: the mean hides a long tail; these say what a typical and a
            # bad call cost. Only shown when there are timed calls to measure.
            p50 = summary.get("p50_ms")
            p90 = summary.get("p90_ms")
            if p50 is not None and p90 is not None:
                print(f"                    p50 {p50:,} ms  ·  p90 {p90:,} ms")
        last_ts = summary.get("last_ts")
        when = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_ts))
                if isinstance(last_ts, (int, float)) else "—")
        print(f"  Last used       : {summary.get('last_host') or '—'}  at {when}")
        hosts = summary.get("hosts") or {}
        if hosts:
            print("  By host         :")
            for h, c in hosts.items():
                print(f"    {h:20s} {c}")
        # CLI credit, matching the list view's footer. The summary is the other
        # view of the same command; leaving it without the CLI figure made the two
        # views disagree about what the user saved (only on the CLI path).
        try:
            from . import footer as footer_mod
            credit = footer_mod.cli_credit(footer_mod.facts())
        except Exception:
            credit = None
        if credit:
            if cfg.resolve_lang() == "zh":
                print(f"  CLI 模式        : 每次调用都跳过全量 "
                      f"{credit['resident_avoided']:,} token 的 schema")
            else:
                print(f"  CLI mode        : each call skipped the full "
                      f"{credit['resident_avoided']:,}-token schema set")
        # Retention and size were invisible: the ledger silently rolls off old
        # lines at a fixed cap, and a user deciding whether it is "an audit log"
        # deserves to know both the cap and how close the file is to it.
        keep = usage_mod._activity_keep()
        path = usage_mod._activity_file()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        print(f"  Retention       : newest {keep:,} calls kept "
              f"(older lines roll off)")
        print(f"  Ledger size     : {_human_bytes(size)} at {path}")
        first_ts = summary.get("first_ts")
        if isinstance(first_ts, (int, float)):
            since = time.strftime("%Y-%m-%d %H:%M", time.localtime(first_ts))
            print(f"  Earliest kept   : {since} (how far back this history goes)")
        return

    limit = head_n if head_n and head_n > 0 else 20
    entries = usage_mod.read_activity(limit=0, host=host_filter)
    # `--since` / `--failures` / `--tool` / `--search` narrow the set before the
    # head cap is applied, so `--failures --head 20` means "the last 20 failures",
    # not "failures among the last 20 calls".
    entries = _activity_filter(entries, since_ts=since_ts, failures_only=failures_only,
                               tool_filter=tool_filter, search_arg=search_arg)
    if limit:
        entries = entries[:limit]
    total = usage_mod.activity_summary()["entries"]

    if fmt in ("toon", "mcptoon", "compact", "json"):
        payload = {"entries": entries, "count": len(entries), "total": total,
                   "path": str(usage_mod._activity_file())}
        if host_filter:
            payload["host"] = host_filter
        if since_arg is not None:
            payload["since"] = since_arg
        if failures_only:
            payload["failures_only"] = True
        if tool_filter:
            payload["tool"] = tool_filter
        if search_arg:
            payload["search"] = search_arg
        print(output.render(output.stamp_schema(payload), fmt=fmt, head_n=head_n,
                            max_chars=max_chars, full=full))
        return

    if not entries:
        if failures_only:
            print("No failed calls recorded in this window — good news.")
        elif tool_filter:
            print(f"No routed calls recorded for tool {tool_filter!r} in this window.")
        elif search_arg:
            print(f"No routed calls matching {search_arg!r} in this window.")
        elif host_filter:
            print(f"No routed calls recorded from host {host_filter!r}.")
            print("  Drop --host to see every agent, or `mcptoon activity --summary`"
                  " for the by-host totals.")
        elif since_arg is not None:
            print(f"No routed calls recorded since {since_arg!r}.")
        else:
            print("No routed calls recorded yet.")
            print("  Use a tool through mcptoon (or let your agent use one), then check"
                  " again.")
        print(f"  Ledger: {usage_mod._activity_file()}")
        return

    scope = ""
    if host_filter:
        scope += f" from {host_filter}"
    if tool_filter:
        scope += f" on {tool_filter}"
    if search_arg:
        scope += f" matching {search_arg!r}"
    if since_arg is not None:
        scope += f" since {since_arg}"
    if failures_only:
        scope += " (failures only)"
    label = "failed call" if failures_only else "routed call"
    print(f"mcptoon activity — last {len(entries)} {label}"
          f"{'' if len(entries) == 1 else 's'}{scope}")
    line = "─" * 66
    print(line)
    for e in entries:
        print(_activity_line(e))
    print(line)
    print(f"  showing {len(entries)} of {total} total · full ledger: "
          f"{usage_mod._activity_file()}")
    # The CLI-credit footer: the per-line view names what each call pulled, but it
    # never sums what the whole window *kept out of context*. On a CLI machine that
    # is the number a user scrolling history actually wants ("what did all these
    # calls save me?"). Only shown on the CLI path — a serve user's saving is the
    # gateway's, already named elsewhere.
    try:
        from . import footer as footer_mod

        credit = footer_mod.cli_credit(footer_mod.facts())
        if credit:
            resident = footer_mod._human_tokens(credit["resident_avoided"])
            if footer_mod.lang() == "zh":
                print(f"  CLI 模式：以上每次调用都没加载全量 {resident} token 的 schema")
            else:
                print(f"  CLI mode: each call above skipped loading the full "
                      f"{resident}-token schema set")
    except Exception:
        pass


def _activity_line(e: dict) -> str:
    """Render one ledger entry as a (possibly multi-line) block. Shared by the
    list view and `--follow`, so the two can never drift in shape."""
    from . import welcome as _welcome
    ts = e.get("ts")
    when = (time.strftime("%m-%d %H:%M:%S", time.localtime(ts))
            if isinstance(ts, (int, float)) else "—")
    host = (e.get("host") or "CLI")[:16]
    sk = f"{e.get('server','')}:{e.get('tool','')}"[:30]
    ok = "ok " if e.get("ok") else "ERR"
    tok = e.get("tokens") or 0
    # Wall-clock duration, when the caller timed it. A slow call is flagged
    # inline: a line that took 8 seconds is the one worth noticing, and it is
    # otherwise indistinguishable from a fast one.
    ms = e.get("ms")
    dur = ""
    slow = False
    if isinstance(ms, int) and ms >= 0:
        slow = ms >= _SLOW_CALL_MS
        dur = f"  {'SLOW ' if slow else ''}{ms:,} ms"
    # Colour only on a real terminal (paint() returns plain text for a pipe/NO_COLOR),
    # so a captured transcript stays clean: red for a failed line, yellow for a slow
    # one. The signal is already in the text ("ERR"/"SLOW"); colour just makes it
    # pop for a human watching `activity --follow`.
    ok_field = ok
    dur_field = dur
    if _welcome.color_enabled():
        if not e.get("ok"):
            ok_field = _welcome.paint(ok, "warn")
        elif slow:
            dur_field = _welcome.paint(dur, "warn")
    out = [f"  {when}  {host:16s} {sk:30s} {ok_field}  {tok:>7,} tok{dur_field}"]
    # `detail` names what actually moved (e.g. the skills a resolve handed out) —
    # the difference between "resolve_skills ran" and "it distributed
    # xiewen-shipin and duanju-juben".
    detail = e.get("detail")
    if detail:
        out.append(f"      ↳ {detail}")
    # `err` says why a line is red — the difference between "it failed" and
    # "it failed because the server returned METHOD_NOT_FOUND".
    err = e.get("err")
    if err and not e.get("ok"):
        out.append(f"      ✗ {err}")
    return "\n".join(out)


def _activity_prune_before(path, cutoff: float):
    """Drop ledger lines whose ts is older than `cutoff`. Returns (removed, kept, ok).

    Rewrites the file only when something is actually pruned. A line that cannot be
    parsed is KEPT — this is a targeted prune, not a repair, and silently dropping a
    torn line here would destroy data the user did not ask to remove. Best-effort:
    an unreadable/unwritable file returns ok=False so the caller can report it.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return 0, 0, True
    except OSError:
        return 0, 0, False
    kept_lines = []
    removed = 0
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        try:
            e = json.loads(s)
            ts = e.get("ts") if isinstance(e, dict) else None
        except (json.JSONDecodeError, ValueError):
            kept_lines.append(raw)
            continue
        if isinstance(ts, (int, float)) and ts < cutoff:
            removed += 1
        else:
            kept_lines.append(raw)
    if removed:
        try:
            with path.open("w", encoding="utf-8") as fh:
                fh.writelines(kept_lines)
        except OSError:
            return 0, len(kept_lines), False
    return removed, len(kept_lines), True


def _activity_top(top_n: int, fmt: str, host_filter=None, since_ts=None,
                  failures_only=False, tool_filter=None, search_arg=None,
                  head_n=0, max_chars=0, full=False) -> None:
    """Rank the ledger by host and by tool — "who uses me most, on what?".

    The per-line tail shows what happened; this aggregates it. Two tables: by host
    (which agent) and by server:tool (which capability), each sorted by call count,
    top N. Honours --since / --host / --failures the same way the list view does, so
    "top tools Cursor used today" is expressible. Counts are over the retained
    window (capped at activity_keep), not lifetime — labelled as such in the footer.
    """
    entries = usage_mod.read_activity(limit=0, host=host_filter)
    entries = _activity_filter(entries, since_ts=since_ts, failures_only=failures_only,
                               tool_filter=tool_filter, search_arg=search_arg)

    by_host: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    for e in entries:
        h = e.get("host") or "CLI"
        by_host[h] = by_host.get(h, 0) + 1
        t = f"{e.get('server', '')}:{e.get('tool', '')}".strip(":")
        by_tool[t] = by_tool.get(t, 0) + 1

    def _rank(d: dict) -> list:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]

    if fmt in ("toon", "mcptoon", "compact", "json"):
        payload = {
            "count": len(entries),
            "by_host": dict(_rank(by_host)),
            "by_tool": dict(_rank(by_tool)),
            "path": str(usage_mod._activity_file()),
        }
        if host_filter:
            payload["host"] = host_filter
        if since_ts is not None:
            payload["since"] = True
        if failures_only:
            payload["failures_only"] = True
        print(output.render(output.stamp_schema(payload), fmt=fmt, head_n=head_n,
                            max_chars=max_chars, full=full))
        return

    if not entries:
        print("No routed calls recorded in this window.")
        print(f"  Ledger: {usage_mod._activity_file()}")
        return

    scope = ""
    if host_filter:
        scope += f" from {host_filter}"
    if since_ts is not None:
        scope += " in this time window"
    if failures_only:
        scope += " (failures only)"
    print(f"mcptoon activity — top {top_n} over {len(entries)} call"
          f"{'' if len(entries) == 1 else 's'}{scope}")
    line = "─" * 66
    print(line)
    print(f"  By host ({min(top_n, len(by_host))}):")
    for h, c in _rank(by_host):
        bar = "█" * min(30, max(1, round(c / len(entries) * 30)))
        print(f"    {h:20s} {c:>6,}  {bar}")
    print(f"  By tool ({min(top_n, len(by_tool))}):")
    for t, c in _rank(by_tool):
        bar = "█" * min(30, max(1, round(c / len(entries) * 30)))
        print(f"    {t:30s} {c:>6,}  {bar}")
    print(line)
    print(f"  counted over the retained window · full ledger: "
          f"{usage_mod._activity_file()}")


def _activity_follow(host_filter=None, interval: float = 1.0,
                     failures_only: bool = False) -> None:
    """Stream new ledger lines as they arrive, like `tail -f`. Ctrl-C to stop.

    Polls the ledger file for new lines rather than watching it (portable, and the
    ledger is appended by many short-lived processes that a file-watch would miss).
    Starts from the CURRENT end so it shows what happens next, not history — pair
    with a plain `mcptoon activity` to see the past. Honours ``--host`` and
    ``--failures``. Only the fields already in the ledger are shown; nothing is
    inferred.
    """
    path = usage_mod._activity_file()
    try:
        start = path.stat().st_size if path.exists() else 0
    except OSError:
        start = 0
    print(f"Following {path} — new routed calls appear below (Ctrl-C to stop).")
    print("─" * 66)
    try:
        while True:
            try:
                if not path.exists():
                    time.sleep(interval)
                    continue
                size = path.stat().st_size
                if size < start:
                    start = 0  # file was trimmed/cleared underneath us
                if size > start:
                    with path.open("r", encoding="utf-8", errors="replace") as fh:
                        fh.seek(start)
                        chunk = fh.read()
                        start = fh.tell()
                    for raw in chunk.splitlines():
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            e = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if not isinstance(e, dict):
                            continue
                        if host_filter is not None and e.get("host") != host_filter:
                            continue
                        if failures_only and e.get("ok"):
                            continue
                        print(_activity_line(e))
                time.sleep(interval)
            except KeyboardInterrupt:
                raise
            except OSError:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("")
        print("  stopped.")


def _cmd_retrieve(rest, fmt, max_chars=0):
    """mcptoon retrieve <handle> — the CLI's read half of compression.

    Why this exists: every `--smart` output can end with
    `full text: mcptoon_retrieve handle=<id>`, and that handle was only
    redeemable from an MCP session, because `mcptoon_retrieve` is a native MCP
    tool and the CLI had no counterpart. A shell-only user (or an agent driving
    the CLI, which is how most of mcptoon is actually used) was told exactly how
    to get their data back and then had no way to do it. The command closes that
    hole: same store, same handle, same failure sentences (they live in
    `ccr.RETRIEVE_NOTICES` so the two paths cannot drift).

    Usage:
        mcptoon retrieve <handle>            # print the original
        mcptoon retrieve <handle> --json     # as JSON (default is also JSON)
        mcptoon retrieve --list              # what is in the store right now
    """
    from . import ccr

    if not rest or rest[0] in ("-h", "--help"):
        # A bare `retrieve` is a usage error: it did nothing useful yet exited 0,
        # so `mcptoon retrieve && echo ok` reported success on a no-op (reported
        # 2026-10-18). `--help` is a legitimate success, so only the no-arg case
        # exits 1. Same contract as `inspect` / `call`.
        print("Usage: mcptoon retrieve <handle>")
        print("       mcptoon retrieve --list        Show what is in the store")
        print("")
        print("  Handles are printed by any --smart command, e.g.:")
        print("      mcptoon install --list --smart")
        print("      mcptoon call <server> <tool> --smart")
        if not rest:
            sys.exit(1)
        return

    if rest[0] == "--list":
        info = ccr.stats()
        policy = ccr.policy()
        ttl = policy.get("ttl") or 0
        # `--json` gives scripts the store stats as data. It printed human text
        # regardless of format (reported 2026-10-18).
        if fmt == "json":
            print(json.dumps({
                "count": info["count"],
                "bytes": info["bytes"],
                "oldest_age": info["oldest_age"],
                "ttl": ttl,
                "store_dir": str(ccr._store_dir()),
            }, ensure_ascii=False))
            return
        print(f"Stored originals: {info['count']}")
        print(f"Store size:       {info['bytes']:,} bytes")
        print(f"Oldest entry:     {info['oldest_age']}s")
        print(f"Retention:        {'never expires' if not ttl else f'{ttl}s TTL'}")
        print(f"Store dir:        {ccr._store_dir()}")
        return

    handle = rest[0]
    status, original = ccr.retrieve_status(handle)
    if status != ccr.STATUS_OK:
        # A miss is an error, not an empty success: `mcptoon retrieve <h> && ...`
        # must not look like it worked. Same exit-code rule as `remove`/`config get`.
        print(f"❌ {ccr.retrieve_notice(status)}", file=sys.stderr)
        print(f"   status: {status}", file=sys.stderr)
        sys.exit(1)

    if fmt in ("raw",):
        if isinstance(original, str):
            print(original)
        else:
            print(json.dumps(original, ensure_ascii=False))
        return
    # The original is handed back whole — that is the point of a retrieve — unless
    # the user asks for a cap with --max-chars. `fmt="json"` is machine-readable, so
    # the default 4,000-char cap does not apply here anyway; passing `full=True`
    # would be wrong, because it is checked first and would override --max-chars.
    print(output.render(original, fmt="json", max_chars=max_chars))


def _cmd_footer_facts(_rest, fmt, max_chars=0):
    """One line of real numbers for the per-turn savings footer. Never blocks.

    Usage:
        mcptoon footer-facts
        mcptoon footer-facts --json
    This exists because the agent-side directive tells the model to close a turn
    with one line of savings, and the obvious implementation — run
    `mcptoon status` — is unusable in a chat loop: `status` refreshes a stale
    schema cache by spawning every configured MCP server, measured at ~23s here
    against ~1.9s warm. A footer that occasionally costs 23 seconds is worse than
    no footer, so this reads the cache at whatever age it has and never opens a
    connection. When the cache is missing or older than the freshness TTL it says
    so in `note` rather than refreshing, because a number the caller can date is
    honest and a 23-second pause is not.

    The figures live in `footer.facts()` rather than here, because three surfaces
    now need them: this command, the tail of every other command, and the first
    tool result of an MCP session. Keeping one implementation is what makes all of
    them agree — see the `footer` module docstring for why the line stopped being
    the model's job to remember.
    """
    from . import footer as footer_mod

    f = footer_mod.facts()

    if fmt == "json":
        # Routed through `render` rather than `json.dumps` so `--max-chars` works
        # here too; `fmt="json"` keeps it machine-readable (no default cap).
        # Additive: name the delivery mode and the unified cli_credit dict so a
        # script reads the same "0 resident" truth the human line prints, in the
        # same shape `status --json` uses. Off the CLI path cli_credit is None.
        payload = dict(f)
        payload["delivery_mode"] = footer_mod.current_mode()
        payload["cli_credit"] = footer_mod.cli_credit(f)
        print(output.render(output.stamp_schema(payload), fmt="json", max_chars=max_chars))
        return

    # Human line — the whole point is that this is pasteable into a turn.
    # Tools line, then the skills and compression lines, then the note. Order
    # matches `footer.block()`, so "quote it verbatim" stays true.
    print(footer_mod.line(f))
    for extra in (footer_mod.skills_line(f), footer_mod.compression_line(f)):
        if extra:
            print(extra)
    n = footer_mod.note(f)
    if n:
        print(f"note: {n}")
    # On a CLI machine the three lines above are all serve/gateway figures, which
    # read as "not about me" to a CLI user — the exact complaint this addresses.
    # Append the CLI-caliber line so the pasteable block names what *this* mode
    # saves. It is None off the CLI path, so every other machine's output — and
    # the byte-identity of the first lines with `footer.block()` — is unchanged.
    credit = footer_mod.cli_credit_line(f)
    if credit:
        print(credit)
    # Newer-release hint — reads a cache file only (never the network), so it stays
    # footer-safe and instant. When there is no fresh record, or we are current, it
    # prints nothing and the footer is byte-identical to before. `maybe_refresh_cache`
    # is throttled (once per TTL) and spawns a *detached* `upgrade --check --quiet`;
    # it never blocks this process and never opens a connection inline.
    from . import upgrade as upgrade_mod
    hint = upgrade_mod.footer_hint()
    if hint:
        print(hint)
    upgrade_mod.maybe_refresh_cache()


def _cmd_credit(_rest, fmt, head_n=0, max_chars=0, full=False):
    """One screen: which delivery mode, what it really saves, and the one action.

    The CLI/direct credit now lives on many surfaces (status, statusline,
    footer-facts, report, savings, stats, usage, activity, bench) but there was no
    single command to just *ask* "what is my mode and what am I really saving?".
    This is that one command. It never invents a number: on a direct machine it
    says "you save 0"; on cli/serve it names the real figure; the action comes
    from `mode.recommend`. `--json` carries the same contract fields.
    """
    from . import footer as footer_mod
    from . import mode as mode_mod

    lng = cfg.resolve_lang()
    zh = lng == "zh"
    f = footer_mod.facts()
    cur = footer_mod.current_mode()
    credit = footer_mod.cli_credit(f)
    try:
        rec = mode_mod.recommend(lng=lng)
    except Exception:
        rec = {}

    if fmt == "json":
        payload = {
            "mode": cur,
            "delivery_mode": cur,   # unified key every other surface uses
            "cli_credit": credit,
            "resident_avoided": credit["resident_avoided"] if credit else 0,
            "calls": int(f.get("calls_recorded") or 0),
            "recommended": rec.get("recommended"),
            "one_action": rec.get("one_action"),
            "reason": rec.get("reason"),
            "caliber": f.get("token_caliber") or "",
        }
        print(output.render(output.stamp_schema(payload), fmt="json",
                            head_n=head_n, max_chars=max_chars, full=full))
        return

    calls = int(f.get("calls_recorded") or 0)
    full = int(f.get("tokens_full") or 0)
    if cur == "direct":
        line = (f"直连（装了没接）— 现在省 0；全量 {full:,} token 每轮都在烧"
                if zh else
                f"direct (installed, not wired) — saves 0 right now; the full "
                f"{full:,} tokens load every turn")
    elif cur == "serve-alongside":
        line = (f"serve（网关已接，但直连条目没被接管）— 现在省 0；"
                f"全量 {full:,} token 仍每轮直连加载"
                if zh else
                f"serve-alongside (gateway wired, direct entries not taken over) — "
                f"saves 0 right now; the full {full:,} tokens still load every turn")
    elif cur == "cli":
        line = (f"CLI 模式 — 0 常驻；全量 {full:,} token 不进上下文；已转发 {calls:,} 次"
                if zh else
                f"CLI — 0 resident; the full {full:,} tokens never load; "
                f"{calls:,} calls routed")
    elif cur == "serve":
        gw = int(f.get("gateway_tokens") or 0)
        line = (f"serve 模式 — 每轮固定约 {gw:,} token（对比全量 {full:,}）"
                if zh else
                f"serve — ~{gw:,} tokens/turn fixed (vs {full:,} for full schemas)")
    else:
        line = ("未配置服务器 —— 先跑 `mcptoon quickstart`"
                if zh else "no servers yet — run `mcptoon quickstart`")
    print(line)
    act = rec.get("one_action") or rec.get("reason")
    if act:
        print(("  下一步：" if zh else "  Next: ") + str(act))


def _cmd_mode(rest, fmt, head_n=0, max_chars=0, full=False):
    """Which delivery mode is running, what each costs, and which is cheapest.

    The three modes are `cli` (shell, zero resident, cheapest), `serve`
    (registered MCP gateway, small fixed per-turn cost) and `direct` (installed
    but not wired — the most expensive, and the default after a fresh install).
    The big "99%" saving is definition-side and both `cli` and `serve` deliver
    it; result compression is a rounding error.

    Usage:
        mcptoon mode
        mcptoon mode --json
        mcptoon mode recommend          Which mode this host should use, and one action
        mcptoon mode recommend --json   The same recommendation as JSON
    """
    from . import mode as mode_mod
    mode_mod.run(rest, fmt, head_n, max_chars, full)


def _cmd_statusline(rest, fmt, head_n=0, max_chars=0, full=False):
    """One compact badge line, safe to run every prompt from any host.

    Meant for a status bar or the top of a turn: `🎉 mcptoon · 9 tools (99%
    less) · ≈1.9B saved · 2,903 calls · cli`. Reads only cached figures and never
    spawns a server, so a host may call it on every prompt.

    Usage:
        mcptoon statusline
        mcptoon statusline --json
        mcptoon statusline --install     Wire it into Claude Code's status bar
        mcptoon statusline --uninstall   Remove exactly that entry again
        mcptoon statusline --check       Is it wired? (exit 1 if not)
    """
    from . import mode as mode_mod
    mode_mod.run_statusline(rest, fmt, head_n, max_chars, full)


def _cmd_stats(_rest, fmt, head_n=0, max_chars=0, full=False):
    """Token savings dashboard — shows how much mcptoon saves vs raw JSON.

    `head_n`/`max_chars`/`full` are the global output flags, threaded through so
    they are not silently ignored (this dashboard's `by_server` map is the record
    collection `--head` caps). See `_cmd_install` for why the three travel together.

    Usage:
        mcptoon stats              Human-readable dashboard
        mcptoon stats --json       JSON output
    """
    from . import schema_simplifier
    from .bench import _tokenizer

    manifest = manifest_mod.get_manifest(use_cache=True)
    usage = usage_mod.get_usage_stats()

    # One ruler for every savings figure in the CLI. This dashboard used to divide
    # character counts by 4 while `mcptoon status` used tiktoken, so the two
    # commands a user runs back-to-back answered "how much does this save?" with
    # two different numbers — and this one is literally titled the savings
    # dashboard. It was invisible until `stats` was added to `--help`, which is
    # its own lesson about discoverability hiding defects.
    encode, caliber, _exact = _tokenizer()

    def _tokens(text: str) -> int:
        return max(1, int(encode(text)))

    # Count tools & compute token savings
    total_tools = 0
    total_full_tokens = 0
    total_slim_tokens = 0
    by_server_full = {}
    by_server_slim = {}

    for server, tools in manifest.items():
        if not tools:
            continue
        server_full = 0
        server_slim = 0
        for t in tools:
            if "error" in t:
                continue
            total_tools += 1
            full_json = json.dumps(t, ensure_ascii=False)
            slim = schema_simplifier.simplify_tool_def(t)
            slim_json = json.dumps(slim, ensure_ascii=False)
            full_tok = _tokens(full_json)
            slim_tok = _tokens(slim_json)
            total_full_tokens += full_tok
            total_slim_tokens += slim_tok
            server_full += full_tok
            server_slim += slim_tok
        by_server_full[server] = server_full
        by_server_slim[server] = server_slim

    # NOTE: this deliberately sums per-tool measurements, which is exactly what
    # `mcptoon status` does — the two commands are now required to print the same
    # numbers for the same catalog. Do not "improve" one of them to measure the
    # whole manifest in a single dump: that is a different (and larger) quantity,
    # and having a third number that matches neither command is worse than having
    # one that matches both.
    saved = total_full_tokens - total_slim_tokens
    pct = (saved / total_full_tokens * 100) if total_full_tokens > 0 else 0
    # Same gateway figure the footer and `status` report, from the one helper —
    # three surfaces, one number (2026-09-26 audit).
    from . import footer as footer_mod
    gw_tokens, gw_pct = footer_mod.gateway_savings(total_full_tokens)
    # CLI mode credits a different fact: the catalog never becomes resident. Pull
    # the shared credit (None off the CLI path) so this dashboard stops leading a
    # CLI user with a serve number they are not living (same caliber rule as the
    # status/statusline/footer surfaces).
    cli_credit = footer_mod.cli_credit(footer_mod.facts())
    disabled = cfg.list_disabled_tools()

    if fmt == "json":
        data = {
            "total_tools": total_tools,
            # Kept under their original names so existing consumers do not break;
            # the values are now measured with the shared tokenizer instead of
            # chars/4, which is a correction rather than a contract change.
            "full_tokens_est": total_full_tokens,
            "slim_tokens_est": total_slim_tokens,
            "tokens_saved": saved,
            "savings_pct": round(pct, 1),
            "gateway_tokens": gw_tokens,
            "gateway_saved": (total_full_tokens - gw_tokens) if gw_tokens else None,
            "gateway_pct": gw_pct,
            "token_caliber": caliber,
            "delivery_mode": footer_mod.current_mode(),
            "cli_credit": cli_credit,
            "total_calls": usage["total_calls"],
            "success_rate": usage["success_rate"],
            "disabled_tools": len(disabled),
            "by_server": {s: {"full": by_server_full.get(s, 0), "slim": by_server_slim.get(s, 0)} for s in by_server_full},
        }
        print(output.render(output.stamp_schema(data), fmt="json", head_n=head_n,
                            max_chars=max_chars, full=full))
    else:
        print("╔══════════════════════════════════════════╗")
        print("║      mcptoon — Token Savings Dashboard   ║")
        print("╚══════════════════════════════════════════╝")
        print()
        print(f"  Tools discovered:     {total_tools}")
        print(f"  Full JSON tokens:     {total_full_tokens:,}")
        print(f"  Slim manifest tokens: {total_slim_tokens:,}")
        if gw_tokens and gw_pct is not None:
            print(f"  Gateway tokens:       {gw_tokens:,}  "
                  f"← what the agent loads by default")
        print(f"  ─────────────────────────────────")
        if gw_tokens and gw_pct is not None:
            print(f"  Tokens SAVED:         {total_full_tokens - gw_tokens:,} "
                  f"({gw_pct:.1f}%) via the gateway")
            print(f"                        {saved:,} ({pct:.1f}%) slim schemas only")
        else:
            print(f"  Tokens SAVED:         {saved:,} ({pct:.1f}%)")
        # The "via the gateway" headline above is a serve fact. On a CLI machine it
        # is not what the user is living — the real saving is that the whole
        # catalog never loads. Lead with that, and demote the gateway line to
        # "what you would load if you wired serve", so the dashboard stops
        # crediting a CLI user with a gateway number.
        if cli_credit:
            print(f"  CLI: 0 resident — the full {cli_credit['resident_avoided']:,} "
                  f"token catalog never enters context")
            print(f"       (a call pulls ~{cli_credit['per_call']:,} tokens of names "
                  f"to pick one schema)")
            print(f"       the 'via the gateway' line above applies only if you "
                  f"wire serve")
        elif footer_mod.current_mode() in ("direct", "serve-alongside"):
            # Not saving yet: the gateway pair above is what you WOULD save once
            # wired/taken over, not a saving happening now. Say so on the savings
            # dashboard itself — otherwise the "Tokens SAVED: …" line reads as a
            # live tally on a machine that is loading MORE than before install.
            if footer_mod.current_mode() == "serve-alongside":
                print("  NOTE: serve-alongside — the gateway is wired but the direct "
                      "entries are not taken over, so right now you save 0.")
                print("        → run `mcptoon sync --takeover` to route them through "
                      "the gateway")
            else:
                print("  NOTE: direct — installed but not wired, so right now you "
                      "save 0; the numbers above are what you WOULD save.")
                print("        → run `mcptoon sync --self` to wire serve, or use "
                      "`mcptoon call`")
        print(f"  Disabled tools:       {len(disabled)}")
        print(f"  Caliber:              {caliber}")
        print()
        if usage["total_calls"] > 0:
            print(f"  Usage: {usage['total_calls']} calls, {usage['success_rate']} success")
            if usage["by_server"]:
                print("  Top servers by usage:")
                for s, c in list(usage["by_server"].items())[:5]:
                    print(f"    {s:20s} {c} calls")
        print()
        if by_server_full:
            # These rows are the slim-schema caliber, not the gateway one — the
            # gateway withholds upstream schemas wholesale, so there is no honest
            # per-server split of it. Label it so the number under the gateway
            # headline is not read as the same thing (2026-09-26 polish pass).
            print("  Per-server token savings (slim schemas only):")
            for s in sorted(by_server_full):
                sf = by_server_full[s]
                ss = by_server_slim.get(s, 0)
                sp = ((sf - ss) / sf * 100) if sf > 0 else 0
                print(f"    {s:20s} {sf:>6,} → {ss:>6,}  (-{sp:.0f}%)")
        # The dashboard is an aggregate: its headline numbers are sums over every
        # server, so `--head` (documented as a global flag) cannot cap them without
        # making the totals lie. Rather than silently ignore it, say so — a flag
        # that is accepted and does nothing is the exact silent-degradation this
        # project treats as a defect. Only when a cap was actually requested.
        if head_n and head_n > 0:
            print()
            print(f"  note: --head {head_n} does not apply to this dashboard "
                  f"(the totals are sums over all servers).")


def _cmd_status(_rest, fmt):
    """One screen: what's here, what it saves, and how to undo it.

    The "is it doing anything?" answer for a tool that installs silently. Four
    facts a newcomer needs and nothing else; every number is read, never guessed.
    The savings figure uses the SAME caliber as `bench` (tiktoken cl100k_base) —
    quoting a different number here than `bench` prints is how a tool loses the
    argument that its numbers are real.

    Usage:
        mcptoon status
        mcptoon status --json
    """
    from . import schema_simplifier
    from .bench import _tokenizer

    servers = cfg.list_servers()
    n_servers = len(servers)

    # One tokenizer, one caliber — the same call `bench` makes.
    encode, caliber, _exact = _tokenizer()

    # Tools + savings, from the cached catalog (never spawns servers).
    try:
        manifest = manifest_mod.get_manifest(use_cache=True)
    except Exception:
        manifest = {}

    total_tools = 0
    full_tokens = 0
    slim_tokens = 0
    for _server, tools in manifest.items():
        if not tools:
            continue
        for t in tools:
            if not isinstance(t, dict) or "error" in t:
                continue
            total_tools += 1
            full_tokens += max(1, int(encode(json.dumps(t, ensure_ascii=False))))
            slim_tokens += max(1, int(encode(json.dumps(
                schema_simplifier.simplify_tool_def(t), ensure_ascii=False))))
    saved = max(0, full_tokens - slim_tokens)
    pct = round(saved / full_tokens * 100, 1) if full_tokens else 0.0

    # The number a user actually wants — what installing mcptoon removes from the
    # agent's context — is the compact gateway, not the slim-schema saving. Same
    # helper the footer uses, so the two surfaces cannot disagree (2026-09-26).
    from . import footer as footer_mod
    gw_tokens, gw_pct = footer_mod.gateway_savings(full_tokens)

    try:
        stats = usage_mod.get_usage_stats()
        calls = int(stats.get("total_calls", 0))
        routed_calls = int(stats.get("routed_calls", calls))
        native_calls = int(stats.get("native_calls", 0))
    except Exception:
        calls = 0
        routed_calls = 0
        native_calls = 0

    # Is the gateway itself registered in any agent config? Read-only check.
    wired = _gateway_wired_in()
    # The delivery mode is a stricter question than `wired`: `not wired` is true for
    # BOTH cli and direct, but they save opposite amounts. cli = shell host, catalog
    # never loads (real saving); direct = installed, agent loads the full catalog
    # native (no saving). Branching the human view on `not wired` made direct claim
    # the CLI "0 resident / never load" truth it does not live (2026-10-20).
    mode_now = footer_mod.current_mode()
    # The recommendation (which mode this host should use + one action), so the
    # JSON view carries the same fix the human "Recommended" line shows.
    try:
        from . import mode as mode_mod
        _rec = mode_mod.recommend(lng=cfg.resolve_lang())
        _rec_now = (_rec or {}).get("recommended")
        _rec_action = (_rec or {}).get("one_action") or (_rec or {}).get("reason")
    except Exception:
        _rec_now, _rec_action = None, None

    # Skills are the other half of the catalog, and this screen used to report
    # only the MCP half — a manager that manages two things naming one. Read from
    # the built index (the same count `skills list --all` prints, recursive and
    # de-duplicated); never re-scan here, because a status command must not walk
    # the filesystem. Absent index → no row, never a guessed 0.
    try:
        from . import skills as skills_mod
        n_skills = len(skills_mod.load_index().get("skills") or []) or None
    except Exception:
        n_skills = None
    # The index snapshot can lag the live catalog: `status` reads the built index
    # (no filesystem walk — a status command must stay cheap), while `bench` and
    # the footer re-measure live. Reported 2026-10-17: status said 464 while the
    # footer said 469, with no hint which was current. Read the footer's cached
    # live count (a tiny sidecar, no walk) and flag when the index is behind, so
    # the two numbers can never disagree silently.
    skills_live = None
    if n_skills:
        try:
            _figs = skills_mod._load_skill_token_cache().get("figures") or {}
            skills_live = int(_figs.get("count") or 0) or None
        except Exception:
            skills_live = None

    # The presence answer: is mcptoon being used at all, and by which agent?
    # Read off the activity ledger (who/when), never the counter (how many). A
    # `status` that only talks about savings cannot answer the question a person
    # who installed this and forgot actually has. Cheap: the ledger is a small
    # local file, no servers touched.
    try:
        act = usage_mod.activity_summary()
    except Exception:
        act = {"entries": 0, "last_host": None, "last_ts": None,
               "today_calls": 0, "hosts": {}, "last_fail": None}

    if fmt == "json":
        print(json.dumps(output.stamp_schema({
            "servers": n_servers,
            "tools": total_tools,
            "skills": n_skills,
            "skills_source": "index" if n_skills else None,
            # The human view flags "index may be stale" when the built index lags
            # the live catalog; a script consuming --json needs the same signal or
            # it will trust a stale count. `skills_stale` is True only when the
            # index count is known to be behind the live count.
            "skills_live": skills_live,
            "skills_stale": bool(n_skills and skills_live and skills_live > n_skills),
            "tokens_full": full_tokens,
            "tokens_slim": slim_tokens,
            "tokens_saved_est": saved,
            "savings_pct": pct,
            "gateway_tokens": gw_tokens,
            "gateway_pct": gw_pct,
            "token_caliber": caliber,
            "calls_recorded": calls,
            "calls_routed": routed_calls,
            "calls_native": native_calls,
            "gateway_registered": wired,
            # The CLI-credit figures, so a script sees the same "0 resident" truth
            # the human view now prints in CLI mode. `delivery_mode` names which
            # caliber the numbers belong to; `resident_avoided` is the full catalog
            # a CLI call never loads. Both are additive keys — a serve machine
            # simply reads resident_avoided alongside its gateway figure.
            "delivery_mode": mode_now,
            "resident_avoided": full_tokens if mode_now == "cli" else 0,
            # The alongside detail (gateway wired but direct entries not taken
            # over): a script needs the count, not just the mode name.
            "direct_entries": _direct_entries_now(),
            "cli_credit": footer_mod.cli_credit(footer_mod.facts()),
            "recommended": _rec_now,
            "one_action": _rec_action,
            "footer_enabled": cfg.footer_enabled(),
            "presence_enabled": cfg.presence_enabled(),
            "receipt_enabled": cfg.receipt_enabled(),
            "activity_entries": act.get("entries", 0),
            "activity_today": act.get("today_calls", 0),
            "activity_today_skills": act.get("today_skill_dist", 0),
            "last_host": act.get("last_host"),
            "last_used_ts": act.get("last_ts"),
            "last_fail": act.get("last_fail"),
        }), indent=2, ensure_ascii=False))
        return

    line = "─" * 54
    print(line)
    print("  mcptoon — status")
    print(line)
    # Answer "which mode should this host use?" right here, so a user reading the
    # one-screen status does not have to know `mode recommend` exists. Only shown
    # when there is a real recommendation with an action (never on a clean cli
    # machine whose recommendation is "nothing to do").
    try:
        if _rec_now and _rec_action:
            print(f"  Recommended        : {_rec_now} — {_rec_action}")
    except Exception:
        pass
    if n_servers:
        print(f"  Managing           : {n_servers} MCP servers, {total_tools} tools")
    else:
        print("  Managing           : nothing yet — run `mcptoon quickstart`")
    if n_skills:
        print(f"  Skills in catalog  : {n_skills} (recursive, deduped)  [skills index]")
        if skills_live and skills_live > n_skills:
            # The index is behind the live catalog. Say so, with the fix — the
            # alternative is two surfaces quietly quoting 464 and 469.
            print(f"                       (live catalog has {skills_live} — index may be "
                  f"stale, run `mcptoon skills index`)")
    if total_tools:
        if mode_now == "direct":
            # Installed but not wired: the agent loads the full catalog natively and
            # saves nothing. Name the cost and the one action that turns it on — the
            # old view fell into the "not wired" branch and printed the CLI "0
            # resident" line, which is a saving a direct machine does not have.
            print(f"  Tool definitions   : full {full_tokens:,} tokens load natively "
                  f"— nothing is saved yet  [{caliber}]")
            print(f"                       (direct = installed, not wired; run "
                  f"`mcptoon sync --self` to save, or use `mcptoon call`)")
        elif mode_now == "serve-alongside":
            # Gateway wired, but host configs still list the upstream entries it
            # manages, so those hosts load the full catalog directly and the
            # gateway saves nothing yet. Printing the "→ gw_tokens (saved 99%)"
            # pair here would credit mcptoon for a saving it is not delivering.
            _de = 0
            try:
                _de = int(mode_mod.detect().get("direct_entries") or 0)
            except Exception:
                _de = 0
            print(f"  Tool definitions   : full {full_tokens:,} tokens still load "
                  f"natively — nothing is saved yet  [{caliber}]")
            print(f"                       (serve-alongside = gateway wired but "
                  f"{_de:,} direct entr{'y' if _de == 1 else 'ies'} not taken over; "
                  f"run `mcptoon sync --takeover`)")
        elif gw_tokens and gw_pct is not None and not wired:
            # CLI mode: the gateway is NOT wired into an agent, so the "→ gw_tokens
            # via the gateway" story is a serve fact this machine is not living.
            # Print the CLI truth instead: the catalog never sits resident, and a
            # call pulls only the name index. Reporting the gateway pair here would
            # credit CLI for a saving it delivers a different way.
            _idx = footer_mod.facts().get("name_index_tokens") or 0
            _per = (f"~{_idx:,} tokens of names to pick one" if _idx
                    else "the one schema it needs")
            print(f"  Tool definitions   : 0 resident — full {full_tokens:,} tokens "
                  f"never load; a call pulls {_per}  [{caliber}]")
            print(f"                       (serve mode instead loads a fixed "
                  f"{gw_tokens:,}; you are on the cheaper CLI path)")
        elif gw_tokens and gw_pct is not None:
            _gw_saved = footer_mod.display_pct(full_tokens - gw_tokens, full_tokens)
            _slim_saved = footer_mod.display_pct(saved, full_tokens)
            print(f"  Tool definitions   : {full_tokens:,} → {gw_tokens:,} tokens "
                  f"via the gateway (saved {_gw_saved}%)  [{caliber}]")
            print(f"                       (slim schemas alone: {slim_tokens:,}, "
                  f"{_slim_saved}%)")
        else:
            _slim_saved = footer_mod.display_pct(saved, full_tokens)
            print(f"  Tool definitions   : {full_tokens:,} → {slim_tokens:,} tokens "
                  f"(saved {saved:,}, {_slim_saved}%)  [{caliber}]")
    print(f"  Calls recorded     : {calls}")
    # Two different things, once behind one number: calls routed to *upstream*
    # tools vs the gateway's own native tools (skill distribution lives here).
    # A user deciding whether mcptoon is "doing anything for my agent" cares which.
    if calls:
        print(f"                       {routed_calls} routed to tools, "
              f"{native_calls} via mcptoon's own tools (skills, manifest, inspect)")
    # Presence: who is using it and when — the question `Calls recorded` alone
    # cannot answer. "No routed calls yet" is itself the useful fact (it means the
    # gateway is installed but nothing has gone through it).
    if act.get("entries"):
        last_ts = act.get("last_ts")
        when = (time.strftime("%Y-%m-%d %H:%M", time.localtime(last_ts))
                if isinstance(last_ts, (int, float)) else "—")
        who = act.get("last_host") or "CLI"
        print(f"  Last used          : {who} at {when}"
              f"  ·  {act.get('today_calls', 0)} today  ·  see `mcptoon activity`")
        # "Did it hand me a capability today?" — the skill-distribution moment,
        # which is what a user installing mcptoon for its skills actually cares
        # about, distinct from a generic routed call. Only shown when >0.
        tsk = act.get("today_skill_dist", 0)
        if tsk:
            print(f"  Skills today       : {tsk} distribution"
                  f"{'' if tsk == 1 else 's'}  ·  see `mcptoon activity`")
        # "Did it break recently?" — a separate question from "is it being used".
        # Only shown when a call actually failed; names the agent, the tool, when,
        # and the short reason so the user is not sent digging.
        lf = act.get("last_fail")
        if lf:
            fts = lf.get("ts")
            fwhen = (time.strftime("%Y-%m-%d %H:%M", time.localtime(fts))
                     if isinstance(fts, (int, float)) else "—")
            fwho = lf.get("host") or "CLI"
            ftool = f"{lf.get('server', '')}:{lf.get('tool', '')}".strip(":")
            freason = (lf.get("err") or "").strip()
            tail = f"  ({freason})" if freason else ""
            print(f"  Last failure       : {fwho} {ftool} at {fwhen}{tail}")
        if _installed_but_silent(act):
            print("  ⚠ Nothing routed in over a day. If your agent stopped using "
                  "mcptoon, run `mcptoon doctor`.")
    else:
        print("  Last used          : no routed calls yet — let an agent use a tool,"
              " then `mcptoon activity`")
        # The one case that looks identical to "quietly working" but is not:
        # wired into an agent, yet nothing has ever come through. Say the
        # possibility out loud — softly, as a warning line, never an error, and
        # never changing the exit code — so a broken wiring gets noticed.
        if _installed_but_silent(act):
            print("  ⚠ Wired into an agent, but no call has come through. If your "
                  "agent never uses it, run `mcptoon doctor`.")
    if wired:
        print("  Gateway in agents  : yes — agents can see mcptoon itself")
    else:
        print("  Gateway in agents  : no — run `mcptoon sync --self` to register it")
    # Which delivery mode is running, and whether a cheaper one exists. This is
    # the direct answer to "am I saving anything?" — a fresh install sits in
    # `direct` (installed, not wired) and saves nothing, which `status` used to
    # never say out loud. Read-only, cache-only (mode.detect never spawns a
    # server), so it stays cheap.
    try:
        from . import mode as mode_mod
        _m = mode_mod.detect()
        _mode_label = {
            "cli": "CLI (shell) — cheapest, zero resident cost",
            "serve": "serve (MCP gateway) — small fixed per-turn cost",
            "serve-alongside": "serve-alongside (gateway wired, direct entries not "
                               "taken over) — saves nothing yet",
            "direct": "direct (not wired) — most expensive, saves nothing yet",
            "empty": "no servers configured yet",
        }.get(_m["mode"], _m["mode"])
        print(f"  Mode               : {_mode_label}")
        if _m["mode"] == "direct":
            print("                       → run `mcptoon sync --self`, or use "
                  "`mcptoon call` — see `mcptoon mode`")
        elif _m["mode"] == "serve-alongside":
            _de = int(_m.get("direct_entries") or 0)
            print(f"                       → {_de:,} direct entr"
                  f"{'y' if _de == 1 else 'ies'} still load natively; run "
                  "`mcptoon sync --takeover` to route them through the gateway "
                  "— see `mcptoon mode`")
    except Exception:
        pass
    print(line)
    print("  Take it back any time:")
    print("    mcptoon off          remove the gateway from your agents")
    print("    mcptoon restore      drop the gateway and put your servers back")
    print("    mcptoon uninstall    full cleanup (preview with --dry)")
    print("  Prove the numbers: mcptoon bench   ·   what it did: mcptoon activity")
    print("")


def _cmd_off(rest, fmt):
    """Remove the gateway entry from every agent config — the reversible "off".

    Keeps mcptoon installed and your server definitions intact; it only stops
    the gateway from being handed to your agents. `mcptoon sync --self` puts it
    back. This is the answer to "I want it to stop touching my agents".

    Usage:
        mcptoon off
        mcptoon off --dry     preview without writing
    """
    from .sync import remove_gateway_from_all

    dry_run = "--dry" in rest or "--dry-run" in rest
    results = remove_gateway_from_all(dry_run=dry_run)
    # `removed` means "the gateway entry was found", not "it is gone": a write that
    # failed still reports removed=True with written=False (sync.py). Counting only
    # `removed` made `off` print "Done: N agent(s) no longer see mcptoon" while the
    # file still held the entry (reproduced 2026-10-02). A real removal needs both.
    present = [r for r in results if r.get("removed") and (dry_run or r.get("written"))]
    failed = [r for r in results if r.get("removed") and not dry_run and not r.get("written")]

    if fmt == "json":
        print(json.dumps({
            "dry_run": dry_run,
            "removed_from": [r.get("agent") for r in present],
            "count": len(present),
            "failed": [{"agent": r.get("agent"), "error": r.get("error")} for r in failed],
        }, indent=2, ensure_ascii=False))
        return

    line = "─" * 54
    print(line)
    print("  mcptoon off" + ("  (DRY RUN — nothing written)" if dry_run else ""))
    print(line)
    if not present and not failed:
        print("  Gateway is not registered in any agent. Nothing to remove.")
    else:
        for r in present:
            verb = "would remove" if dry_run else "removed"
            print(f"  {'→' if dry_run else '✓'} {r.get('agent_name', r.get('agent')):25s} {verb} the gateway entry")
        for r in failed:
            print(f"  ✗ {r.get('agent_name', r.get('agent')):25s} could not be written — the gateway entry is STILL there")
            if r.get("error"):
                print(f"      {str(r['error'])[:100]}")
        print("")
        if dry_run:
            print(f"  Preview: {len(present)} agent(s) would lose the gateway entry.")
        elif failed:
            print(f"  Done: {len(present)} agent(s) no longer see mcptoon; "
                  f"{len(failed)} could not be updated (see above).")
            print("  Your servers are untouched.")
        else:
            print(f"  Done: {len(present)} agent(s) no longer see mcptoon. Your servers are untouched.")
            print("  Put the gateway back with: mcptoon sync --self")
            # `off` only removes the gateway. If a takeover dropped the user's
            # direct server entries, they are NOT back yet — point at the command
            # that actually returns them, so `off` is not mistaken for the undo.
            try:
                from .sync import restore_plan
                if restore_plan():
                    print("  If a takeover removed your own server entries, bring them")
                    print("  back with: mcptoon restore")
            except Exception:
                pass
    print(line)
    print("")


def _safe_rmtree(path) -> bool:
    """Delete a directory only if it is one mcptoon itself created.

    A destructive command should not be one bad constant away from deleting
    something else. If `MCPTOON_CACHE_DIR` (or a future refactor) ever resolved to
    a parent — the user's home, a drive root — an unguarded `rmtree` would take the
    user's world with it. `mcptoon` is the only directory name this project
    creates, so anything else is refused and reported rather than deleted.

    Returns True when the directory was removed.
    """
    p = Path(path)
    if p.name != "mcptoon":
        return False
    import shutil

    shutil.rmtree(p, ignore_errors=True)
    return not p.exists()


# The two files that hold the running savings tally. `--keep-history` clears
# everything else in the cache (the schema cache is rebuildable in seconds) but
# leaves these, so the number the user watched climb survives the uninstall.
_HISTORY_FILES = ("usage.json", "activity.jsonl")


def _safe_clear_keep_history(path) -> bool:
    """Empty a cache directory but keep the savings tally — same ownership guard.

    Used by `uninstall --keep-history`. Removes every entry under the directory
    except `usage.json` and `activity.jsonl`; if anything is left over besides
    those two (a file we could not delete), returns False so the caller reports it
    rather than claiming a clean sweep.

    Returns True when the directory is gone or now holds only the history files.
    """
    p = Path(path)
    if p.name != "mcptoon":
        return False
    import shutil

    if not p.exists():
        return True
    for child in list(p.iterdir()):
        if child.name in _HISTORY_FILES:
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            pass
    leftovers = [c for c in p.iterdir() if c.name not in _HISTORY_FILES]
    return not leftovers


def _cmd_restore(rest, fmt):
    """Put every agent config back to the state before mcptoon edited it.

    This is the real "undo the takeover". `mcptoon off` only removes the gateway
    entry; it does not bring back the servers `sync --takeover` dropped, because
    those were removed from the live file and survive only in the `<config>.bak`
    mcptoon wrote first. `restore` copies that backup back, so the original
    servers return and the gateway entry is gone — the pre-install state.

    Usage:
        mcptoon restore
        mcptoon restore --dry            preview without writing
        mcptoon restore --agent cursor   one host only
        mcptoon restore --yes            skip the interactive confirmation
    """
    from .sync import restore_all_from_backup, restore_agent_from_backup, restore_plan

    dry_run = "--dry" in rest or "--dry-run" in rest
    assume_yes = "--yes" in rest or "-y" in rest
    agent_id = None
    for i, a in enumerate(rest):
        if a == "--agent" and i + 1 < len(rest):
            agent_id = rest[i + 1]
            break
        elif a.startswith("--agent="):
            agent_id = a.split("=", 1)[1]
            break

    plan = restore_plan(agent_id)
    line = "─" * 54
    if fmt == "json":
        if dry_run:
            print(json.dumps({"dry_run": True, "plan": plan}, indent=2, ensure_ascii=False))
            return
        results = (restore_agent_from_backup(agent_id, dry_run=False)
                   if agent_id else restore_all_from_backup(dry_run=False))
        # Same filter as the text branch below: `restored` alone means "there was
        # something to undo", not "a file changed". A host with restored=True,
        # written=False (e.g. "config unreadable; left unchanged") was counted by
        # `--json` and omitted from "Done: N" by the plain form — two answers for
        # one run (2026-10-02). Report the written ones and the failures.
        present = [r for r in results if r.get("restored") and r.get("written")]
        failed = [r for r in results if r.get("restored") and r.get("error")]
        print(json.dumps({
            "restored": [r.get("agent") for r in present],
            "count": len(present),
            "failed": [{"agent": r.get("agent"), "error": r.get("error")} for r in failed],
        }, indent=2, ensure_ascii=False))
        return

    print(line)
    print("  mcptoon restore" + ("  (DRY RUN — nothing written)" if dry_run else ""))
    print(line)
    if not plan:
        print("  Nothing to restore — no config has a differing `.bak`.")
        print("  (If mcptoon has never edited a config, there is nothing to undo.)")
        print(line)
        print("")
        return
    print("  This drops the mcptoon gateway entry and puts back the servers it")
    print("  removed. Anything you added since is left alone:")
    for row in plan:
        print(f"    · {row['agent_name']}")
        print(f"        {row['path']}")
    print("")
    if dry_run:
        print(f"  Preview: {len(plan)} config(s) would be restored.")
        print(line)
        print("")
        return
    if not assume_yes:
        if not sys.stdin.isatty():
            print("  Refusing to overwrite configs without confirmation. Re-run with --yes.")
            print(line)
            print("")
            return
        try:
            answer = input("  Restore them from backup? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  Cancelled — nothing was restored.")
            print(line)
            print("")
            return
        print("")

    results = (restore_agent_from_backup(agent_id, dry_run=False)
               if agent_id else restore_all_from_backup(dry_run=False))
    present = [r for r in results if r.get("restored") and r.get("written")]
    failed = [r for r in results if r.get("restored") and r.get("error")]
    for r in present:
        print(f"  ✓ {r.get('agent_name', r.get('agent')):25s} restored from backup")
    if failed:
        for r in failed:
            print(f"  ✗ {r.get('agent_name', r.get('agent')):25s} {r.get('error')}")
    print("")
    print(f"  Done: {len(present)} config(s) put back. Re-run `mcptoon quickstart`")
    print("  to re-register the gateway when you want mcptoon on again.")
    print(line)
    print("")


def _uninstall_history_summary(cache_dirs=None) -> dict | None:
    """What the accumulated savings history holds, or None when there is none.

    `uninstall` deletes the whole cache directory, and that directory is where the
    running tally lives (`usage.json`: every routed call with its token count and
    timestamp; `activity.jsonl`: the recent ledger). Deleting it is correct for a
    clean exit, but the plan never SAID so — a user who has watched "≈1.9B saved"
    tick up for weeks was told which files vanish, never that the *number they came
    to trust* vanishes with them. This reads just enough to put that number in the
    plan, in the same units the footer uses.

    `cache_dirs` is resolved by the caller through `cfg.state_paths()`, which honours
    the `MCPTOON_CACHE_DIR` override at CALL time. Reading `usage._USAGE_FILE` here
    would be the import-time-constant bug the reversible-command tests exist to
    catch: that constant is frozen at import and ignores the env, so a sandboxed
    `uninstall` would read the developer's real tally. Cache-only, never spawns a
    server (same contract as `footer.facts`).
    """
    import json
    from datetime import datetime

    if not cache_dirs:
        return None
    path = None
    for d in cache_dirs:
        candidate = Path(d) / "usage.json"
        if candidate.exists():
            path = candidate
            break
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    calls = data.get("calls") or []
    total = int(data.get("total") or len(calls) or 0)
    if total <= 0:
        return None
    first_ts = None
    for rec in calls:
        ts = rec.get("ts") if isinstance(rec, dict) else None
        if isinstance(ts, (int, float)):
            first_ts = ts if first_ts is None else min(first_ts, ts)
    days = None
    first_date = None
    if first_ts:
        try:
            first_dt = datetime.fromtimestamp(first_ts)
            first_date = first_dt.strftime("%Y-%m-%d")
            days = max(0, (datetime.now() - first_dt).days)
        except (OSError, OverflowError, ValueError):
            pass
    return {"calls": total, "first_date": first_date, "days": days}


def _cmd_uninstall(rest, fmt):
    """Full, reversible cleanup — print exactly what will be removed, then remove it.

    A tool the user cannot get rid of is indistinguishable from one that never
    asked. This is the exit door: it removes the gateway from every agent config
    and deletes mcptoon's own files, and it PRINTS the plan first so the user can
    audit it. `--dry` shows the same plan and stops.

    Usage:
        mcptoon uninstall
        mcptoon uninstall --dry       preview only
        mcptoon uninstall --yes       skip the interactive confirmation
        mcptoon uninstall --keep-history   delete the cache but keep the savings tally
    """
    from .sync import remove_gateway_from_all

    dry_run = "--dry" in rest or "--dry-run" in rest
    assume_yes = "--yes" in rest or "-y" in rest
    keep_config = "--no-keep-config" not in rest
    keep_history = "--keep-history" in rest

    # mcptoon's own files, resolved through config.state_paths() so env overrides
    # (MCPTOON_CONFIG_FILE and friends) are honoured. Crucially this NEVER deletes
    # your server definitions by default: config.json / config.toml hold the MCP
    # servers *you* configured. Deleting a user's config while claiming to "clean
    # up" is exactly the surprise this tool exists to avoid.
    paths = cfg.state_paths()
    bookkeeping = paths["bookkeeping"]
    server_configs = paths["servers"]
    if not keep_config:
        bookkeeping = [*bookkeeping, *server_configs]

    agents = remove_gateway_from_all(dry_run=True)
    agent_hits = [r for r in agents if r.get("removed")]
    dirs_present = [d for d in paths["cache"] if Path(d).exists()]
    # Split bookkeeping into real directories vs files by asking the filesystem,
    # NOT by suffix: dotfiles like `.welcome` have an empty suffix and would be
    # misclassified as directories. Only `STATE_DIR/handlers` is a directory today;
    # it must be removed as a tree, everything else as a single file.
    bookkeeping_dirs = [Path(p) for p in bookkeeping if Path(p).is_dir()]
    files_present = [f for f in bookkeeping if not Path(f).is_dir() and Path(f).exists()]
    config_kept = [f for f in server_configs if Path(f).exists()]

    line = "─" * 54
    print(line)
    print("  mcptoon uninstall" + ("  (DRY RUN — nothing removed)" if dry_run else ""))
    print(line)
    print("  This will:")
    if agent_hits:
        for r in agent_hits:
            print(f"    · remove the gateway entry from {r.get('agent_name', r.get('agent'))}"
                  f"  ({r.get('path')})")
    else:
        print("    · (no agent config currently has the gateway entry)")
    for d in dirs_present:
        if keep_history:
            print(f"    · clear directory  {d}  (KEEPING usage.json + activity.jsonl — "
                  f"your savings history)")
        else:
            print(f"    · delete directory  {d}")
    for f in files_present:
        print(f"    · delete file       {f}")
    for d in bookkeeping_dirs:
        print(f"    · delete directory  {d}")
    if config_kept:
        kept_names = ", ".join(Path(f).name for f in config_kept)
        print(f"    · KEEP {kept_names}  (your server definitions — delete with --no-keep-config)")
    if (not dirs_present and not files_present and not bookkeeping_dirs
            and not agent_hits and not config_kept):
        print("    · nothing to remove — mcptoon left no trace here")
    print("")

    # The half the plan never said: what the user actually loses. A number they
    # watched climb for weeks is the whole reason they kept the tool; deleting it
    # without a word is the surprise this command exists to avoid.
    history = (_uninstall_history_summary(dirs_present)
               if dirs_present and not keep_history else None)
    if history:
        print("  You will lose:")
        span = ""
        if history.get("days") is not None and history.get("first_date"):
            span = f" over {history['days']} day(s) since {history['first_date']}"
        print(f"    · your savings history — {history['calls']:,} routed call(s){span}")
        print("      (the number in `mcptoon report`; gone with the cache)")
        print("      keep it with: mcptoon uninstall --keep-history")
        print("")
    elif keep_history and dirs_present:
        print("  Your savings history (usage.json + activity.jsonl) is kept.")
        print("")

    print("  Your own MCP server definitions are never touched (unless you pass")
    print("  --no-keep-config).")
    print(line)

    if dry_run:
        print("  Dry run — nothing was removed. Re-run without --dry to apply.")
        print("")
        return

    if not assume_yes:
        # Non-interactive stdin (CI, piped) means we cannot ask: refuse rather
        # than delete silently. --yes is the explicit opt-in.
        #
        # Note this guard is a courtesy, not the safety property. On Windows the NUL
        # device reports `isatty() == True`, so `stdin=DEVNULL` slips past it and
        # reaches the prompt below, where EOF makes the answer empty — which is not
        # "yes". Both routes refuse; neither deletes. Keep it that way: do not treat
        # `isatty()` as proof that somebody is there to answer.
        if not sys.stdin.isatty():
            print("  Refusing to delete without confirmation. Re-run with --yes.")
            print("")
            return
        try:
            answer = input("  Remove all of the above? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  Cancelled — nothing was removed.")
            print("")
            return

    removed_agents = remove_gateway_from_all(dry_run=False)
    # Count only writes that actually landed. `removed` means "the entry was
    # found", so counting it reported success for a failed write (same bug as
    # `off`, 2026-10-02).
    n_agents = sum(1 for r in removed_agents
                   if r.get("removed") and r.get("written"))
    failed_agents = [r for r in removed_agents
                     if r.get("removed") and not r.get("written")]
    refused = []
    for d in dirs_present:
        if keep_history:
            ok = _safe_clear_keep_history(d)
        else:
            ok = _safe_rmtree(d)
        if not ok:
            refused.append(d)
    # Generated handler dir(s) — removed as a whole tree, like the cache dirs but
    # never "kept for history" (handlers are regenerable, not a tally).
    for d in bookkeeping_dirs:
        if d.exists() and not _safe_rmtree(str(d)):
            refused.append(str(d))
    # Count only files that are actually gone. The loop swallowed OSError, so a
    # file that could not be deleted was still counted in "Deleted ... N file(s)".
    undeleted = []
    for f in files_present:
        try:
            Path(f).unlink(missing_ok=True)
        except OSError:
            pass
        if Path(f).exists():
            undeleted.append(f)
    n_files = len(files_present) - len(undeleted)
    print("")
    print(f"  ✓ Removed the gateway from {n_agents} agent config(s).")
    for r in failed_agents:
        print(f"  ✗ {r.get('agent_name', r.get('agent'))} — the gateway entry is STILL there")
        if r.get("error"):
            print(f"      {str(r['error'])[:100]}")
    n_dirs = len(dirs_present) - len(refused)
    if keep_history and n_dirs:
        print(f"  ✓ Cleared {n_dirs} cache director{'y' if n_dirs == 1 else 'ies'} "
              f"(kept your savings history) and deleted {n_files} file(s).")
    else:
        print(f"  ✓ Deleted {n_dirs} director{'y' if n_dirs == 1 else 'ies'} "
              f"and {n_files} file(s).")
    for d in refused:
        print(f"  ! Refused to delete {d} — not a directory mcptoon owns.")
    for f in undeleted:
        print(f"  ! Could not delete {f}")
    if config_kept:
        print(f"  ✓ Kept your server definitions: {', '.join(Path(f).name for f in config_kept)}")
    if keep_history and n_dirs:
        print("  ✓ Kept your savings history — `mcptoon report` still shows the running total.")
    print("  mcptoon the package is still installed — remove it with:")
    print("    pip uninstall mcptoon")
    print(line)
    print("")


def _installed_but_silent(act: dict) -> bool:
    """True when the gateway is wired into an agent but has recorded nothing for
    over a day — the "quietly working" vs "quietly broken" ambiguity.

    A user who installs mcptoon and then sees no sign of it cannot tell those two
    apart, and the honest, non-alarming answer is to name the possibility rather
    than stay mute. Returns False as soon as there is any routed call (even one),
    so a working install never nags, and requires the gateway to actually be wired
    in (a config with nothing registered is not "broken", it is unconfigured).
    """
    try:
        if not act.get("entries"):
            return _gateway_wired_in()
        last_ts = act.get("last_ts")
        if not isinstance(last_ts, (int, float)):
            return False
        return (time.time() - last_ts) > 24 * 3600
    except Exception:
        return False


def _direct_entries_now() -> int:
    """How many direct server entries `sync --takeover` would still remove (0 if none).

    Read-only and cache-free (``takeover_plan`` walks the agent configs, ~1.7 ms,
    never spawns a server). The `status --json` payload carries it so a script can
    see the `serve-alongside` count without parsing the mode name. Best-effort: any
    failure reads as 0 rather than breaking `status`.
    """
    try:
        from . import mode as mode_mod
        return int(mode_mod.detect().get("direct_entries") or 0)
    except Exception:
        return 0


def _gateway_wired_in() -> bool:
    """True if `mcptoon serve` appears as a server entry in any agent config.

    Read-only and best-effort: a malformed agent config is treated as "not wired"
    rather than crashing the status command.
    """
    from .sync import (SELF_SERVER_NAME, _claude_desktop_path, _cline_path,
                       _cursor_path, _vscode_copilot_path, _windsurf_path)
    paths = [*_cursor_path(), _claude_desktop_path(), _cline_path(),
             _windsurf_path(), _vscode_copilot_path()]
    for path in paths:
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        # Cursor/Claude/Cline/Windsurf: {"mcpServers": {...}}; VS Code: {"mcp": {"servers": {...}}}
        for section in (data.get("mcpServers"), (data.get("mcp") or {}).get("servers")):
            if isinstance(section, dict) and SELF_SERVER_NAME in section:
                return True
    return False


def _cmd_config(rest, fmt, head_n=0, max_chars=0, full=False):
    """Read or write gateway settings (footer, welcome, lang).

    `head_n`/`max_chars`/`full` are the global output flags, forwarded so
    `config --json` honours them. See `_cmd_install` for why they travel together.

    Usage:
        mcptoon config                 Show every setting
        mcptoon config get <key>       Print one value
        mcptoon config set <key> <v>   Persist one value
        mcptoon config unset <key>     Forget one value (back to its default)
        mcptoon config reset           Forget every override (all defaults)
    """
    from .config import (SETTING_DEFAULTS, VALID_LANGS, load_settings,
                         reset_settings, resolve_lang, set_setting, unset_setting)

    action = rest[0].lower() if rest else "show"

    if action in ("", "show", "list"):
        values = load_settings()
        if fmt == "json":
            print(output.render(values, fmt="json", head_n=head_n,
                                max_chars=max_chars, full=full))
            return
        print("mcptoon settings")
        for key in sorted(values):
            print(f"  {key:12s} = {values[key]}")
        print()
        print("  footer on|off controls the one-line token-savings disclosure.")
        print("  presence on|brief|off controls the short \"mcptoon routed N calls\""
              " line after a command that used it;")
        print("    separate from footer — turn off savings, keep the usage notice,"
              " or the reverse.")
        print("  lang auto|zh|en picks the language of that line;"
              " auto follows the OS language.")
        print("  compress smart|off|toon controls result compression;"
              " smart (default) shrinks redundant results.")
        print("  select.engine lexical|command picks how `mcptoon select` ranks"
              " tools for a task;")
        print("    lexical (default) is built in and offline, command runs"
              " select.command yourself.")
        return

    if action == "get":
        if len(rest) < 2:
            _err("Usage: mcptoon config get <key>")
            sys.exit(1)
        key = rest[1].strip().lower()
        if key not in SETTING_DEFAULTS:
            # An unknown key is an error: a scripted `mcptoon config get <key>`
            # must not read as success (and print nothing useful) when the key
            # does not exist. `config set` already exits 1 on the same mistake.
            _err(f"Unknown setting: {key}. Known: {', '.join(sorted(SETTING_DEFAULTS))}")
            # Same "did you mean" the command/option parsers use, so a near-miss
            # key (`footr` -> `footer`) is a fix, not a hunt through the list.
            near = _closest(key, SETTING_DEFAULTS)
            if near:
                _err(f"  did you mean: {', '.join(near)}?")
            sys.exit(1)
        print(load_settings()[key])
        return

    if action == "set":
        if len(rest) < 3:
            _err("Usage: mcptoon config set <key> <value>")
            sys.exit(1)
        # The key is always an identifier, so lowercasing it is safe and forgiving.
        # The value is not: closed-choice settings are lowercase enums and accept
        # "ON"/"Off" for free, but a free-text setting holds something like a path
        # or a command line, where lowercasing silently corrupts the value (a path
        # with uppercase in it would be stored mangled and the user would have no
        # clue why their ranker never ran). So only lowercase enum values.
        from .config import SETTING_CHOICES
        key = rest[1].strip().lower()
        value = rest[2].lower() if key in SETTING_CHOICES else rest[2]
        if key == "footer" and value not in ("on", "off"):
            _err("footer accepts only: on | off")
            sys.exit(1)
        if key == "lang" and value not in VALID_LANGS:
            _err("lang accepts only: auto | zh | en")
            sys.exit(1)
        try:
            set_setting(key, value)
        except ValueError as e:
            # A rejected value changes nothing, so the exit code must say so —
            # otherwise `mcptoon config set exposure compakt && restart` reads as
            # success and the user never learns the preset is unchanged.
            _err(str(e))
            sys.exit(1)
        print(f"{key}: {value}   (saved)")
        if key == "footer" and value == "off":
            print("The gateway will stop adding the savings line on the next connection.")
        if key == "lang":
            # Print what the setting resolves to *now*, not what was typed: with
            # `auto` those differ, and "auto" alone leaves the user guessing which
            # machine signal won.
            print(f"The savings line will speak: {resolve_lang()}")
        return

    if action == "unset":
        if len(rest) < 2:
            _err("Usage: mcptoon config unset <key>")
            sys.exit(1)
        key = rest[1].strip().lower()
        try:
            default = unset_setting(key)
        except ValueError as e:
            _err(str(e))
            sys.exit(1)
        print(f"{key}: {default}   (reset to default)")
        return

    if action == "reset":
        reset_settings()
        print("All settings reset to defaults.")
        for key in sorted(load_settings()):
            print(f"  {key:12s} = {load_settings()[key]}")
        return

    _err(f"Unknown config action: {action}")
    _err("Usage: mcptoon config [get <key> | set <key> <value> | "
         "unset <key> | reset]")
    sys.exit(1)


def _cmd_toggle(rest, fmt, head_n=0, max_chars=0, full=False):
    """Toggle a tool on/off (persisted in ~/.mcptoon/toggles.json).

    Usage:
        mcptoon toggle <server> <tool>     Toggle a specific tool
        mcptoon toggle --list              List all toggled tools
        mcptoon toggle --list --json       List disabled tools as JSON
    """
    if "--list" in rest or not rest:
        disabled = cfg.list_disabled_tools()
        # `--json` gives scripts the disabled-tool list as data. It used to print
        # human text regardless (reported 2026-10-18).
        if fmt == "json" or "--json" in rest:
            print(output.render(sorted(disabled), fmt="json", head_n=head_n,
                                max_chars=max_chars, full=full))
            return
        if not disabled:
            print("No tools are disabled. All tools are active.")
            print("")
            print("Usage: mcptoon toggle <server> <tool>   # toggle a tool off/on")
            return
        print(f"Disabled tools ({len(disabled)}):")
        for key in sorted(disabled):
            print(f"  ✗ {key}")
        print("")
        print("Re-enable: mcptoon toggle <server> <tool>  (toggle again)")
        return

    if len(rest) < 2:
        print("Usage: mcptoon toggle <server> <tool>")
        print("")
        print("Examples:")
        print("  mcptoon toggle exa search        # disable exa's search tool")
        print("  mcptoon toggle exa search        # re-enable it")
        print("  mcptoon toggle --list            # show all disabled tools")
        sys.exit(1)

    server = rest[0]
    tool = rest[1]

    # Verify server and tool exist
    servers = cfg.load_config()
    if server not in servers:
        _err(f"Server '{server}' not found.")
        _err(f"Available: {', '.join(sorted(servers.keys()))}")
        sys.exit(1)

    # A disabled entry for a tool that does not exist is a silent no-op: the tool
    # stays visible (it was never there) and `toggle --list` shows a rule the user
    # cannot match to any real tool. Check the cache when we have it — the same
    # offline-only rule `policy set` uses (2026-10-17).
    from . import cache as _cache
    cached, _age = _cache.get_cached_tools_any_age(server)
    if cached is not None:
        names = {t.get("name") for t in cached if isinstance(t, dict) and "error" not in t}
        if tool not in names:
            _err(f"Tool '{tool}' not found on '{server}'.")
            _err(f"See its tools: mcptoon inspect {server}")
            sys.exit(1)

    new_state = cfg.toggle_tool(server, tool)
    status = "ENABLED ✓" if new_state else "DISABLED ✗"
    print(f"{server}:{tool} → {status}")
    # A toggle is reversible, but the output only said the new state — a user who
    # just hid a tool had to remember that the same command brings it back. State
    # the undo explicitly; it is the whole point of a toggle.
    if new_state:
        print(f"  Disable it again: mcptoon toggle {server} {tool}")
    else:
        print(f"  Re-enable it:     mcptoon toggle {server} {tool}")


def _cmd_auto_discover(rest, fmt, head_n=0, max_chars=0, full=False):
    """Auto-discover MCP servers (network probe + config scan + env detection).

    `head_n`/`max_chars`/`full` are the global output flags, threaded through so
    `discover --json` honours them. See `_cmd_install` for why they travel together.

    Usage:
        mcptoon discover                  # auto-discover, print results
        mcptoon discover --write          # discover + write to config
        mcptoon discover --http <url>     # probe a specific HTTP MCP endpoint
        mcptoon discover --no-network     # skip network probing (faster)
        mcptoon discover --no-configs     # skip scanning existing configs
    """
    do_write = "--write" in rest
    http_url = ""
    scan_configs = "--no-configs" not in rest
    detect_env = "--no-env" not in rest
    detect_local = "--no-local" not in rest
    probe_network = "--no-network" not in rest

    for i, a in enumerate(rest):
        if a == "--http" and i + 1 < len(rest):
            http_url = rest[i + 1]
            break
        elif a.startswith("--http="):
            http_url = a.split("=", 1)[1]
            break

    from . import discover as disc

    print("Auto-discovering MCP servers...")
    print("")

    result = disc.auto_discover(
        scan_configs=scan_configs,
        detect_env=detect_env,
        detect_local=detect_local,
        probe_network=probe_network,
    )

    # Add explicit HTTP endpoint if specified
    if http_url:
        probe_info = disc.probe_http_endpoint(http_url, timeout=2.0)
        if probe_info and probe_info.get("alive"):
            http_config = disc.make_http_config(http_url)
            result.servers["http-endpoint"] = http_config
            result.sources["http-endpoint"] = ["manual"]
            # `tools_count` is None when the endpoint answered `initialize` but its
            # tool list could not be read — say so rather than "0 tools".
            if probe_info.get("tools_known", True):
                tool_count = probe_info.get("tools_count") or 0
                result.reasons["http-endpoint"] = (
                    f"HTTP MCP endpoint at {http_url} ({tool_count} tools)")
            else:
                result.reasons["http-endpoint"] = (
                    f"HTTP MCP endpoint at {http_url} (reachable; tool list unreadable)")
        else:
            # The endpoint did not answer an MCP `initialize`. Counting it as a
            # discovered server put a dead URL in `result.count` and in `--write`
            # merges, with only the prose "(not responding)" as a signal
            # (reproduced 2026-10-02). Report it, but do not count it.
            print(f"  ! {http_url} did not answer an MCP initialize — not added.")
            print("    (the URL is recorded in the note below, but not as a server)")

    if fmt in ("toon", "mcptoon", "compact", "slim"):
        print(output.render(list(result.servers.keys()), fmt=fmt,
                            head_n=head_n, max_chars=max_chars, full=full))
    elif fmt == "json":
        print(output.render(result.servers, fmt="json",
                            head_n=head_n, max_chars=max_chars, full=full))
    else:
        print(result.summary())

    if do_write and result.count > 0:
        added, skipped, overwritten = cfg.merge_servers(result.servers, overwrite=False)
        print(f"Config updated: {cfg.CONFIG_FILE}")
        print(f"  +{added} new servers added")
        if skipped:
            print(f"  ={skipped} existing servers skipped")
        print("")
        print("Run: mcptoon manifest --slim")


def _cmd_import(rest, fmt="auto", head_n=0, max_chars=0, full=False):
    """Import MCP servers from another client's config.

    `head_n`/`max_chars`/`full` are the global output flags, threaded through so
    `import --json` honours them. See `_cmd_install` for why they travel together.

    Usage:
        mcptoon import                      # scan every known client (dry run)
        mcptoon import --from cursor        # one client only
        mcptoon import --file servers.json  # any {"mcpServers"|"servers": {...}} export
        mcptoon import --write              # merge the found servers into your config
        mcptoon import --write --force      # overwrite entries that already exist
    """
    from . import discover as disc

    file_path = ""
    from_client = ""
    do_write = "--write" in rest
    do_force = "--force" in rest
    consumed = set()  # indices of tokens consumed as a flag's value
    for i, a in enumerate(rest):
        if a == "--file" and i + 1 < len(rest):
            file_path = rest[i + 1]
            consumed.add(i + 1)
        elif a.startswith("--file="):
            file_path = a.split("=", 1)[1]
        elif a == "--from" and i + 1 < len(rest):
            from_client = rest[i + 1]
            consumed.add(i + 1)
        elif a.startswith("--from="):
            from_client = a.split("=", 1)[1]

    # A bare positional is a file path: `mcptoon import servers.json` is the
    # natural spelling, but the verb only ever looked at `--file`/`--from`, so a
    # positional path was silently dropped and `import /nonexistent/x.json`
    # scanned every client and exited 0 as if the file had been read (reported
    # 2026-10-18). Accept one positional as the file when neither --file nor
    # --from was given; reject it when it conflicts with an explicit flag.
    positionals = [a for j, a in enumerate(rest)
                   if j not in consumed and not a.startswith("-")]
    if positionals:
        if file_path or from_client:
            _err(f"Error: unexpected argument {positionals[0]!r} "
                 f"(already given --file/--from)")
            sys.exit(1)
        if len(positionals) > 1:
            _err(f"Error: import takes at most one file path, got {len(positionals)}")
            sys.exit(1)
        file_path = positionals[0]

    # ─── Gather findings ───
    if file_path:
        p = Path(file_path)
        if not p.exists():
            print(f"Config file not found: {p}", file=sys.stderr)
            sys.exit(1)
        try:
            findings = disc.scan_import_file(p)
        except json.JSONDecodeError as e:
            print(f"Not valid JSON: {p} ({e})", file=sys.stderr)
            sys.exit(1)
        source_label = str(p)
    elif from_client:
        canonical = disc.IMPORT_CLIENT_ALIASES.get(from_client, from_client)
        if canonical not in disc._CLIENT_SCANNERS:
            known = ", ".join(sorted(set(disc.IMPORT_CLIENT_ALIASES.values())))
            print(f"Unknown client: {from_client}", file=sys.stderr)
            print(f"Known clients: {known}", file=sys.stderr)
            print("Or point at any file with: mcptoon import --file <path>", file=sys.stderr)
            sys.exit(1)
        findings = disc.scan_import_client(from_client)
        source_label = canonical
    else:
        findings = []
        for cid in ("claude-desktop", "cursor", "cline", "windsurf"):
            findings.extend(disc.scan_import_client(cid))
        source_label = "all known clients"

    # ─── Dedupe by name (first source wins, matching discover's priority) ───
    servers: dict = {}
    sources: dict = {}
    for item in findings:
        name = item["name"]
        if name in servers:
            continue
        servers[name] = item["config"]
        sources[name] = item["source"]

    # ─── Report ───
    if fmt == "json":
        print(output.render(servers, fmt="json", head_n=head_n, max_chars=max_chars, full=full))
        if do_write and servers:
            cfg.merge_servers(servers, overwrite=do_force)
        return

    if not servers:
        print(f"No MCP servers found in {source_label}.")
        if not file_path:
            print("")
            print("If your servers live somewhere else, export them and point at the file:")
            print("  mcptoon import --file <path-to-export.json>")
        return

    print(f"Found {len(servers)} server(s) in {source_label}:")
    print("")
    by_source: dict = {}
    for name, src in sources.items():
        by_source.setdefault(src, []).append(name)
    for src, names in by_source.items():
        print(f"  [{src}] {', '.join(names)}")
    print("")

    if not do_write:
        print("(--dry run: nothing written. Add --write to merge these into your config.)")
        print(f"  Would write to: {cfg.CONFIG_FILE}")
        return

    added, skipped, overwritten = cfg.merge_servers(servers, overwrite=do_force)
    print(f"Config updated: {cfg.CONFIG_FILE}")
    print(f"  +{added} new server(s) added")
    if overwritten:
        print(f"  ~{overwritten} overwritten")
    if skipped:
        print(f"  ={skipped} existing server(s) skipped (use --force to overwrite)")
    print("")
    print("Next: mcptoon manifest --slim    # see all available tools")


def _explain_server_error(raw: str) -> tuple[str, str]:
    """Turn a raw MCP client error into (plain reason, what to do next).

    Thin delegate to `manifest.explain_error` — the table lives there because the
    failing-server text is rendered in several places (`doctor`, `inspect`,
    `manifest`), and one table beats four that drift.
    """
    return manifest_mod.explain_error(raw)


def _cmd_doctor(rest, fmt="auto"):
    """Self-diagnose configuration and connectivity.

    Usage:
        mcptoon doctor            # human-readable diagnostics
        mcptoon doctor --json     # structured {checks, issues, ok, broken}
    """
    json_mode = fmt == "json" or "--json" in rest
    rows = []          # structured check results for --json
    broken = []        # (server, reason) for the human summary + JSON

    def emit(status, name, detail, human_line, **extra):
        rows.append({"name": name, "status": status, "detail": detail, **extra})
        if not json_mode:
            print(human_line)

    issues = 0
    checks = 0

    if not json_mode:
        print("mcptoon doctor — running diagnostics...")
        print()

    # 1. Python version
    checks += 1
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        emit("ok", "python", f"{py_ver} (>=3.10 required)",
             f"  ✓ Python {py_ver} (>=3.10 required)")
    else:
        emit("error", "python", f"{py_ver} needs 3.10+",
             f"  ✗ Python {py_ver} — needs 3.10+")
        issues += 1

    # 2. Config file
    checks += 1
    # `cfg.CONFIG_FILE` is only the JSON path; `load_config` also reads
    # `config.toml`. Gating on JSON alone told a user with a TOML config
    # "No config found. Run: mcptoon quickstart" — advice that, before this fix,
    # would have deleted their servers (2026-10-02).
    if cfg.has_config_file():
        servers = cfg.load_config()
        shown = cfg.CONFIG_FILE if cfg.CONFIG_FILE.exists() else cfg.CONFIG_FILE_TOML
        emit("ok", "config", f"{shown} ({len(servers)} servers)",
             f"  ✓ Config: {shown} ({len(servers)} servers)")
    else:
        emit("error", "config", "no config found",
             "  ✗ No config found. Run: mcptoon quickstart")
        issues += 1
        if json_mode:
            print(json.dumps({"checks": rows, "issues": issues, "ok": False,
                              "broken": broken}, ensure_ascii=False, indent=2))
        else:
            print()
            print(f"  {checks} checks, {issues} issue(s)")
        sys.exit(1)

    # 3. Cache directory
    checks += 1
    if cfg.CACHE_DIR.exists():
        emit("ok", "cache", str(cfg.CACHE_DIR), f"  ✓ Cache dir: {cfg.CACHE_DIR}")
    else:
        emit("warn", "cache", "missing (will be created on first use)",
             "  ! Cache dir missing (will be created on first use)")
        cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 4. Check each server
    servers = cfg.load_config()
    for name in sorted(servers.keys()):
        s_cfg = servers[name]
        transport = s_cfg.get("transport", "stdio")
        checks += 1

        try:
            tools = manifest_mod.get_server_tools(name, use_cache=True)
            errs = [t for t in tools if isinstance(t, dict) and "error" in t]
            if errs:
                # A server that never started is an *issue*, not an empty server.
                # It used to print `0 tools (server may be empty)` and leave the
                # issue count at zero, so `doctor` ended with "All good!" on a
                # machine whose server binary did not exist (2026-10-02).
                #
                # The raw error is kept on the line because it is the only thing
                # that names the real cause, but it is no longer the *whole*
                # message: the plain reason and the next step follow it, so the
                # output is useful to someone who has never seen a JSON-RPC id.
                raw = str(errs[0].get("error", ""))
                reason, next_step = _explain_server_error(raw)
                emit("error", f"server:{name}", f"cannot start: {raw[:70]}",
                     f"  ✗ {name:20s} [{transport:5s}] cannot start: {raw[:70]}\n"
                     f"      {reason}.\n      → {next_step}",
                     server=name, transport=transport, reason=reason)
                issues += 1
                broken.append((name, reason))
            else:
                count = len(tools)
                if count > 0:
                    emit("ok", f"server:{name}", f"{count} tools",
                         f"  ✓ {name:20s} [{transport:5s}] {count} tools",
                         server=name, transport=transport, tools=count)
                else:
                    emit("warn", f"server:{name}", "0 tools (started, exposes none)",
                         f"  ! {name:20s} [{transport:5s}] 0 tools "
                         f"(server started but exposes none)",
                         server=name, transport=transport, tools=0)
        except Exception as e:
            raw = str(e)
            reason, next_step = _explain_server_error(raw)
            emit("error", f"server:{name}", f"ERROR: {raw[:80]}",
                 f"  ✗ {name:20s} [{transport:5s}] ERROR: {raw[:80]}\n"
                 f"      {reason}.\n      → {next_step}",
                 server=name, transport=transport, reason=reason)
            issues += 1
            broken.append((name, reason))

    # 5. Environment
    checks += 1
    agent_type = os.environ.get("MCPTOON_AGENT_TYPE", "")
    if agent_type:
        emit("ok", "env", f"MCPTOON_AGENT_TYPE={agent_type}",
             f"  ✓ MCPTOON_AGENT_TYPE={agent_type}")
    else:
        emit("info", "env", "MCPTOON_AGENT_TYPE not set (defaulting to auto)",
             "  - MCPTOON_AGENT_TYPE not set (defaulting to auto)")

    # 6. Status-line badge. `doctor` tested every server but never asked the one
    # question a healthy-but-invisible install raises: is the badge actually on a
    # status bar, or is the user paying for a tool they never see? Not being wired
    # is a CHOICE, not a fault (only Claude Code auto-supports a status bar), so
    # this is `info`/`warn` and never bumps `issues`. `mode.statusline_status()`
    # existed for exactly this and was never called.
    checks += 1
    try:
        from . import mode as mode_mod
        sl = mode_mod.statusline_status()
    except Exception:
        sl = None
    if sl is not None:
        if sl.get("wired"):
            emit("ok", "statusline", f"wired in {sl.get('path')}",
                 f"  ✓ Status line: wired in Claude Code ({sl.get('path')})")
        elif sl.get("file_exists"):
            emit("info", "statusline", "not wired (Claude Code settings present)",
                 "  - Status line: not wired — `mcptoon statusline --install` puts the"
                 " savings badge in Claude Code's status bar")
        else:
            emit("info", "statusline", "no Claude Code settings (other hosts: see docs)",
                 "  - Status line: Claude Code not detected. Other hosts have no status"
                 " bar; run `mcptoon statusline` to see the badge anywhere")

    # 7. Delivery mode. `doctor` tested every server but never answered the one
    # question a healthy-but-invisible install raises: is mcptoon actually saving
    # anything, or is it installed and doing nothing? `direct` (installed, not
    # wired) is the common silent case — the agent loads the full catalog native,
    # so nothing is saved until it is wired or `call` is used. Name it with one
    # action. Never bumps `issues`: a not-yet-wired install is a choice, not a fault.
    checks += 1
    try:
        from . import footer as footer_mod
        _dmode = footer_mod.current_mode()
        _dfacts = footer_mod.facts()
    except Exception:
        _dmode, _dfacts = None, {}
    _dfull = (_dfacts or {}).get("tokens_full") or 0
    if _dmode == "direct":
        emit("warn", "mode", "direct (not wired) — nothing is saved yet",
             f"  ! Mode: direct — installed but not wired, so the agent loads the "
             f"full {_dfull:,} tokens natively.\n"
             f"      → run `mcptoon sync --self` to save, or use `mcptoon call`\n"
             f"      → `mcptoon credit` shows your mode and the real saving in one line",
             mode=_dmode)
    elif _dmode == "serve-alongside":
        # Gateway wired but the upstream entries still load directly, so the
        # gateway saves nothing yet. The plain "serve — gateway wired" OK line
        # would declare a healthy saving that is not happening; name the gap and
        # the takeover fix instead.
        _de = 0
        try:
            from . import mode as mode_mod
            _de = int(mode_mod.detect().get("direct_entries") or 0)
        except Exception:
            _de = 0
        emit("warn", "mode", "serve-alongside — gateway wired but not taken over",
             f"  ! Mode: serve-alongside — the gateway is wired, but {_de:,} direct "
             f"entr{'y' if _de == 1 else 'ies'} still load the full {_dfull:,} tokens "
             f"natively, so nothing is saved yet.\n"
             f"      → run `mcptoon sync --takeover` to route them through the gateway",
             mode=_dmode)
    elif _dmode == "cli":
        emit("ok", "mode", "cli — 0 resident, full catalog never loads",
             f"  ✓ Mode: cli — 0 resident, the full {_dfull:,} tokens never load",
             mode=_dmode)
    elif _dmode == "serve":
        emit("ok", "mode", "serve — gateway wired", "  ✓ Mode: serve — gateway wired",
             mode=_dmode)
    elif _dmode == "empty":
        emit("info", "mode", "no servers yet", "  - Mode: nothing registered yet", mode=_dmode)

    if json_mode:
        # Promote the delivery mode to top-level fields so a script reads it
        # directly instead of scanning checks[] for the "mode" row.
        try:
            from . import mode as mode_mod
            _rec = mode_mod.recommend(lng=cfg.resolve_lang())
            _rec_now = _rec.get("recommended") if _rec else None
            _rec_action = _rec.get("one_action") if _rec else None
        except Exception:
            _rec_now, _rec_action = None, None
        print(json.dumps({
            "checks": rows, "issues": issues, "ok": issues == 0,
            "broken": [{"server": n, "reason": r} for n, r in broken],
            "delivery_mode": _dmode,
            "recommended": _rec_now,
            "one_action": _rec_action,       # unified name (matches credit/report)
            "recommended_action": _rec_action,  # back-compat alias
        }, ensure_ascii=False, indent=2))
        if issues:
            sys.exit(1)
        return

    print()
    print(f"  {checks} checks, {issues} issue(s)")
    if issues == 0:
        print("  All good! ✓")
        # A clean bill of health is not the same as "you'd notice it working".
        # Teach the one thing a healthy-but-silent tool never shows: where to
        # watch it do its job. Skip when nothing is registered to serve (a bare
        # config would make "let an agent use a tool" advice hollow).
        try:
            _wired = _gateway_wired_in()
        except Exception:
            _wired = False
        if _wired and cfg.presence_enabled():
            try:
                _act = usage_mod.activity_summary()
            except Exception:
                _act = {}
            if _installed_but_silent(_act):
                # Healthy components, but nothing has actually flowed through.
                # "All good" alone would hide a wiring problem the checks cannot
                # see (they test each server, not whether an agent ever calls the
                # gateway). Name the ambiguity instead of declaring victory.
                print("  ⚠ All components check out, but no call has come through "
                      "the gateway yet. If your agent never uses mcptoon, that is a "
                      "wiring problem, not a health problem — see `mcptoon activity`.")
            else:
                print("  See it working: let an agent use a tool, then run"
                      " `mcptoon activity`")
    else:
        # Name the broken servers together, once, at the end. The per-server
        # lines scroll away on a machine with a dozen servers, and "see above"
        # is not an answer when the answer is one line.
        if broken:
            print()
            print(f"  {len(broken)} server(s) need attention:")
            for name, reason in broken:
                print(f"    • {name} — {reason}")
            print("  Start with: mcptoon inspect <server>")
        else:
            print(f"  {issues} issue(s) found. See above for details.")

    # ─── Smart tips ───
    _doctor_smart_tips(servers)

    # Star hint: once per machine, only on a fully healthy doctor run, and
    # never in CI or when suppressed (MCPTOON_NO_STAR_HINT=1). Terminal-only:
    # the structured outputs other commands serve to scripts are untouched.
    if issues == 0 and _should_show_star_hint():
        print()
        print("  Found this useful? A GitHub star helps others find mcptoon:")
        print("  https://github.com/activeing123/mcptoon")
        _mark_star_hint_shown()

    # A diagnostic that found problems must say so in its exit code. `doctor`
    # printed "✗ … cannot start" and "N issue(s)" yet exited 0, so a CI health
    # check or `mcptoon doctor && deploy` read a broken machine as healthy
    # (reported 2026-10-17). Warnings (e.g. an empty cache dir, printed with `!`)
    # are not issues and do not change the code — only real `✗` findings do.
    if issues:
        sys.exit(1)


def _star_hint_marker():
    return cfg.CACHE_DIR / "star-hint-shown"


def _should_show_star_hint() -> bool:
    """Show the star hint at most once per machine, never in CI."""
    if os.environ.get("CI") or os.environ.get("MCPTOON_NO_STAR_HINT"):
        return False
    try:
        return not _star_hint_marker().exists()
    except OSError:
        return False  # fail quiet: never nag on odd filesystems


def _mark_star_hint_shown():
    try:
        cfg.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _star_hint_marker().write_text("shown", encoding="utf-8")
    except OSError:
        pass


def _doctor_smart_tips(servers: dict):
    """Print smart tips based on current configuration.

    This is the Land & Expand strategy in action:
    - <3 servers: suggest adding more (zero-config servers)
    - 3-5 stdio servers: mention HTTP endpoints as an option
    - >5 stdio servers: strongly recommend HTTP aggregation
    - HTTP endpoint already configured: confirm it's working
    """
    if not servers:
        return

    stdio_count = sum(1 for s in servers.values() if s.get("transport", "stdio") == "stdio")
    http_count = sum(1 for s in servers.values() if s.get("transport") == "http")
    total = len(servers)

    tips = []

    # Tip 1: Too few servers
    if total <= 2:
        tips.append(
            "Tip: Add zero-config servers (no API key needed):\n"
            "  mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything\n"
            "  mcptoon add memory --stdio npx -y @modelcontextprotocol/server-memory\n"
            "  Or run: mcptoon init --auto"
        )

    # Tip 2: Many stdio servers — recommend HTTP aggregation
    if stdio_count >= 6:
        tips.append(
            f"Tip: You have {stdio_count} stdio servers. Each spawns a separate process.\n"
            "  Consider aggregating them behind one HTTP MCP endpoint:\n"
            "  mcptoon init --auto --http http://your-server:8080/mcp\n"
            "  Benefits: faster startup, shared connection, all tools behind one URL"
        )
    elif stdio_count >= 3:
        tips.append(
            f"Tip: {stdio_count} stdio servers detected. If startup feels slow,\n"
            "  consider an HTTP MCP endpoint: mcptoon add my-server --http http://localhost:8080/mcp"
        )

    # Tip 3: HTTP endpoint already configured
    has_http = any(s.get("transport") == "http" for s in servers.values())
    if has_http:
        tips.append(
            "HTTP MCP endpoint configured. All tools across all servers are accessible\n"
            "  through one endpoint — no per-server process spawning needed."
        )

    # Tip 4: No HTTP servers at all
    if http_count == 0 and stdio_count >= 4:
        tips.append(
            "Tip: All your servers use stdio (subprocess). For better performance,\n"
            "  consider running an HTTP MCP server to serve them over HTTP."
        )

    if tips:
        print()
        print("  ── Smart Tips ──")
        for tip in tips:
            print()
            for line in tip.split("\n"):
                print(f"  {line}")


# ═══════════════════════════════════════════════════
# Install — one-command MCP server installation
# ═══════════════════════════════════════════════════

def _cmd_install_pack(pack_name, *, dry_run, fmt, list_only=False):
    """List or install a skill pack (a named bundle of MCP tools + a prompt)."""
    from . import packs as packs_mod
    from .packs import PackError

    try:
        catalog = packs_mod.load_catalog()
    except PackError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    if list_only or pack_name is None:
        if fmt == "json":
            print(json.dumps({"packs": catalog}, ensure_ascii=False, indent=1))
            return
        print(f"  {len(catalog)} skill pack(s) available:\n")
        for p in catalog:
            tools = ", ".join(t.get("name", "?") for t in p.get("tools") or [])
            print(f"    {p.get('name')}  — {p.get('title', '')}")
            print(f"        {p.get('description', '')}")
            print(f"        tools: {tools}")
        print("\n  Install one:  mcptoon install --pack <name>")
        print("  Preview:      mcptoon install --pack <name> --dry")
        return

    pack = packs_mod.find_pack(catalog, pack_name)
    if pack is None:
        print(f"  ❌ No pack named {pack_name!r}.")
        print("  List packs: mcptoon install --packs")
        sys.exit(1)

    if fmt == "json":
        report = packs_mod.install_pack(pack, dry_run=dry_run)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        sys.exit(0 if report["ok"] else 1)

    tools = pack.get("tools") or []
    verb = "Would install" if dry_run else "Installing"
    print(f"  Pack: {pack.get('name')} — {pack.get('title', '')}")
    print(f"  {verb} {len(tools)} tool(s):")
    for t in tools:
        kind, payload = packs_mod._tool_kind(t)
        print(f"    {t.get('name', '?'):<14} {payload or '(unrecognized)'}  [{kind or '?'}]")
    if pack.get("prompt"):
        dest = packs_mod.packs_root() / pack["name"] / "PROMPT.md"
        print(f"  Prompt → {dest}")
    if dry_run:
        print("\n  Dry run — nothing was installed. Drop --dry to install.")
        return

    report = packs_mod.install_pack(pack)
    print()
    for t in report["tools"]:
        mark = "✅" if t["ok"] else "❌"
        print(f"    {mark} {t['name']}")
    if report.get("prompt"):
        print(f"  Prompt written: {report['prompt']}")
    if not report["ok"]:
        print("  ⚠ some tools failed to install — see the report above.", file=sys.stderr)
        sys.exit(1)
    print("  Next: mcptoon sync   (hand the new servers to your agents)")


def _post_install_mode_hint(fmt) -> None:
    """After `install`, name the delivery mode and the one action to start saving.

    Adding a server does not wire anything: a fresh install often stays in `direct`
    (installed, not wired), where the agent loads the full catalog natively and
    nothing is saved. Say so at the moment the user just added a tool, with the one
    command that fixes it. Human mode only; never on a machine that already saves.
    """
    if fmt not in ("auto", "human"):
        return
    try:
        from . import footer as footer_mod
        cur = footer_mod.current_mode()
    except Exception:
        return
    if cur == "direct":
        _err("  ⚠ Mode: direct (not wired) — nothing is saved yet. "
             "`mcptoon sync --self` wires serve, or use `mcptoon call`.")
    elif cur == "serve-alongside":
        _err("  ⚠ Mode: serve-alongside — the gateway is wired but has not taken "
             "over the direct entries, so nothing is saved yet. "
             "`mcptoon sync --takeover` routes them through the gateway.")
    elif cur == "cli":
        _err("  ✓ Mode: cli — a call loads one schema on demand; the full catalog "
             "never loads.")


def _post_onboard_mode_hint(fmt) -> None:
    """After `quickstart`, say whether the machine is now saving (stdout).

    Same intent as `_post_install_mode_hint` but on the onboarding summary (stdout,
    not stderr): a fresh install commonly stops at `direct` where the big 99% is not
    being realised. Name the mode and the one command that shows the truth.
    """
    if fmt not in ("auto", "human"):
        return
    try:
        from . import footer as footer_mod
        cur = footer_mod.current_mode()
    except Exception:
        return
    if cur == "direct":
        print("  ⚠ Mode: direct (not wired) — you are not saving yet. "
              "`mcptoon sync --self` wires serve.")
    elif cur == "serve-alongside":
        print("  ⚠ Mode: serve-alongside — gateway wired but direct entries not "
              "taken over, so you are not saving yet. `mcptoon sync --takeover`.")
    elif cur:
        print(f"  ✓ Mode: {cur} — saving is on. See `mcptoon credit`.")


def _cmd_install(rest, fmt, full=False, head_n=0, max_chars=0):
    """Install/list/remove MCP servers with auto-handler generation.

    ``full``, ``head_n`` and ``max_chars`` come from the global output flags. They
    have to be forwarded rather than assumed: these paths render through
    `_render_result`, which caps output and prints "use --full" when it does.

    Why all three and not just ``full``: before this, only ``full`` was threaded
    through, so `--head` and `--max-chars` were silently ignored here — the two
    remaining global output flags that did not work on this one command. They were
    fixed together because they are one defect (this handler did not receive the
    output flags), not three. Confirmed by running `install --list` with each flag
    and diffing stdout: `--full` changed nothing, `--head 1` changed nothing,
    `--max-chars 500` changed nothing.

    Usage:
        mcptoon install <name> --npm <package>   Install from npm (npx)
        mcptoon install <name> --pip <package>   Install from pip
        mcptoon install <name> --url <url>       Install HTTP/SSE MCP
        mcptoon install <name> --url <url> --header 'Authorization: Bearer ${TOKEN}'
                                                 Same, for a server that needs a header.
                                                 `${TOKEN}` names an environment
                                                 variable, read at call time — the
                                                 secret is never written to disk.
        mcptoon install --list                   List installed servers
        mcptoon install --remove <name>           Remove an installed server
    """
    npm_pkg = None
    pip_pkg = None
    http_url = None
    server_name = None
    do_list = False
    do_remove = False
    do_search = False
    do_packs = False
    pack_name = None
    dry_run = False
    http_headers = {}

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--npm" and i + 1 < len(rest):
            npm_pkg = rest[i + 1]
            i += 2
        elif a == "--pip" and i + 1 < len(rest):
            pip_pkg = rest[i + 1]
            i += 2
        elif a == "--url" and i + 1 < len(rest):
            http_url = rest[i + 1]
            i += 2
        elif a == "--header" and i + 1 < len(rest):
            # Same shape as `add --http --header 'Key: Value'` (issue #24): one
            # parser, so `install --url` and `add --http` cannot drift.
            h = rest[i + 1]
            if ":" in h:
                k, v = h.split(":", 1)
                http_headers[k.strip()] = v.strip()
            i += 2
        elif a == "--search" and i + 1 < len(rest):
            do_search = True
            server_name = rest[i + 1]
            i += 2
        elif a == "--packs":
            do_packs = True
            i += 1
        elif a == "--pack" and i + 1 < len(rest):
            pack_name = rest[i + 1]
            i += 2
        elif a == "--dry":
            dry_run = True
            i += 1
        elif a == "--list":
            do_list = True
            i += 1
        elif a == "--remove" and i + 1 < len(rest):
            server_name = rest[i + 1]
            do_remove = True
            i += 2
        elif not a.startswith("--"):
            server_name = a
            i += 1
        else:
            i += 1

    # mcptoon install --packs / --pack <name>  → install a whole workflow at once
    if do_packs or pack_name is not None:
        _cmd_install_pack(pack_name, dry_run=dry_run, fmt=fmt, list_only=do_packs)
        return

    if do_list:
        from .installer import list_installed
        result = list_installed()
        # Routed through `_render_result` rather than `output.render` directly:
        # `--smart` must go down the *same* path as `call`, so the compressed view
        # carries a retrieve handle. `output.render(fmt="smart")` no longer
        # compresses at all (it has no store context to key a handle on), so
        # calling it here would silently turn `--smart` into plain JSON.
        # Measured on this machine: `install --list` is 32,835 bytes and does get
        # compressed, so this is not a theoretical path.
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="list")
        return

    if do_remove:
        from .installer import remove_installed
        result = remove_installed(server_name)
        # `install --remove` is the other door that removes a server; drop its
        # schema cache here too so it does not leak the same way `remove` did.
        if isinstance(result, dict) and result.get("status") == "removed":
            from . import cache as cache_mod
            try:
                cache_mod.clear_server_cache(server_name)
            except Exception:
                pass
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="remove")
        return

    # mcptoon install --search <keyword>  → list matches, install nothing
    if do_search:
        from .installer import search_registry, RegistryError
        try:
            results = search_registry(server_name, limit=20)
        except RegistryError as e:
            print(f"  ❌ {e}")
            sys.exit(1)
        if not results:
            print(f"  No MCP server found matching '{server_name}'.")
            sys.exit(1)
        print(f"  Found {len(results)} servers matching '{server_name}':\n")
        for i, r in enumerate(results):
            name = r.get("name", "")
            src = r.get("source", "")
            desc = " ".join((r.get("description", "") or "").split())[:70]
            kind = r.get("kind") or ("hosted" if src == "smithery"
                                     else ("remote" if r.get("url") else ""))
            tag = f" [{kind}]" if kind else ""
            mark = " ✓" if r.get("verified") else ""
            uses = r.get("uses") or 0
            uses_s = f"   {uses:,} calls" if uses else ""
            print(f"    {i + 1:>2}. {name}{mark}{tag}  ({src}){uses_s}")
            if desc:
                print(f"        {desc}")
        print(f"\n  ✓ = verified by the registry. Third-party servers are not audited"
              f" by mcptoon — check the source before granting credentials.")
        print(f"\n  Install one:  mcptoon install <name>")
        print(f"  Preview only: mcptoon install --search <name>")
        return

    if http_url:
        from .installer import install_http
        result = install_http(http_url, server_name, headers=http_headers)
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="http")
        return

    if npm_pkg:
        from .installer import install_npm
        result = install_npm(npm_pkg, server_name)
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="npm")
        _post_install_mode_hint(fmt)
        return

    if pip_pkg:
        from .installer import install_pip
        result = install_pip(pip_pkg, server_name)
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="pip")
        _post_install_mode_hint(fmt)
        return

    # mcptoon install <name>  (no --npm/--pip/--url) → auto-search & install
    if server_name and not server_name.startswith("--"):
        from .installer import install_by_name, search_registry, RegistryError
        # First: show what we found, so the user sees what is about to be installed.
        try:
            results = search_registry(server_name)
        except RegistryError as e:
            print(f"  ❌ {e}")
            sys.exit(1)
        if not results:
            print(f"  ❌ No MCP server found matching '{server_name}'.")
            print(f"  Search wider: mcptoon install --search <keyword>")
            print(f"  Or install directly: mcptoon install {server_name} --npm <package>")
            return
        # If multiple results, show them
        if len(results) > 1:
            print(f"  Found {len(results)} servers matching '{server_name}':")
            for i, r in enumerate(results[:10]):
                name = r.get("name", "")
                desc = (r.get("description", "") or "")[:60]
                src = r.get("source", "")
                print(f"    {i+1}. {name} ({src}) — {desc}")
            print(f"\n  Installing best match: {results[0].get('name', server_name)}")
        else:
            print(f"  Found: {results[0].get('name', server_name)} — {(results[0].get('description', '') or '')[:80]}")

        result = install_by_name(server_name)
        _render_result(result, fmt, head_n, max_chars, full, True,
                       server="install", tool="by-name")
        from .errors import is_error
        if is_error(result):
            sys.exit(1)
        _post_install_mode_hint(fmt)
        return

    print("Usage:")
    print("  mcptoon install <name>              # Auto-search & install from registry")
    print("  mcptoon install --search <keyword>  # Search registries, install nothing")
    print("  mcptoon install --packs             # List the available skill packs")
    print("  mcptoon install --pack <name>       # Install a whole pack (tools + prompt)")
    print("  mcptoon install --pack <name> --dry  # Preview a pack, install nothing")
    print("  mcptoon install <name> --npm <pkg>  # Install from npm")
    print("  mcptoon install <name> --pip <pkg>  # Install from pip")
    print("  mcptoon install <name> --url <url>  # Install HTTP/SSE MCP")
    print("  mcptoon install --list              # List installed servers")
    print("  mcptoon install --remove <name>      # Remove an installed server")


# ═══════════════════════════════════════════════════
# Shell completion
# ═══════════════════════════════════════════════════

_BASH_COMPLETION = r'''
_mcptoon_complete() {
    local cur prev commands
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="__MC_TOON_COMMANDS__"

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$commands" -- $cur) )
        return 0
    fi

    case "$prev" in
        call|inspect)
            if [ $COMP_CWORD -eq 2 ]; then
                COMPREPLY=( $(compgen -W "$(mcptoon list 2>/dev/null | sed 's/  //;s/ \[.*//')" -- $cur) )
            fi
            ;;
        mode)
            COMPREPLY=( $(compgen -W "recommend" -- $cur) )
            ;;
        --format)
            COMPREPLY=( $(compgen -W "openai openapi mcp json human" -- $cur) )
            ;;
        --toon|--mcptoon|--slim|--smart|--json|--compact|--raw|--full|--stdin)
            COMPREPLY=()
            ;;
    esac
}
complete -F _mcptoon_complete mcptoon
'''

_ZSH_COMPLETION = r'''
#compdef mcptoon

_mcptoon() {
    local commands=(__MC_TOON_COMMANDS__)
    local formats=(openai openapi mcp json human)

    if (( CURRENT == 1 )); then
        _describe 'command' commands
        return
    fi

    case $words[2] in
        call|inspect)
            if (( CURRENT == 2 )); then
                local servers=($(mcptoon list 2>/dev/null | sed 's/  //;s/ \[.*//'))
                _describe 'server' servers
            fi
            ;;
        mode)
            _describe 'mode' 'recommend'
            ;;
        --format)
            _describe 'format' formats
            ;;
    esac
}
compdef _mcptoon mcptoon
'''

_FISH_COMPLETION = r'''
complete -c mcptoon -n '__fish_use_subcommand' -a '__MC_TOON_COMMANDS__'
complete -c mcptoon -n '__fish_seen_subcommand_from call inspect' -a '(mcptoon list 2>/dev/null | sed "s/  //;s/ \[.*//")'
complete -c mcptoon -n '__fish_seen_subcommand_from mode' -a 'recommend'
complete -c mcptoon -n '__fish_seen_subcommand_from --format' -a 'openai openapi mcp json human'
'''

_PS_COMPLETION = '''
$scriptBlock = {
    param($wordToComplete, $commandAst, $cursorPosition)
    $commands = __MC_TOON_COMMANDS_PS__
    $commands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
Register-ArgumentCompleter -CommandName mcptoon -ScriptBlock $scriptBlock
'''


def _completion_rc_path(shell: str):
    """The rc/profile file a shell reads at startup, where `--install` writes.

    A shell that is asked to install its own completion has to know *where* the
    user's startup file lives; hardcoding it per shell here keeps the answer in
    one place instead of making the user copy a path out of the docs. Windows has
    no `~/.bashrc` by convention, so bash/zsh fall back to the same dotfile names
    they use everywhere else (Git Bash / WSL honour them), and PowerShell uses its
    documented profile location.
    """
    from pathlib import Path
    home = Path.home()
    if shell in ("powershell", "ps"):
        if os.name == "nt":
            return home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
        return home / ".config" / "powershell" / "profile.ps1"
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".bashrc"


# Delimiters that make `--install` idempotent (a second run replaces the block
# instead of appending a duplicate) and `--uninstall` exact (it removes only what
# mcptoon wrote, never a line the user added).
_COMPLETION_BEGIN = "# >>> mcptoon completion >>>"
_COMPLETION_END = "# <<< mcptoon completion <<<"


def _completion_block(script: str) -> str:
    # The shell scripts open with a newline (the raw string starts on its own
    # line); trim it so the block does not begin with a blank line after the marker.
    return f"{_COMPLETION_BEGIN}\n{script.strip(chr(10))}\n{_COMPLETION_END}\n"


def _install_completion(shell: str, script: str, name: str, dry: bool = False) -> None:
    """Write the completion block into the shell's rc file, idempotently.

    Re-running replaces the existing block in place, so the file never grows a
    second copy; running it when the block is already byte-identical reports
    "already installed" and touches nothing (a mtime-only change on a config file
    is exactly the kind of surprise a routine command should avoid). `dry=True`
    prints the target file and the exact block that would be written, without
    writing — so a user can preview before letting a command edit their dotfile.
    """
    path = _completion_rc_path(shell)
    block = _completion_block(script)
    if dry:
        already = path.exists() and _COMPLETION_BEGIN in path.read_text(encoding="utf-8")
        action = "replace the existing block" if already else "append a new block"
        print(f"Would install mcptoon completion for {name} into: {path}")
        print(f"  ({action})")
        print("-" * 60)
        print(block, end="")
        print("-" * 60)
        print("No file was changed (--dry).")
        return
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    if _COMPLETION_BEGIN in existing and _COMPLETION_END in existing:
        start = existing.index(_COMPLETION_BEGIN)
        end = existing.index(_COMPLETION_END) + len(_COMPLETION_END)
        # `tail` already carries the newline(s) that followed the end marker; add
        # them back verbatim so a byte-identical block compares equal and reports
        # "already installed" instead of rewriting the file on every run.
        tail = existing[end:]
        updated = existing[:start] + block.rstrip("\n") + tail
        if updated == existing:
            print(f"mcptoon completion for {name} is already installed in {path}")
            return
        path.write_text(updated, encoding="utf-8")
        print(f"mcptoon completion for {name} updated in {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix:
        prefix += "\n"  # one blank line between the user's content and our block
    path.write_text(prefix + block, encoding="utf-8")
    print(f"mcptoon completion for {name} installed in {path}")
    print("  Open a new shell (or source the file) to activate it.")


def _uninstall_completion(shell: str, name: str) -> None:
    """Remove mcptoon's completion block from the shell's rc file, if present."""
    path = _completion_rc_path(shell)
    if not path.exists():
        print(f"mcptoon completion for {name} is not installed ({path} does not exist)")
        return
    existing = path.read_text(encoding="utf-8")
    if _COMPLETION_BEGIN not in existing or _COMPLETION_END not in existing:
        print(f"mcptoon completion for {name} is not installed in {path}")
        return
    start = existing.index(_COMPLETION_BEGIN)
    end = existing.index(_COMPLETION_END) + len(_COMPLETION_END)
    before = existing[:start].rstrip("\r\n")
    after = existing[end:].lstrip("\r\n")
    if before:
        before += "\n"
    updated = before + after
    path.write_text(updated, encoding="utf-8")
    print(f"mcptoon completion for {name} removed from {path}")


def _cmd_completion(rest):
    """Generate shell completion script (optionally install/uninstall it).

    Usage:
        mcptoon completion bash            Print the completion script
        mcptoon completion bash --install  Write it into ~/.bashrc (idempotent)
        mcptoon completion bash --install --dry  Preview the write, change nothing
        mcptoon completion bash --uninstall Remove it from ~/.bashrc

    Printing a script and telling the user to paste it into the right file is a
    dead end for most people — they have to know which rc file their shell reads
    and where it lives. `--install` closes that loop; the block is wrapped in
    markers so a re-run updates in place and `--uninstall` removes exactly what
    mcptoon added. `--dry` previews the target path and exact block without
    touching the file. Without any of these flags the behaviour is unchanged
    (print to stdout) so `eval "$(mcptoon completion bash)"` keeps working.
    """
    do_install = "--install" in rest
    do_uninstall = "--uninstall" in rest
    dry = "--dry" in rest
    rest = [a for a in rest if a not in ("--install", "--uninstall", "--dry")]

    # With `--install`/`--uninstall` and no shell named, detect one so
    # `mcptoon completion --install` is not a usage error.
    if not rest and (do_install or do_uninstall):
        rest = [_detect_shell()]

    shell = rest[0] if rest else "bash"

    scripts = {
        "bash": ("Bash", _BASH_COMPLETION),
        "zsh": ("Zsh", _ZSH_COMPLETION),
        "fish": ("Fish", _FISH_COMPLETION),
        "powershell": ("PowerShell", _PS_COMPLETION),
        "ps": ("PowerShell", _PS_COMPLETION),
    }

    if shell not in scripts:
        _err(f"Unknown shell: {shell}")
        _err(f"Supported: {', '.join(scripts.keys())}")
        sys.exit(1)

    name, script = scripts[shell]
    # One source of truth for the verb list; each shell script embeds a marker.
    script = script.replace("__MC_TOON_COMMANDS__", _CMD_WORDS)
    script = script.replace("__MC_TOON_COMMANDS_PS__", _CMD_PS_WORDS)

    if do_install:
        _install_completion(shell, script, name, dry=dry)
        return
    if do_uninstall:
        if dry:
            print(f"Would remove mcptoon completion for {name} from: {_completion_rc_path(shell)}")
            print("No file was changed (--dry).")
            return
        _uninstall_completion(shell, name)
        return

    print(f"# mcptoon completion for {name}")
    print("# Install: eval this script or add to your shell config")
    print(script)


def _detect_shell() -> str:
    """Best-effort guess at the user's shell, for `completion --install` with none named.

    `$SHELL` is authoritative on POSIX; on Windows there is no such variable, so
    PowerShell is the safe default (it is the shell this CLI's docs and examples
    assume there). A shell we cannot map falls back to bash, which is the same
    default the plain `completion` command uses.
    """
    shell_env = (os.environ.get("SHELL") or "").lower()
    for cand in ("zsh", "fish", "bash"):
        if cand in shell_env:
            return cand
    if os.name == "nt":
        return "powershell"
    return "bash"


# ═══════════════════════════════════════════════════
# Agent Plugins command (spec 1.0.0)
# ═══════════════════════════════════════════════════

def _cmd_plugin(rest, fmt):
    """mcptoon plugin — Agent Plugins 1.0.0 support (scan / install / list / remove)."""
    if not rest:
        _err("Usage: mcptoon plugin <scan|install|list|remove> [args]")
        _err("")
        _err("Subcommands:")
        _err("  scan <dir>        Validate a plugin package (read-only)")
        _err("  install <dir>     Install a plugin into every agent (v0.7.1)")
        _err("  list              List installed plugins (v0.7.1)")
        _err("  remove <name>     Remove a plugin (v0.7.1)")
        sys.exit(1)

    sub = rest[0]
    if sub == "scan":
        _cmd_plugin_scan(rest[1:], fmt)
    elif sub == "install":
        _cmd_plugin_install(rest[1:])
    elif sub == "list":
        _cmd_plugin_list(fmt)
    elif sub == "remove":
        _cmd_plugin_remove(rest[1:])
    else:
        print(f"Unknown plugin subcommand: {sub}", file=sys.stderr)
        print("Available: scan | install | list | remove", file=sys.stderr)
        sys.exit(1)


def _cmd_plugin_install(args):
    """mcptoon plugin install <dir> [--force] [--no-sync]"""
    from .plugin import install_plugin

    force = "--force" in args
    sync_agents = "--no-sync" not in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print("Usage: mcptoon plugin install <plugin-dir> [--force] [--no-sync]")
        sys.exit(1)

    result = install_plugin(positional[0], force=force, sync_agents=sync_agents)
    if not result["ok"]:
        if result.get("stage") == "scan":
            print("❌ Plugin failed validation — fix these and retry:", file=sys.stderr)
            for f in result["fatal"]:
                print(f"  ❌ [{f['code']}] {f['message']}", file=sys.stderr)
        else:
            print(f"❌ {result.get('message', 'install failed')}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Installed plugin: {result['name']} v{result['version']}")
    print(f"  Plugin dir:  {result['dest']}")
    print(f"  Data dir:    {result['data_dir']}  (kept across upgrades)")
    print(f"  Servers:     {', '.join(result['servers']) or '(none)'}")
    if result["skills"]:
        print(f"  Skills:      {', '.join(result['skills'])}")
    sync = result.get("sync")
    if isinstance(sync, dict) and "synced_agents" in sync:
        print(f"  Synced to:   {sync['synced_agents']}/{sync['total_agents']} agents")
    elif isinstance(sync, dict) and sync.get("error"):
        print(f"  ⚠ sync failed: {sync['error']} — run `mcptoon sync` manually")
    else:
        print("  Sync:        skipped (--no-sync) — run `mcptoon sync` when ready")
    sys.exit(0)


def _cmd_plugin_list(fmt):
    """mcptoon plugin list"""
    import json as _json

    from .plugin import list_plugins

    plugins = list_plugins()
    if fmt == "json":
        print(_json.dumps(plugins, indent=2, ensure_ascii=False))
        return
    if not plugins:
        print("No plugins installed. Try: mcptoon plugin install <dir>")
        return
    print(f"── Installed plugins: {len(plugins)} ──")
    for p in plugins:
        print(f"  {p['name']}  v{p['version']}  ({len(p['servers'])} servers)")
        print(f"    installed: {p['installed_at']}")
        for s in p["servers"]:
            print(f"    · {s}")


def _cmd_plugin_remove(args):
    """mcptoon plugin remove <name> [--no-sync]"""
    from .plugin import remove_plugin

    sync_agents = "--no-sync" not in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print("Usage: mcptoon plugin remove <name> [--no-sync]")
        sys.exit(1)

    result = remove_plugin(positional[0], sync_agents=sync_agents)
    if not result["ok"]:
        print(f"❌ {result['message']}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Removed plugin: {result['name']}")
    for s in result["removed_servers"]:
        print(f"  − {s}")
    if result.get("data_dir_kept"):
        print(f"  Data dir kept: {result['data_dir_kept']}")
    sync = result.get("sync")
    if isinstance(sync, dict) and "synced_agents" in sync:
        print(f"  Synced removal to: {sync['synced_agents']}/{sync['total_agents']} agents")
    sys.exit(0)


def _cmd_plugin_scan(args, fmt):
    """mcptoon plugin scan <dir> — validate an Agent Plugins package."""
    import json as _json

    from .plugin import scan_plugin

    if not args:
        print("Usage: mcptoon plugin scan <plugin-dir>")
        sys.exit(1)

    report = scan_plugin(args[0])

    if fmt == "json":
        print(_json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report["ok"] else 1)

    plugin = report["plugin"]
    name = plugin.get("name") or "(unknown)"
    version = f" v{plugin.get('version')}" if plugin.get("version") else ""

    print(f"── Agent Plugin scan: {report['dir']} ──")
    print(f"  Plugin:  {name}{version}")
    skills = report["skills"]
    print(f"  Skills:  {len(skills)}" + (f" ({', '.join(skills)})" if skills else ""))
    servers = report["servers"]
    skipped = report["skipped_servers"]
    print(f"  Servers: {len(servers)} valid, {len(skipped)} skipped")
    for s in servers:
        print(f"    · {s['name']}  [{s['type']}]")
    for s in skipped:
        print(f"    ✗ {s['name']}  skipped — {s['reason']}")

    for w in report["warnings"]:
        print(f"  ⚠ [{w['code']}] {w['message']}")
    for f in report["fatal"]:
        print(f"  ❌ [{f['code']}] {f['message']}")

    if report["ok"]:
        n_warn = len(report["warnings"])
        tail = f" ({n_warn} warning{'s' if n_warn != 1 else ''})" if n_warn else ""
        print(f"\n  ✅ Valid plugin — ready for mcptoon plugin install{tail}")
        sys.exit(0)
    else:
        print(f"\n  ❌ Plugin rejected — {len(report['fatal'])} fatal issue(s)")
        sys.exit(1)


# ═══════════════════════════════════════════════════
# Natural language fallback
# ═══════════════════════════════════════════════════

def _try_natural(command, rest, fmt, head_n, max_chars, full):
    """Try to interpret natural language input.

    Only genuine phrases are routed here. A *single* mistyped word that happens
    to contain a keyword as a substring used to be treated as natural language:
    `mcptoon listt` matched "list" inside the word and ran `manifest`, and
    `mcptoon healthh` matched "health" and ran the health check — both exiting 0,
    so a typo'd command in a CI step reported success (reported 2026-10-18). A
    single bare word (no extra arguments) must be a real command; anything else
    falls through to the "unknown command" path with a did-you-mean hint.
    """
    text = " ".join([command] + rest).lower()

    # A lone word that is *close to a real command* is a mistyped command, not a
    # phrase. `mcptoon listt` matched "list" inside the word and ran `manifest`,
    # and `mcptoon healthh` matched "health" and ran the health check — both
    # exiting 0, so a typo'd command in a CI step reported success (reported
    # 2026-10-18). Refuse to keyword-match a near-command so the typo surfaces as
    # an error. A genuine single-token phrase (e.g. `mcptoon 有什么工具`) is not
    # close to any command, so it still reaches the keyword routing below.
    if not rest and _closest(command, _COMPLETION_COMMANDS):
        print(f"mcptoon: unknown command '{command}'", file=sys.stderr)
        print(f"  did you mean: {', '.join(_closest(command, _COMPLETION_COMMANDS))}?",
              file=sys.stderr)
        print("Run 'mcptoon help' for the command list, or 'mcptoon --help'.",
              file=sys.stderr)
        sys.exit(1)

    if any(kw in text for kw in ["什么", "有哪些", "工具", "tools", "list", "manifest"]):
        _cmd_manifest(rest, fmt, head_n, max_chars, full)
        return

    if any(kw in text for kw in ["服务器", "server", "list server"]):
        _cmd_list(rest)
        return

    if any(kw in text for kw in ["搜工具", "找工具", "search tool", "search"]):
        _cmd_search(rest, fmt, head_n, max_chars, full)
        return

    if any(kw in text for kw in ["发现", "搜索服务器", "discover", "auto-discover"]):
        _cmd_auto_discover(rest, fmt, head_n, max_chars, full)
        return

    if any(kw in text for kw in ["健康", "health", "check"]):
        _cmd_health_check(rest, fmt, head_n, max_chars, full)
        return

    # Not a command and not natural language we recognise. This is a failure:
    # write it to stderr and exit non-zero. It used to `print` to stdout and fall
    # off the end of `main` returning 0, so a typo'd command in a CI step or a
    # `mcptoon x && next` chain reported success and the error was lost from
    # stderr (reported 2026-10-17: `mcptoon notacommand` -> exit 0, stderr 0 bytes).
    print(f"mcptoon: unknown command '{command}'", file=sys.stderr)
    near = _closest(command, _COMPLETION_COMMANDS)
    if near:
        print(f"  did you mean: {', '.join(near)}?", file=sys.stderr)
    print("Run 'mcptoon help' for the command list, or 'mcptoon --help'.", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════

def _print_command_help(command: str) -> None:
    """Print one command's own usage page (or the global page if it has none).

    Shared by `<command> --help` and `mcptoon help <command>` so the two routes
    cannot drift. Deliberately short: the command's own usage, an `Options for`
    line, and a one-line pointer to `mcptoon --help` — never a re-dump of the whole
    global reference (that made `skills --help` longer than the front door).
    """
    usage = _command_usage(command)
    if not usage:
        _print_help()
        return
    lines = usage.splitlines()
    first = lines[0].strip()
    body = "\n".join(lines[1:]).strip()
    # Name the command in a header so `mcptoon manifest --help` says which command
    # it is describing. Some docstrings (skills) already open with "mcptoon <cmd>
    # — ..."; don't double the prefix.
    if first.lower().startswith("mcptoon"):
        print(first)
    else:
        print(f"mcptoon {command} — {first}")
    if body:
        print()
        print(body)
    flags = _command_flags(command)
    if flags:
        print()
        print(f"Options for '{command}': {', '.join(flags)}")
    print()
    print("Global flags and every other command: run 'mcptoon --help'.")


def _command_usage(command: str) -> str:
    """The command's own usage text: its handler's docstring, cleaned up.

    `skills --help`, `docs --help`, `quickstart --help` used to print the general
    help page byte-for-byte — the subcommand's own flags were undiscoverable
    (reported 2026-10-17). The handler docstrings already carry a `Usage:` block
    for most commands; this renders the one for the command asked about. Returns
    "" when the command is unknown or its handler has no docstring, and the caller
    falls back to the general help alone.
    """
    handler = _COMMAND_HANDLERS.get(command)
    if handler is None:
        handler = _lazy_handler(command)
    if handler is None:
        return ""
    doc = inspect.getdoc(handler)
    if not doc and command == "skills":
        # `_cmd_skills` dispatches subcommands and carries no docstring; its own
        # usage lives in `_skills_usage()`.
        try:
            from .skills import _skills_usage
            return _skills_usage()
        except Exception:
            return ""
    if not doc:
        return ""
    return textwrap.dedent(doc).strip()


def _command_flags(command: str) -> list[str]:
    """The long options named in the command's own usage docstring, in first-seen order.

    A compact, accurate answer to "what options does THIS command take?" without
    re-printing the whole global reference. Reads the same docstring `_command_usage`
    renders, so the two never disagree. Only long options are collected; global
    flags live on the `mcptoon --help` page the caller points at.
    """
    text = _command_usage(command)
    if not text:
        return []
    seen = []
    for tok in re.findall(r"--[a-zA-Z][a-zA-Z0-9-]*", text):
        if tok not in seen:
            seen.append(tok)
    return seen


def _lazy_handler(command: str):
    """Resolve a handler that lives in a lazily-imported module, or None."""
    try:
        if command == "skills":
            from .skills import _cmd_skills
            return _cmd_skills
        if command == "docs":
            from . import docs as _docs
            return _docs.run
        if command == "report":
            from . import report as _report
            return _report.run
        if command == "savings":
            from . import savings as _savings
            return _savings.run
        if command == "update":
            from . import update as _update
            return _update.run
        if command == "upgrade":
            from . import upgrade as _upgrade
            return _upgrade.run
        if command == "bench":
            from . import bench as _bench
            return _bench.run_bench
    except Exception:
        return None
    return None


# command (and its aliases) -> the handler whose docstring documents it. Used only
# for `mcptoon <command> --help`; the dispatch chain stays the source of truth for
# behaviour. Commands with their own help page (serve/demo/demo-server) are absent
# on purpose — they print their own and never reach `_command_usage`.
_COMMAND_HANDLERS: dict[str, object] = {}


def _print_help():
    print(f"""mcptoon v{__import__('mcptoon').__version__} — one gateway for all your MCP tools
                       compressed · visible · reversible

Start here:
    mcptoon quickstart                    One-command setup (discover + config + wire agents)
    mcptoon status                        What's here, what it saves, how to undo it
    mcptoon off                           Remove the gateway from your agents (reversible)
    mcptoon restore                       Drop the gateway and put your servers back
    mcptoon uninstall                     Full cleanup (--dry to preview)

Usage:
    mcptoon quickstart                    One-command setup (discover + config + show tools)
    mcptoon list                          List configured servers
    mcptoon manifest                      List all tools (compact)
    mcptoon manifest --full               List all tools with params
    mcptoon manifest --format openai      Export as OpenAI function calling format
    mcptoon manifest --format openapi     Export as OpenAPI 3.0 spec
    mcptoon manifest --format mcp         Export as MCP tools/list format
    mcptoon discover                      Auto-discover MCP servers (scan + probe)
    mcptoon discover --write              Discover + write to config
    mcptoon discover --http <url>         Probe a specific HTTP MCP endpoint
    mcptoon discover --health             Health check (legacy discover behavior)
    mcptoon import                        Import servers from Claude/Cursor/Cline/Windsurf
    mcptoon import --from cursor          Import from one client only
    mcptoon import --file servers.json    Import from any exported config file
    mcptoon import --write                Merge imported servers into your config
    mcptoon inspect <server> <tool>       Show tool schema
    mcptoon search <query>                Search tools across all servers
    mcptoon select "<task>"               Top tools for a task (past ~40 tools models pick wrong)
    mcptoon call <server> <tool> [ARGS]   Call a tool
    mcptoon call --auto <tool> [ARGS]     Call a tool (auto-find server)
    mcptoon call <server> <tool> --stdin  Read args from stdin (large payloads)
    mcptoon openapi list <spec>           Drive any OpenAPI/Swagger REST API as commands
    mcptoon openapi call <spec> <cmd>     Call one operation (params: name=value)
    mcptoon graphql list <endpoint>       Drive any GraphQL endpoint as commands
    mcptoon graphql call <endpoint> <cmd> Call one query/mutation (--fields "a b")
    mcptoon auth login <name> ...         OAuth login (PKCE) for a protected API
    mcptoon auth creds <name> ...         OAuth client-credentials token
    mcptoon auth status <name>            Show token state (never the token)
    mcptoon resources list [server]       List a server's MCP resources
    mcptoon resources read <server> <uri> Read one resource by URI
    mcptoon prompts list [server]         List a server's prompt templates
    mcptoon prompts get <server> <name>   Render a prompt with arguments
    mcptoon complete <server> <ref>       Ask server to complete an argument value
    mcptoon bake create <name> ...        Save a connection under a short name
    mcptoon bake run <name> <action> ...  Reuse a saved connection
    mcptoon bake list|show|remove|install Manage saved connections
    mcptoon exec <lang> "<code>"          Run code; only its stdout enters context
    mcptoon exec <lang> --file <path>     Run a script file the same way
    mcptoon exec --langs                  List the runtimes this machine can run
    mcptoon init                          Create sample config
    mcptoon init --auto                   Auto-discover all MCP servers
    mcptoon init --auto --http <url>      Auto-discover + add HTTP MCP endpoint
    mcptoon add <name> [options]          Add a server
    mcptoon remove <name>                 Remove a server
    mcptoon usage                         Show usage stats
    mcptoon activity                      Who used mcptoon, when, on what (last 20 calls)
    mcptoon activity --summary            Totals: today, last host, by host
    mcptoon status                        One-screen: what's here and what it saves
    mcptoon stats                         Token-savings dashboard (vs raw JSON)
    mcptoon report                        Whole savings account on one screen
    mcptoon savings                       Milestones you've crossed (1B? 4,700 novels?)
    mcptoon credit                        One screen: your mode, what it really saves, one action
    mcptoon mode                          Which delivery mode you're in (cli/serve/direct), what each costs
    mcptoon mode recommend                Which mode THIS host should use, and the one action to get there
    mcptoon statusline                    One-line savings badge for a status bar / turn header
    mcptoon statusline --install          Wire that badge into Claude Code's status bar (undo: --uninstall)
    mcptoon footer-facts                  One line of savings for a chat footer
    mcptoon retrieve <handle>             Get back the original behind a --smart handle
    mcptoon retrieve --list               Show what the retrieve store holds right now
    mcptoon config                        Show gateway settings (footer, welcome)
    mcptoon config set footer off         Silence the per-turn savings line
    mcptoon toggle <server> <tool>        Enable/disable one tool (--list to show)
    mcptoon policy                        Per-tool compression policy (raw/toon/slim/smart)
    mcptoon doctor                        Self-diagnose config + connectivity
    mcptoon completion <shell>            Generate shell completion (bash|zsh|fish|ps)
    mcptoon completion <shell> --install  Write it into that shell's rc file (idempotent)
    mcptoon install <name> --npm <pkg>    Install MCP server from npm
    mcptoon install <name> --pip <pkg>    Install MCP server from pip
    mcptoon install <name> --url <url>    Install HTTP/SSE MCP server
    mcptoon install --list                List installed servers
    mcptoon install --remove <name>       Remove an installed server
    mcptoon update                        Refresh cached tool surface; report server drift
    mcptoon update --check                Report drift only, write nothing (exit 1 if moved)
    mcptoon upgrade                       Update mcptoon itself to the latest PyPI release
    mcptoon upgrade --check               Report only; exit 1 if a newer release exists

    mcptoon plugin scan <dir>             Validate an Agent Plugins 1.0.0 package
    mcptoon plugin install <dir>          Install a plugin into every agent
    mcptoon plugin list                   List installed plugins
    mcptoon plugin remove <name>          Remove a plugin

    mcptoon serve                         Run as MCP server (stdio bridge for agents)
    mcptoon serve --http --auth           HTTP mode; bare --auth auto-generates a token
    mcptoon serve --background --http     Detach: keep serving after the terminal closes
    mcptoon serve --status                Check the background instance; --stop to end it
    mcptoon demo                          Zero-config one-command demo
    mcptoon demo --quick                  Results only, skip the step-by-step narration
    mcptoon demo --keep                   Leave the demo server in config afterwards
    mcptoon demo-server                   Self-contained MCP demo server (11 tools, no network)
    mcptoon add demo --stdio python -m mcptoon demo-server
    mcptoon --version                     Print the installed version and exit
    mcptoon sync                          Sync config to all agents (Claude Desktop, Cursor, etc.)
    mcptoon sync --dry                    Preview without writing
    mcptoon sync --agent <id>             Sync to one agent only
    mcptoon sync --self                   Also register the mcptoon gateway itself in each agent
    mcptoon sync --takeover               Route managed servers through the gateway (implies --self)
    mcptoon health                        Health check all MCP servers
    mcptoon health --json                 JSON output for CI/CD (exit 1 if dead)

    mcptoon skills list                   List the agent skill catalog (--usage adds hit counts)
    mcptoon skills resolve <query>        BM25 shortlist of skills (offline, no LLM)
    mcptoon skills sync [SRC] [VIEW...]   Distribute a skill catalog to every agent's folder
    mcptoon skills add|remove <name>      Create a skill in the source / retire it to the archive

    mcptoon docs index <dir>              Index a Markdown tree so agents stop reading it whole
    mcptoon docs resolve <query>          Best files for a query (returns paths, offline)
    mcptoon docs list                     Every indexed document, by slug
    mcptoon docs doctor                   Check the docs index against the disk

    mcptoon kb index <path>               Index documents so you can search inside them
    mcptoon kb fetch <url>                Fetch a URL and index it (24h TTL cache)
    mcptoon kb search "<query>"           Ranked passages (porter + trigram, RRF)
    mcptoon kb list                       Indexed sources with size and age
    mcptoon kb stats                      Chunks, DB size, trigram support

    mcptoon session                       What happened this session (catch up after a compact)
    mcptoon session --purge               Delete this project's event log

    mcptoon bench                         Prove the savings on your own machine (tools + skills)
    mcptoon bench --json                  Machine-readable; --roots/--query/-k tune the skills half

Output flags:
    --toon         Standard TOON (toon-format/toon spec). Saves 5.7% vs JSON on a
                          mixed call-result sample; 1.8%-48.6% depending on result
                          shape (reproduce: scripts/make_benchmark.py)
    --mcptoon      Legacy mcptoon pipe format (saves 20-40% tokens)
    --slim         Ultra-compact tool manifests (saves 88.5% tokens, measured)
    --smart        Structure-aware result compression (keeps keys, cuts payload)
    --json         JSON output (never char-truncated — pipe it into jq)
    --compact      Names only
    --stdin        Read JSON args from stdin (for large payloads)
    --head N       Limit to the first N items — the format-agnostic way to shrink
                          a big payload (cuts records, not bytes, so the result stays
                          valid in every format)
    --max-chars N  Truncate to N chars (default 4000 for human-readable formats;
                          --json/--toon are capped only when you pass this)
    --full         No truncation
    --format X     Export: openai|openapi|mcp|json|human
    --fallback-json  Fall back to JSON if TOON encoding fails

Examples:
    mcptoon init
    mcptoon manifest --toon               # standard TOON format
    mcptoon manifest --mcptoon            # legacy pipe format
    mcptoon manifest --slim               # ultra-compact tool schemas
    mcptoon call fetch fetch '{{"url":"https://example.com"}}' --toon
    echo '{{"huge":"payload"}}' | mcptoon call server tool --stdin --toon
    mcptoon discover
    mcptoon doctor

Environment:
MCPTOON_AGENT_TYPE=claude    Auto-select --toon (optional)
MCPTOON_AGENT_TYPE=openai    Auto-select --json (default)

Config: ~/.mcptoon/config.json
""")


# ═══════════════════════════════════════════════════
# New commands (v0.6+)
# ═══════════════════════════════════════════════════

def _cmd_serve(rest):
    """Run as MCP server (stdio bridge for agents)."""
    from .serve import run_serve
    run_serve(rest)


def _cmd_demo(rest):
    """Zero-config one-command demo."""
    from .demo import run_demo
    run_demo(rest)


def _cmd_demo_server(rest):
    """Run the built-in, self-contained demo MCP server over stdio."""
    from .demo_server import run_demo_server
    run_demo_server(rest)


def _print_takeover_plan(plan):
    """Show the entries `--takeover` is about to remove, before it removes them.

    This is the subtraction half of Write Consent (CONTEXT.md): additions — our own
    entry, a pointer, a skill — may be silent, but takeover deletes server entries
    the user wrote into a host config, so it is listed and confirmed once first.
    Nothing has been written when this prints; it is a plan, not a result.
    """
    line = "─" * 54
    print(line)
    print("  mcptoon sync --takeover")
    print(line)
    print("  This will remove these server entries from your agent configs and")
    print("  route them through the mcptoon gateway instead:")
    for row in plan:
        print(f"    · {row['agent_name']}: {', '.join(row['servers'])}")
        print(f"        {row['path']}")
    print("")
    print("  A `<config>.bak` is written alongside each file first, so this is")
    print("  reversible: `mcptoon restore` puts your original servers back.")
    print(line)


def _cmd_sync(rest, fmt):
    """Sync mcptoon config to AI agent config files.

    Usage:
        mcptoon sync                 # sync to all detected agents
        mcptoon sync --dry           # preview without writing
        mcptoon sync --agent cursor  # sync to specific agent only
        mcptoon sync --agent claude-desktop
        mcptoon sync --agent windsurf
        mcptoon sync --self          # ALSO register `mcptoon serve` in each agent
        mcptoon sync --takeover      # route managed servers through the gateway
                                     # (removes their direct host entries; implies --self)
                                     # lists what it will remove and asks first
        mcptoon sync --takeover --dry # preview the removal plan, change nothing
        mcptoon sync --takeover --yes # skip the confirmation (scripted runs)
        mcptoon sync --no-self       # explicit servers-only (the default)
        mcptoon sync --watch         # keep syncing as configs change
        mcptoon sync --watch --interval 5 --quiet --watch-mode strict
    """
    from .sync import (sync_to_all, sync_to_agent, format_sync_report,
                       takeover_plan)

    dry_run = "--dry" in rest or "--dry-run" in rest
    # Default OFF, unlike `quickstart`: `sync` is a routine, repeatable command, and
    # silently injecting a *new* server entry into an agent's config on every routine
    # run would be a surprise. `--self` opts in; `quickstart` (the install path) turns
    # it on by default, and `mcptoon status` points here when the gateway is missing.
    include_self = "--self" in rest
    # Takeover is the "the gateway *is* the connection" mode: remove each upstream
    # server the gateway manages from the host config and reach it through mcptoon
    # instead. Opt-in, because it edits entries the user may have written by hand —
    # but it is the only mode that makes the compressed schema actually land.
    takeover = "--takeover" in rest
    if takeover:
        include_self = True

    # --watch: continuous sync loop (see watch.py)
    if "--watch" in rest:
        from .watch import main as watch_main
        sys.exit(watch_main(rest))

    # Parse --agent
    agent_id = None
    for i, a in enumerate(rest):
        if a == "--agent" and i + 1 < len(rest):
            agent_id = rest[i + 1]
            break
        elif a.startswith("--agent="):
            agent_id = a.split("=", 1)[1]
            break

    # Takeover is the one subtraction in `sync`: it removes server entries the user
    # wrote into a host config, so — unlike the additive `--self` — it lists what it
    # will drop and confirms once (CONTEXT.md: Write Consent). `--dry` prints the
    # same plan and stops; `--yes` is the explicit opt-in for scripted runs. An empty
    # plan means there is nothing to remove, so there is nothing to ask.
    if takeover:
        plan = takeover_plan(agent_id)
        if plan:
            _print_takeover_plan(plan)
        else:
            print("  mcptoon sync --takeover: nothing to remove — no agent config "
                  "carries an entry mcptoon manages.")
        print("")
        if dry_run:
            print("  Dry run — nothing was removed. Re-run without --dry to apply.")
            print("")
            return
        if plan and not ("--yes" in rest or "-y" in rest):
            # Non-interactive stdin (CI, piped) cannot answer: refuse rather than
            # remove silently. --yes is the opt-in. Same guard as `uninstall`, for
            # the same reason: a Windows NUL stdin reports isatty() True, so the
            # prompt below is reached and an EOF answer is simply not "yes".
            if not sys.stdin.isatty():
                print("  Refusing to remove entries without confirmation. Re-run with --yes.")
                print("")
                return
            try:
                answer = input("  Remove the entries above? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if answer in ("n", "no"):
                print("  Cancelled — nothing was removed.")
                print("")
                return
            print("")

    if agent_id:
        result = sync_to_agent(agent_id, dry_run=dry_run, include_self=include_self,
                               takeover=takeover)
        report = format_sync_report([result], dry_run=dry_run)
    else:
        results = sync_to_all(dry_run=dry_run, include_self=include_self,
                              takeover=takeover)
        report = format_sync_report(results, dry_run=dry_run)

    print(report)
    if include_self and not dry_run:
        print("")
        print("  Gateway registered: agents can now see mcptoon itself (`mcptoon serve`).")
        if takeover:
            print("  Takeover: managed servers now reach the agent through the gateway.")
            print("  Undo any time: `mcptoon restore` (puts your original servers back)")
        else:
            print("  Undo any time: mcptoon off")


def _cmd_health(rest, fmt):
    """Health check all configured MCP servers.

    Usage:
        mcptoon health                # check all servers
        mcptoon health --timeout 5    # 5 second timeout per server
        mcptoon health --json         # JSON output (for CI/CD)
    """
    from .health import check_all, format_health_report

    timeout = 10.0
    for i, a in enumerate(rest):
        if a == "--timeout" and i + 1 < len(rest):
            try:
                timeout = float(rest[i + 1])
            except ValueError:
                _err(f"  --timeout needs a number (seconds), got {rest[i + 1]!r}")
                sys.exit(1)
            break

    # JSON output for CI/CD
    if fmt == "json" or "--json" in rest:
        import json as _json
        results = check_all(timeout=timeout)
        print(_json.dumps(results, ensure_ascii=False, indent=2))
    else:
        results = check_all(timeout=timeout)
        print(format_health_report(results))

    # Exit 1 if any server is dead, in BOTH output modes. The JSON path already
    # did this; the human-readable path printed "1 dead" and exited 0, so
    # `mcptoon health && deploy` (or a CI check reading the exit code) treated a
    # machine with an unreachable server as healthy (reported 2026-10-17). The
    # two modes must agree on what "unhealthy" means.
    dead = sum(1 for r in results if r["status"] in ("error", "timeout"))
    if dead > 0:
        sys.exit(1)


# ─── Per-command usage registry (populated last, once every handler exists) ───
# Only the handlers defined in this module; the lazy-imported ones (docs, report,
# update, skills, bench) are resolved by `_command_usage` through a small fallback.
def _populate_command_handlers() -> None:
    mapping = {
        "list": _cmd_list, "servers": _cmd_list,
        "manifest": _cmd_manifest, "tools": _cmd_manifest,
        "inspect": _cmd_inspect, "search": _cmd_search, "select": _cmd_select,
        "call": _cmd_call, "exec": _cmd_exec, "quickstart": _cmd_quickstart, "qs": _cmd_quickstart,
        "init": _cmd_init, "add": _cmd_add, "remove": _cmd_remove,
        "usage": _cmd_usage, "status": _cmd_status, "brief": _cmd_status,
        "stats": _cmd_stats, "retrieve": _cmd_retrieve, "activity": _cmd_activity,
        "footer-facts": _cmd_footer_facts, "toggle": _cmd_toggle,
        "mode": _cmd_mode, "statusline": _cmd_statusline, "credit": _cmd_credit,
        "policy": _cmd_policy, "import": _cmd_import, "doctor": _cmd_doctor,
        "install": _cmd_install, "completion": _cmd_completion,
        "sync": _cmd_sync, "off": _cmd_off, "restore": _cmd_restore,
        "uninstall": _cmd_uninstall, "health": _cmd_health, "plugin": _cmd_plugin,
        # `config` was missing from this map even though `_cmd_config` has a Usage
        # docstring, so `mcptoon config --help` fell through to the whole global
        # page and never showed its own get/set/unset/reset syntax (reported
        # 2026-10-17).
        "config": _cmd_config,
    }
    _COMMAND_HANDLERS.update(mapping)


_populate_command_handlers()
