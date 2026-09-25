# Changelog

All notable changes to mcptoon will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **The gateway withholds the upstream tool list by default.** `serve` used to
  enumerate every upstream tool with a simplified schema — the cost that made a
  mounted gateway save ~0 on this machine once the host also listed its servers
  directly. `tools/list` now returns only mcptoon's own tools; upstream tools stay
  fully callable (`mcptoon_manifest` names them, `mcptoon_inspect` shows one
  schema, `mcptoon_call` runs it) but are no longer enumerated. Measured against a
  real `mcptoon serve` handshake on a 12-server / 96-tool machine, `tiktoken
  cl100k_base`: **18,686 → 2,607 tokens per turn (−86.0%)**. This is the "compact
  manifest" ADR 0004 originally promised ("Claude Code 只看到 1 个 MCP server")
  and ADR 0006's layered schemas had not delivered.
- The handshake now explains where the tools went, in a second directive
  independent of the savings line: `mcptoon config set footer off` no longer also
  hides the tool-location note, since under the new default that note is the only
  thing telling the model the user's MCP servers still exist.
- Roll back with one command — no host config edit, no reinstall:
  `mcptoon config set exposure full`. Both the setting's value and its default are
  validated, so a typo fails loudly instead of persisting a mode nothing honours.

### Added

- **Both legs now land on a host that can carry them.** `sync --self` already
  mounted `mcptoon serve` in every agent whose config holds MCP servers, and wrote
  a skill pointer for Codex. Claude Code can do both — it mounts servers in
  `~/.claude.json` *and* reads `~/.claude/CLAUDE.md` as machine-wide context on
  every session — so it now gets the mount and the pointer. The two are
  independent: the mount gives the host native tools, the pointer gives it the
  catalog in words, and neither is as good alone. `mcptoon off` removes both,
  restoring the memory file byte for byte (the block is heading-anchored and cut at
  the next `## `).
  A host is included only on evidence that its file is read **every** session:
  Codex (`AGENTS.md`) and Claude Code (`CLAUDE.md`). Cursor is deliberately left
  out — `~/.cursorrules` is the legacy form, so a pointer there could be a silent
  no-op, which is worse than not writing one. Windsurf, Cline and VS Code Copilot
  expose no dedicated global instruction file and stay MCP-only rather than risk
  editing a file the user shares with everything else.
- **mcptoon's own skill now ships in the wheel and installs itself.** The skill
  that explains the exposure presets, and what to do when a tool panel looks
  empty, existed in the repo but never reached a `pip install`: every builtin pack
  carried `"skills": []`, `install_pack` only wrote `PROMPT.md`, and the only
  channel that shipped it was the Claude Code plugin. `quickstart` now copies it
  into each agent's skill folder (best-effort — never fails onboarding), and
  `mcptoon skills install-self [--view DIR] [--dry]` repairs a machine where it is
  missing. Only a file whose frontmatter declares `name: mcptoon` is treated as
  ours: a missing one is created, and our own **stale** one is refreshed — otherwise
  an upgrading user keeps the copy from the release they first installed and never
  reads the new defaults. A view holding a *different* skill is still left
  completely alone, because another manager may own that folder and two managers
  writing one view is how a catalog gets clobbered.
  `tests/test_skill_package.py` pins the three distribution copies byte-identical
  and pins `skill/SKILL.md` into `package-data`.
- **The first command on a machine finishes the install `pip` could not.** A
  `pip install` runs no code, so it landed the package and nothing else: the skill
  sat in site-packages where no agent reads it, and no skill index existed, so a
  user who never ran `quickstart` stayed half-installed while the docs promised
  "pip install, then just use it". Now the first real command (anything but
  `serve`/`off`/`uninstall`/`demo`) installs the agent-visible skill and builds
  the skill index, then stops. It is the *additive* half of the write-consent
  rule: it creates a missing skill, refreshes our own stale copy, and never touches
  a skill that is not ours; it is silent for pipes and machine formats, like the
  welcome it rides beside. The marker records the installed skill's fingerprint, so
  a release that ships a new skill heals once more instead of being suppressed by
  the previous release's marker. `uninstall` clears the marker, so a clean
  reinstall self-heals again.
- **`exposure` setting (`compact` | `full`).** `compact` is the default and the
  cheaper preset; `full` restores the previous enumeration for a host whose tool
  panel reads `tools/list`, or a model that will not ask for the manifest first.
  Switching takes effect on the host's next connection.
- **`sync --takeover`: the gateway becomes the connection, not another server.**
  `quickstart` and `sync --self` registered `mcptoon serve` *alongside* every
  upstream server, so a host that already listed its servers kept loading all of
  their tool schemas directly — the gateway added a line and saved nothing, which
  is the opposite of what the tool exists for. `mcptoon sync --takeover` removes
  each server mcptoon manages from the host config and reaches it through the
  gateway instead (a server mcptoon does not manage is left alone, since the
  gateway cannot serve it). Implies `--self`. The change is reversible: the
  existing `<config>.bak` written on first change is the undo, and `mcptoon off`
  still removes only the gateway entry. `sync --dry` and the sync report now name
  how many direct entries were replaced (`−N direct, now via gateway`).

  Measured on a real 12-server / 96-tool catalog (this repo's own dev box, same
  tiktoken caliber `status` and `bench` use): mounting the upstreams directly
  costs **21,074** tokens of tool schemas, and the gateway entry added on top
  costs another **2,607** under the default compact exposure (**18,686** if
  `exposure=full`) — the same tools reaching the agent twice. Takeover drops the
  direct half, so the host's tool context goes **23,681 → 2,607** instead of
  growing. That is the difference between "installed" and "installed and worth
  installing".
  Takeover is a *subtraction* — it removes server entries the user wrote into a
  host config — so it now lists exactly what it will drop and asks once before
  doing it. `--dry` prints the plan and stops, `--yes` skips the prompt for
  scripted runs, and a declined or unanswerable prompt writes nothing. The
  additive `--self` stays silent: additions are reversible and lose nothing,
  removals are not.
- **`quickstart` now *offers* takeover instead of quietly saving nothing.** The
  additive default above is safe but near-worthless on a machine whose servers are
  already registered directly — the host keeps loading every upstream schema, so the
  install that promised savings delivers ~0. `quickstart` therefore ends onboarding
  with a **red warning** that says so, lists exactly which direct entries it would
  replace, and asks once: answering yes routes them through the gateway (via
  `sync --takeover --yes`), anything else keeps the safe default. It is an offer,
  never a default flip — the additive path is unchanged — and it obeys the same
  consent bounds as every other prompt here: silent under `--dry`, machine formats,
  `--no-self`, an empty removal plan, and `MCPTOON_NO_TAKEOVER_OFFER`; a
  non-interactive stdin is never asked and is pointed at `mcptoon sync --takeover`
  instead. The colour comes from one new choke point, `welcome.paint`, which returns
  plain text for a pipe or `NO_COLOR`, so no escape codes reach a captured
  transcript.
- **The skill catalog is now reachable over MCP.** `serve` published tools and
  `mcptoon skills` managed skills, but an agent connected to the gateway could not
  see or resolve a skill without shelling out to the CLI. Two first-party tools close
  that gap: `mcptoon_skills` lists the catalog (`slug` + one-line description), and
  `mcptoon_resolve_skills` takes a task and returns the best-matching skills from the
  same offline BM25 the CLI uses. Both are read-only and need no upstream servers, so a
  gateway that only ever proxied tools can now answer "which skill should I load?".
  The projection lives in `skills.catalog_rows` / `skills.resolve_shortlist`, shared by
  the CLI and the tools, so the two surfaces cannot rank differently; `resolve` also
  records the same usage counts, so `mcptoon skills list --usage` reflects MCP calls.

### Fixed

- **`mcptoon_inspect` and `mcptoon_call` now actually exist.** The compact
  exposure's whole safety argument is that withholding the tool list withholds
  *visibility*, not *capability* — "`mcptoon_manifest` names them,
  `mcptoon_inspect` shows one schema, and `mcptoon_call` runs it". The last two
  were named in the handshake directive, in the skill, and in ADR 0012, but had
  never been implemented: a real `tools/call` for either returned `Unknown tool`.
  Under the default preset an agent could therefore learn an upstream tool's
  *name* but not its *parameters*, so "the tools still work" held only if it
  guessed the arguments. Both are implemented now — `mcptoon_inspect` returns one
  upstream tool's full input schema, and `mcptoon_call` routes `{name, arguments}`
  back through the bridge's own call path, so it inherits schema validation,
  danger checks, output compression and usage tracking rather than forking them.
  The lesson is the test that was missing, not the code: the old test asserted the
  tool *index* still held the tool and never called one, so a green suite proved
  nothing about callability. `tests/test_native_tools.py::TestCallBridge` now
  performs real calls. The two tools cost **469** tokens per turn on the default
  path (2,138 → 2,607), which is why the skill and the ADR quote the new number.
- **`mcptoon config set` now exits non-zero when it rejects a value.** A bad value
  left the setting unchanged but still exited 0, so
  `mcptoon config set exposure compakt && restart` read as a successful preset
  change. A refusal is a failure and now reports like one.
- **`sync` verifies the gateway entry survived its own write.** A successful
  `write_text` is not proof the entry is there: Claude Code rewrites
  `~/.claude.json` on its own schedule, and an observed race dropped the
  `mcptoon` entry back out seconds after a sync that reported success. The write
  is now read back, and a lost gateway entry returns `written: False` with a
  warning naming the file — a silent loss only surfaces later, as a user
  wondering why their tools vanished.
- **`skills sync` no longer mistakes an agent view for the catalog.** With no
  source argument the command took the first default root (`~/.claude/skills` and
  friends) as its source — but those paths are exactly where the agent *views*
  live. On a machine whose view is a real directory rather than a link back to the
  catalog, a sync would read the view and republish it into every view, freezing a
  copy as if it were the truth, with nothing in the output to say so. A default
  root now counts as a source only when it is a link to the real catalog; a plain
  directory there is refused, and the caller is asked to name the source.
- **21 skills were invisible to the catalog, and a deleted skill never left it.**
  Found by running the new staleness probe against this machine's real 407-skill
  catalog rather than the fixtures:
  - The walk matched the manifest as `child / "SKILL.md"`. On Windows that found
    the 21 skills that spell it `skill.md` — but only because NTFS folds case;
    the same code on Linux would have dropped every one of them, and a stricter
    `== "SKILL.md"` comparison drops them everywhere. The manifest name is now
    matched case-insensitively, so the catalog is the same on every platform.
  - Staleness was "is any SKILL.md newer than the index file", which cannot see a
    *deletion* (the files that remain are not newer) — a hand-removed skill kept
    answering from the index. The index now stores a signature over the whole
    listing (path, size, mtime of every manifest) and compares against it, so an
    add, an edit and a delete are all detected. Verified against the real
    catalog: deleting a skill and re-resolving removed it (408 → 407) with no
    manual `skills index`.

- **Concurrent skill resolves lost their usage counts.** `record_skill_use` was a
  bare read-modify-write, and two callers reach it now — the CLI (`resolve`/`route`)
  and the MCP tool (`mcptoon_resolve_skills`). Measured 2026-09-24: 30 concurrent
  resolves recorded a count of 1, each thread having read the old file and written
  back the same `+1`. It is now serialized in-process and written atomically (unique
  tmp name + `os.replace`), the same discipline `usage._save_usage` already used, so a
  reader can never catch a torn file either. The count is what `list --usage` shows,
  so losing 29 of 30 was a visible lie about which skills earn their keep.

- **The skill index no longer needs a manual step, and the CLI-only hosts now
  actually get the pointer.** Four gaps that together meant "installed" did not
  mean "working":
  - `mcptoon skills index` was required before `resolve`/`route`/the MCP tools
    would answer anything, and a skill added afterwards stayed invisible until it
    was re-run. The index now builds itself on first use and rebuilds when the
    catalog on disk no longer matches the signature it was built from — a
    stat-only probe (measured 0.25s cold, 0.03s warm for this machine's 1,217
    manifests, against 0.4s for a full parse), so it rides every resolve.
    `list`/`stats` stay strict readers and never build one as a side effect.
    `mcptoon quickstart` also builds it at the end of onboarding, so the catalog
    is answerable the moment the install finishes.
  - The `codex` sync target wrote to `Path.cwd()/AGENTS.md` — the pointer landed
    in whichever project the user happened to be in, or nowhere — and its text
    named only `mcptoon manifest`, never the catalog. It now targets
    `~/.codex/AGENTS.md`, writes a skill pointer, is idempotent, and is gated on
    `--self` like the gateway registration. The undo (`mcptoon off`) removes
    exactly that block, byte-for-byte.
  - `codex` was not in `detect_installed_agents`, so the automatic path never
    reached it. It is now detected by the presence of its AGENTS.md.
  - **Claude Code** was not a sync target at all, though it is the host where the
    MCP handshake was verified working. `~/.claude.json` (flat `mcpServers`, the
    same shape as Cursor) now syncs, and it is detected when the file exists.

### Changed

- **The handshake now points at the skill tool, and costs less.** The `instructions`
  field of the initialize result is the one channel that reaches the model without a
  tool call, and it talked only about the savings line. It now opens by naming
  `mcptoon_resolve_skills`: a list of tools says nothing about *when* to reach for one,
  so an agent that never sees a skill list in its prompt had no reason to call a
  resolver. The same edit tightened the rest of the paragraph, so the whole block went
  from 351 to 314 tokens — the pointer was paid for out of prose, not added on top. The
  directive names the mounted tool rather than the shell command, because the reader
  always has this gateway and may have no shell.

## [0.7.23] - 2026-09-24

### Fixed

- **The nix package could not build 0.7.22.** `TestInstallByName`'s three tests call
  the real MCP Registry and Smithery APIs; the nix build sandbox has no network and no
  CA certificates, so they failed with `CERTIFICATE_VERIFY_FAILED` / DNS errors and
  turned `numtide/llm-agents.nix` PR #9829 red on all three platforms. The calls now
  retry twice and skip on a network-shaped failure only (OSError/RegistryError), so the
  suite passes offline while a genuine error still fails. 0.7.23 exists because that fix
  landed after the v0.7.22 tag; the tag is not moved (PyPI 0.7.22 is immutable).
- **The wheel-size sweep missed the agent-facing surfaces.** The 0.7.22 correction
  reached the READMEs, DEVELOPERS.md and two docs, but `skills/mcptoon/SKILL.md` (the
  copy published to ClawHub and read by other agents) still said 189KB, the live
  `docs/README-details.html` said 206KB / 26 modules / 17,058 lines, the Claude plugin
  command and session script said 189KB, and the two token-waste articles said ~250KB.
  All now state 227KB (28 modules / 18,475 lines where they name those).
  `test_footprint_claims` now covers `docs/README-details.md` and
  `skills/mcptoon/SKILL.md`, and retires every historical spelling
  (128/146/156/179/180/189/190/206/232/233KB) so none can return from an old draft.

## [0.7.22] - 2026-09-24

### Added

- **Four starter skill packs.** `mcptoon install --packs` lists them; `mcptoon install
  --pack essentials` installs one. Each pack is a named bundle of MCP tools plus a
  ready-to-use prompt — `essentials` (files, browser, memory, search), `web-research`,
  `code-review` and `docs`. The packs are **references only**: the wheel ships the pack
  manifest, never the tools, which are installed from npm/pip when you ask. Preview with
  `--dry`. Two research packs need no API key.
- **`mcptoon skills search <query>`** — search the open skills.sh index for a skill by
  what it does, then install the one you pick with `skills add <git-url>`. Falls back to
  the local index when the network is down. mcptoon hosts no marketplace of its own.

### Changed

- **Both READMEs rewritten around two reader paths** — "I just use AI tools" and "I build
  with MCP / agents" — with a plain-language explanation of the token saving up top, a
  CLI-vs-proxy rationale, and the third-party evidence (Anthropic, Firecrawl, Scalekit,
  MCP-Zero) promoted to the top. The five directory badges the rewrite had dropped
  (Manages, AllMCPs, MCPVault, AI Agents Listing, mcpservers.org) are restored.
- **`packs.json` ships in the wheel** via `[tool.setuptools.package-data]`, so the built-in
  packs work from an install and not only from a source checkout.
- **`pyproject.toml` description** now leads with the one-hub positioning.

### Fixed

- **The wheel-size claim was wrong on every surface.** `README` (both languages),
  `DEVELOPERS.md`, `docs/comparison.md` and `docs/tiktoken-benchmarks.md` said the wheel
  was 233KB. It is **227KB** — measured 2026-09-24 against the tree as CI builds it
  (`python -m build --wheel`, confirmed with `uv build --wheel`: 232,828 bytes). The old
  number came from a Windows checkout whose sources were CRLF and whose README was the
  pre-rewrite 581-line version; line endings alone added ~1.4KB of pure overhead inside
  the archive. The `test_footprint_claims` guard now pins 227KB and retires 233KB.
- **Three tests asserted one machine's environment and failed in CI.** The savings-caliber
  test rejected the honest `chars/4` label that appears when tiktoken is absent; the BM25
  legacy-index test read the developer's ambient `~/.mcptoon` index and glossary; the
  DEVNULL-refusal test accepted only the Windows refusal wording. Product behaviour is
  unchanged — the tests now hold on Windows, macOS and Linux, with or without tiktoken.

## [0.7.21] - 2026-09-21

### Fixed

- **mcptoon installed silently and left no trace on the machine.** `pip install`
  has no post-install hook, so the wheel cannot greet anyone, and the only
  self-announcing path was `install.sh` / `install.ps1` handing off to
  `quickstart` — which prints a table and exits. Worse, `sync` and `quickstart`
  only ever wrote *your* servers into each agent's config; mcptoon's own
  `mcptoon serve` gateway was never registered anywhere, so the MCP
  `instructions` field it uses to announce itself to the model fired zero times.
  From a user's seat that reads like a trojan: it installed, and nothing changed.
  Three channels now make its presence visible and verifiable:
  - **Human.** A one-time first-run note (`_maybe_welcome`) prints a short
    "here's what's configured / here's what to run next" block on the first
    interactive command. It stays silent for `--json` / `--toon` / `--slim` (a
    JSON consumer must get clean JSON, and a suppressed welcome does not consume
    the marker), for `serve` / `demo` / `demo-server` / `completion` / help, and
    when `mcptoon config set welcome off` is set.
  - **Agent.** `quickstart` now registers the gateway itself under the reserved
    name `mcptoon`, so agents can see mcptoon and the `initialize` handshake
    delivers its `instructions`. The entry uses `sys.executable -m mcptoon serve`
    rather than a bare `mcptoon`, because an agent may launch with a PATH that
    lacks the user Scripts directory. `quickstart` defaults it on (it is the
    install path, and its whole job is to leave a trace); `mcptoon sync` defaults
    it **off** and opts in with `--self`, because `sync` is routine and silently
    injecting a new server entry on every routine run would be a surprise.
    `mcptoon quickstart --no-self` skips it; a user server already named
    `mcptoon` is never clobbered. Any write that actually changes an agent
    config first drops a `<config>.bak` (only once, and only when the content
    differs), so the pre-mcptoon state is one copy away.
  - **Effect.** `mcptoon status` prints one screen: servers configured, tools
    indexed, the schema compression with its caliber label, calls recorded, and
    whether the gateway is wired into any agent config (`--json` for scripts).
    And `track_call` finally carries a real token count: every call site passed
    no tokens before, so `mcptoon usage` said `Tokens (est): 0` on every machine
    — a tool that sells token savings could never show one. The count now comes
    from `usage.count_tokens`, which delegates to `bench._tokenizer`, so the
    footer, `usage`, `stats` and `bench` quote one caliber, never two.
  29 tests (`tests/test_presence.py`), all local and offline.

### Added

- **The savings line now arrives on its own, on every surface mcptoon controls.**
  The per-turn footer was wired as a *request*: the agent-side directive asked the
  model to run `mcptoon footer-facts` and paste the result. That is a soft channel
  — it works only if an agent reads the directive, remembers it and complies — and
  on a harness that speaks no MCP (DSH, which is why this round exists) nothing
  appeared at all, so the tool whose entire job is compressing the context was
  itself invisible. The line is now *stamped* rather than requested, on the two
  payloads mcptoon already owns, behind one shared implementation:
  - **Every CLI command.** `cli.main()` prints the block to **stderr** once the
    command finishes, so any agent that can run a shell sees it — Codex, DSH,
    Gemini CLI, Aider, anything with a terminal — with no per-agent
    configuration. stderr rather than stdout on purpose: stdout is
    machine-readable for `--json` and `--toon`, and a courtesy line that breaks
    `mcptoon status --json | jq` would be a worse bug than the invisibility it
    fixes. Silent for the stdio servers (`serve`, `demo-server`), where one stray
    write can desynchronise the JSON-RPC stream; silent for `--version` and for
    `footer-facts`, which has already printed the same block on stdout; printed
    only on success, because after a failed command the terminal is already
    carrying a diagnostic. The wrapper catches `SystemExit` because 41 places in
    `cli.py` leave through `sys.exit()` — `mcptoon manifest` among them — and a
    raised `SystemExit` skips everything written after the dispatch.
  - **The first tool result of an MCP session.** `MCPServerBridge._stamp_footer`
    appends the block to the first successful result routed through
    `_make_tool_result`, the single funnel every proxied call passes through. That
    rides the protocol payload rather than a prompt, so it reaches Claude Desktop,
    Cursor, Cline, Windsurf, VS Code Copilot and any other MCP client without
    needing the model's cooperation. **Once per session, not once per call**: the
    block measures 32 tokens on the tiktoken cl100k_base caliber while a full
    catalog compression saves ~5,200, so stamping every result would break even at
    ~162 calls — and a feature that can eat the savings it advertises is not a
    feature. Error payloads are skipped, and an unanticipated upstream shape is
    passed through untouched rather than raising.
  - The new `footer` module is the single source of truth for all of it
    (`facts()` / `line()` / `note()` / `block()` / `enabled()`), and
    `cli._cmd_footer_facts` now delegates to it, so the CLI tail, the MCP stamp,
    `footer-facts` and the model's own line cannot quote different numbers.
    `config.footer_enabled()` still governs every surface at once. Measured cost of
    the CLI half: 171 ms of tiktoken work per command on this 12-server, 95-tool
    machine — accepted rather than memoised, because a cache-stamp key would still
    have had to keep the *age* half live, and 171 ms next to a 15-60 s `status` is
    not the failure mode this feature exists to avoid.
  - 15 new tests in `tests/test_reversible.py` pin the behaviour: the tail lands on
    stderr and not stdout, `--json` stays parseable, `--version` stays byte-clean,
    the stdio servers never stamp, `footer off` silences all of it, a broken footer
    cannot fail the command carrying it, the MCP stamp lands exactly once, and all
    four surfaces quote one identical line. Two of them exist because the first
    draft was wrong: the tail initially sat at the end of `main()`, where
    `sys.exit()` meant it never ran at all — `mcptoon manifest` printed nothing
    extra, which is exactly the bug being fixed.
  - **The line opens with a 🎉 mark.** A savings figure the user never notices is
    the same failure as no figure at all, and a single emoji is the cheapest way to
    make a line of numbers catch the eye. Kept as `footer.MARK` so it can be changed
    or dropped in one place; the text after it stays byte-identical to
    `footer-facts`, and the mark is confined to the human-facing line — `--json`
    bodies and `--version` stay undecorated.
- **`mcptoon footer-facts`** — one line of real savings numbers for a chat footer,
  read from the cached catalog without contacting any server. This exists because
  the agent-side directive asks the model to close a turn with a savings line, and
  the obvious implementation (`mcptoon status`) is unusable in a chat loop: `status`
  refreshes a stale schema cache by spawning every configured MCP server — measured
  at **23s cold against 1.9s warm** on a 12-server machine. A footer that
  occasionally costs 23 seconds is worse than no footer, so `footer-facts` serves
  whatever the cache holds, says how old it is, and stays under half a second even
  with an expired TTL (verified: 0.46s at `MCPTOON_CACHE_TTL=1`, where `status`
  took 15.6s). Its numbers come from the same tokenizer and the same per-tool sums
  as `status` and `stats`, so all three agree.
- **`mcptoon config set lang auto|zh|en`** — the savings line and its caveat now
  have a stated language instead of an implicit one. The question that exposed the
  gap was a plain one: *how does it decide Chinese or English?* It had no answer,
  because the machine's own signals disagree — measured on the author's box, the
  Windows UI language is Chinese (LANGID `0x804`) while the shell exports
  `LANG=en_US.UTF-8`, so "detect it" was a coin flip that could land differently in
  a terminal than under a scheduled task. `config.resolve_lang()` now owns one
  documented order, highest first: the explicit setting > `MCPTOON_LANG` (the same
  escape hatch as `MCPTOON_CACHE_DIR`) > the OS UI language — read from
  `GetUserDefaultUILanguage` on Windows, precisely because `locale.getlocale()` is
  the thing `LANG` overrides > `LC_ALL`/`LC_MESSAGES`/`LANG` > English. An
  unrecognised value falls through to the machine's answer rather than raising: a
  settings typo must not break a command whose whole job is to print a line.
  - Every surface follows the one setting, because they all render through
    `footer.line()` / `note()` / `block()`: the CLI tail, `mcptoon footer-facts`,
    and the first MCP tool result of a session.
  - **The machine-readable handles stay ASCII in both languages** — the `mcptoon:`
    prefix, the word `tokens`, the `[caliber]` suffix and the `note: ` label. A
    handle that changes with the language hands a parsing problem to consumers who
    never asked for one, and `--json` keeps its English note outright: a JSON body
    is data, not a message to a person.
  - The caveat is re-rendered from the figures already in hand (the raw inputs now
    travel with them), so translating the note never re-reads a cache — let alone
    contacts a server — to say the same sentence in another language.
  - 24 tests in `tests/test_lang.py` pin the order itself (including the measured
    `LANG`-versus-OS conflict), both renderings, and that neither language loses the
    handles other suites key on.

### Fixed

- **`MCPTOON_CACHE_DIR` was documented and silently ignored.** `cache.py` built its
  path from `config.CACHE_DIR`, frozen at import, so the setting moved
  `config._cache_dir()` and nothing else — a caller who relocated the cache still
  wrote to the real `~/.cache/mcptoon`. This is the third instance of the same
  class in this project (the destructive commands had it, and it cost a real
  `config.json` once); the path is resolved per call now, and `tests/test_cache.py`
  isolates through the env var instead of patching the constants that hid the bug.
- **The agent directive pointed at a command the model could not run.** It said
  "read mcptoon_usage for the exact figures" — not a command, so the natural
  substitute was `mcptoon status`, with the 23-second refresh above. It now names
  `mcptoon footer-facts`, says why not `status`, and still states the off switch in
  the same breath.
- **A stale figure could be reported as fresh.** `footer-facts` emits a `note` when
  the catalog is incomplete or old, and the first version tested those two conditions
  as `elif` branches — so on a machine with one server that never resolves, the note
  named the missing server and silently swallowed the staleness. Caught on the author's
  machine where the cache was 128 minutes old against a 5-minute TTL and the note read
  as though only the tool count were partial. The line is quoted verbatim into a chat
  turn, so a stale number presented as current is the one failure that matters; both
  caveats now print together.
- **The directive and the line had drifted, so the mark vanished in the wild.** The
  savings feature exists to be *noticed*, and `footer.MARK` was measured, pinned and
  printed — but `serve._INSTRUCTIONS` only asked the model to "quote it verbatim"
  without ever naming what "it" contains, and the DSH-side instruction block showed
  an example line with no mark in it. Measured consequence (2026-09-22): on a machine
  whose footer really printed `🎉 mcptoon: 95 个工具…`, two consecutive turns reported
  the line **without the 🎉** — the one element the feature exists to make noticeable,
  and the first thing a paraphrase drops. The directive now names the payload
  (`🎉 mcptoon:` on the first line plus the `note:` line when present, in whichever
  language it printed), forbids retyping from memory and translating it, and
  `test_instructions_pin_the_mark_and_the_note_line` fails the build if the directive
  ever stops naming `footer.MARK`. The lesson generalises: an instruction that says
  "quote X verbatim" without describing X is a licence to paraphrase it.

- **The exit door: `mcptoon off` and `mcptoon uninstall`.** Presence alone is not
  what makes a silent installer feel like a trojan — a tool you cannot get rid of
  is. The three channels above make mcptoon visible; these make it removable, which
  is the half that was still missing.
  - `mcptoon off` removes **only** the reserved `mcptoon` gateway entry from every
    agent config and nothing else: your own server definitions, comments and
    ordering in those files are untouched, and every file it changes keeps the
    `<config>.bak` that `sync` writes. `mcptoon sync --self` puts it back. `--dry`
    prints what would change without writing.
  - `mcptoon uninstall` prints its complete plan *before* it removes anything, then
    takes the gateway entries back and deletes mcptoon's own bookkeeping (settings,
    the first-run marker, toggles, compression policy) and its cache directory. It
    deliberately **keeps** `~/.mcptoon/config.json` and `config.toml`, because those
    hold the servers *you* configured — silently deleting a user's server list while
    claiming to clean up would be the worst possible version of the surprise this
    release exists to remove. `--no-keep-config` is the explicit opt-in to delete
    them too. `--dry` shows the same plan and stops. Without `--yes`, a
    non-interactive stdin makes it refuse rather than delete silently.
  - The two commands share `sync.remove_gateway_from_agent` / `remove_gateway_from_all`,
    which de-duplicate by the **resolved** file rather than by the reported path
    string: `detect_installed_agents` lists Cursor twice (global + project) and those
    can be the same file, so the old string comparison processed it twice and
    reported "removed from 6 agents" when five files had changed — its own small lie.
    Keying on the resolved path also let `remove_gateway_from_agent` take a `path`
    override, which fixes a real gap: `_agent_config_path("cursor")` only ever names
    the *global* file, so a project-level `.cursor/mcp.json` silently kept the gateway
    entry that `off` had just reported as removed. On this machine the reported count
    went from a wrong 6 to a correct 5, and both behaviours are pinned by tests that
    fail when the override is dropped (mutation-checked).
  - Uninstall resolves its paths through the new `config.state_paths()`, so the
    `MCPTOON_*_FILE` overrides it advertises are honoured by the command that deletes
    things — the one place getting it wrong is unrecoverable. It also split the
    paths into bookkeeping / servers / cache, which is what makes the
    keep-your-servers default expressible instead of implicit.
  - `_safe_rmtree` refuses to recursively delete any directory not named `mcptoon`
    (the only name this project creates) and reports the skip. A destructive command
    should not be one bad constant away from deleting a user's home: if
    `MCPTOON_CACHE_DIR` ever resolved to a parent, an unguarded `rmtree` would take
    everything with it.
- **A first draft of `uninstall` deleted a real `~/.mcptoon`, and the tests did it.**
  Recording this because it is the strongest argument for the rules above. The
  initial `_cmd_uninstall` read its paths from config.py's import-time constants
  (`cfg.CONFIG_DIR` / `cfg.CONFIG_FILE` / `cfg.SETTINGS_FILE`). Those are computed
  once at import, so they ignore the `MCPTOON_*_FILE` env overrides — and the unit
  test that exercises the destructive branch redirects *env vars*, not module
  attributes. The two never met: running `pytest tests/test_reversible.py` deleted
  the developer's real `config.json` (12 MCP server definitions) and `settings.json`.
  Recovery was possible only because `sync` leaves dated backups: the newest
  (`config.json.pre-auto-20260919-175947`) was verified field-by-field against the
  live agent configs — 11 servers, zero mismatches in command/args/env/url — and the
  single server it predated was recovered from Cursor's own config, restoring all 12
  servers and 95 tools. Two independent guards now stand between a test and that
  outcome, and both were mutation-tested (a dead `cfg.CONFIG_FILE` reference was
  added to `_cmd_off`, the guard was confirmed to fail, then the mutation was removed):
  - `_IsolatedHome.setUp` asserts every path `config.state_paths()` returns resolves
    inside the temp directory, and redirects the whole set by `MCPTOON_*` env
    (including the previously non-overridable `MCPTOON_COMPRESSION_FILE`) rather than
    by patching module attributes.
  - `TestDestructiveCommandsReadPathsLate` inspects the source of `_cmd_uninstall`,
    `_cmd_off` and `_cmd_status` and fails if any of them names one of config.py's
    import-time path constants. Reading the source catches a reintroduction even when
    the running environment happens to make the paths look correct.
- **A real front door for the CLI.** `mcptoon --help` now opens with a wordmark and
  a four-command "Start here" block (`quickstart`, `status`, `off`, `uninstall`)
  before the full command list, so the first thing a new user reads includes how to
  see what it did and how to undo it. `mcptoon status` gained the same closing
  section, and `mcptoon sync --self` now prints the undo command on success.
- **`sync` no longer reports agents it did not write.** The same phantom as the
  removal fix above, on the other side of the command: `sync_to_all` iterated agent
  *rows* and called `sync_to_agent(agent["id"])`, but an id maps to one file — for
  Cursor, the global one. So the project-level row produced a second "✓ 13 servers"
  line for a file already written once, and a full run reported "6 agents updated,
  78 servers" where five files and 65 servers is the truth. It now de-duplicates on
  the file it will actually write, which also keeps sync off a project-level
  `.cursor/mcp.json` it would otherwise have to create — writing into whatever
  directory the user is standing in is exactly the kind of unasked-for side effect
  this release exists to remove.
- **`off` and `uninstall` no longer greet you on the way out.** Both joined
  `_WELCOME_EXEMPT`: a first-run note saying "here's what I configured for you",
  printed immediately above an uninstall, is its own small joke.
- **End-to-end tests for the destructive commands, in a home that is not yours.**
  `tests/test_uninstall_end_to_end.py` (10 tests) runs `python -m mcptoon uninstall
  --yes` and `mcptoon off` as real subprocesses against a fabricated home —
  `USERPROFILE` and `APPDATA` relocate the agent paths, `MCPTOON_*` relocate
  mcptoon's own — then asserts the user's server definitions survived on both sides,
  that `--no-keep-config` really deletes them, that a refusal removes nothing, that a
  second uninstall does not crash, that `off → sync --self` is a round trip, and that
  `off` leaves a `<config>.bak` still holding the pre-change state. A shared guard
  re-reads the developer's real `~/.mcptoon/config.json`, `settings.json` and Cursor
  config afterwards and fails if they changed at all — the check whose absence let
  the original incident through.
- **The non-interactive guard is a courtesy, not the safety property.** Pinned
  because finding it out was the hard way: on Windows the NUL device is a character
  device, so `isatty()` returns True for `stdin=DEVNULL` and the
  `not sys.stdin.isatty()` check does not fire. The prompt then runs, `input()` raises
  `EOFError`, the answer becomes empty — which is not "yes" — and it refuses there
  instead. Both routes refuse and neither deletes, and both are now tested separately
  so that "is it safe to run uninstall in a script" never rests on `isatty()`.
- 58 tests (`tests/test_reversible.py`): the surgical undo keeps user servers,
  leaves a `.bak`, writes nothing on `--dry`, tolerates the VS Code `mcp.servers`
  shape, collapses rows that name the same file (in both directions), uninstall
  survives `--dry`, `--yes` and a non-interactive refusal, the sandbox asserts it
  cannot reach outside itself, and the destructive functions are pinned to call-time
  path resolution. It also pins the per-turn footer's two obligations — its numbers
  agree with `status`/`stats`, and it cannot be made to wait on a server — plus the
  cache-dir env var that `MCPTOON_CACHE_DIR` only pretended to honour. 5 more in
  `tests/test_native_tools.py` pin the agent-side
  directive below; 10 more at the process level in
  `tests/test_uninstall_end_to_end.py`.

### Fixed

- **Three commands existed that no user could find.** `mcptoon config`,
  `mcptoon stats` and `mcptoon toggle` were fully implemented, reachable, and
  absent from `--help` and from both READMEs (grep: zero mentions in either).
  `config` is the worst of the three to have lost — it is how a user silences the
  per-turn savings line, so the release that promised "you can switch this off"
  shipped with the switch unfindable. All three are now in `--help`, in both
  READMEs, and on the AI-facing surface (`docs/llms.txt`), which also did not
  mention them. Every existing guard started from `_print_help()` and looked
  outward, quietly assuming the help was complete; the missing direction —
  dispatcher → help — is now covered by
  `tests/test_command_coverage.py::test_every_dispatched_command_is_either_advertised_or_a_declared_alias`,
  with an explicit alias table so it cannot be satisfied by hiding a command.
- **`stats` and `status` disagreed about how much mcptoon saves.** `mcptoon stats`
  — literally titled the token savings dashboard — measured with
  `len(json) // 4  # rough token estimate` while `mcptoon status` used
  `tiktoken cl100k_base`. On the real machine that read 20,306 / 15,292 against
  20,914 / 15,719 for the same catalog. `stats` now shares the one tokenizer, prints
  the caliber, and carries `token_caliber` in its JSON. Nobody had noticed for as
  long as it was true, because `stats` was not in `--help`: the only way to find the
  discrepancy was to already know both commands existed, which is the same
  discoverability failure wearing a different hat.
- **`mcptoon --help` listed `off` twice** and `uninstall` twice (bare, and again as
  `--dry`), and its description column had drifted into two alignment groups —
  everything down to `install` padded to column 42, the rest to 41 — visible as a
  ragged edge in the one block whose whole job is to look like a front door.
  `uninstall` now appears once, in the `Start here` block where a newcomer needs it,
  and the padding is uniform and guarded by a test.
- **cli.py carried a second, drifted copy of the help text as its module
  docstring.** 68 lines, printed by nothing, and already wrong: it still advertised
  `mcptoon uninstall` in its Usage block, listed `policy` twice, and had never heard
  of `config`, `stats` or `toggle`. Replaced with a pointer to `_print_help()`, the
  single source of truth. Two copies of a front door is one copy too many, and the
  stale one is the one people read.

### Changed

- **`status` and `bench` now quote one tokenizer, not two.** `status` measured
  savings with `len(json) // 4` while `bench` used `tiktoken cl100k_base`, so the two
  commands a user runs back-to-back disagreed about the same catalog — `status` said
  `-25%` where `bench` said `-88.3%`. Two calibers for "how much did you save" is how
  a tool loses the argument that its numbers are real, and the smaller number is the
  one that looks like the honest one. `status` now calls `bench._tokenizer`
  directly, labels the figure with the caliber it used (`chars/4` only as a stated
  fallback when tiktoken is absent), and its `--json` gained `tokens_full`,
  `tokens_slim` and `token_caliber` so both sides of the saving are auditable.
- **The agent-side savings line is now expected rather than permitted.** The
  `initialize` `instructions` field asked the model to *maybe* close with one line,
  which in practice meant turns silently dropped it — the same invisibility this
  release is fixing, one layer down. It now says to end every tool-using turn with
  the figure, to take the number from `mcptoon_usage` and never invent it, to load
  the `mcptoon` skill for the per-server breakdown (so "saved compared to what?" has
  a reachable answer), and how to switch the line off
  (`mcptoon config set footer off`) in the same breath as asking for it. A line the
  user cannot silence is the reason it would read as spam.
- **README's first-push path is now `quickstart`, not `bench`.** The 30-second
  "your own numbers" pitch still points at `bench`, but a fresh reader is sent to
  the command that actually configures the machine and announces itself. Both
  READMEs also now state the undo path next to the gateway paragraph.
- Both READMEs, `DEVELOPERS.md`, `ROADMAP.md`, the landing pages and the benchmark
  post carry re-measured footprint numbers (206KB wheel, 16,839 lines, 1194 tests).
  The wheel byte growth was attributed to this session's source changes by comparing
  the deflate delta of `src/mcptoon/*.py`, so the number is not a toolchain artifact.

## [0.7.20] - 2026-09-20

### Fixed

- **HTTP transport announced `Python-urllib/3.x`, and bot filters 403'd it.**
  `urllib` sets `Python-urllib/3.x` when no `User-Agent` is given. Public hosted
  MCP endpoints sit behind bot filters (Cloudflare error 1010 and friends) that
  reject that signature outright — so `mcptoon add <name> --http <url>` configured
  fine, but every later `manifest` / `call` died with `HTTP_ERROR 403` that read
  like a transport bug. The transport now announces `mcptoon/<version>` by
  default, in both `_http_request` and `_http_notify`. A caller-supplied
  `User-Agent` (via `headers=` / `--header`) still wins, and `extra_headers` are
  untouched, so nothing changes for anyone already setting their own UA. 9 tests
  (`tests/test_http_user_agent.py`), mocked opener, no network. Contributed by
  [@mouse-value-add](https://github.com/mouse-value-add) in
  [#20](https://github.com/activeing123/mcptoon/pull/20).

### Changed

- **The package description now names both halves of the toolbox.** It said
  "MCP client … Sync MCP servers across agents"; it now says "MCP tools + agent
  skills … Sync both across agents". The skills half shipped in 0.7.19's README
  and `mcptoon skills`, but the one-line metadata on PyPI, in `server.json` and
  in `gemini-extension.json` still described tools only. No behavior change.
- **`server.json` now points at the measured claim** — "MCP tools + agent skills
  in one zero-dependency CLI: 71,929 -> 581 tokens (-99.2%, measured)" — instead
  of the older "581-token listings, not 71,929" phrasing.

Suite total 1069 passed + 1 skipped; wheel 190KB; zero dependencies.

## [0.7.19] - 2026-09-18

### Changed

- **README opening rewritten for a first-time reader.** The lede now says what
  mcptoon is in plain words — a 189KB CLI that takes over every MCP tool and
  skill on the machine and keeps both out of the context window — instead of
  naming the category. The call to action leads with the command that proves the
  claim on the reader's own machine (`pip install mcptoon && mcptoon bench`, ~30s).
- **Two duplicated intro paragraphs dropped.** The paragraphs under the opening
  code block repeated what the "why" and "how" sections already say (tools are
  not pre-installed, removal is a no-op, the decoupling layer). The sections keep
  the detail; the duplication is gone.
- **The opening code block shows two commands, not four.** `mcptoon add …` and
  `mcptoon manifest` left the hero block because the 30-second quickstart just
  below already teaches both.
- **The three external benchmarks now link to their sources.** The Anthropic,
  Firecrawl and Scalekit figures under "This is not just us talking" each link
  to the original write-up.

No behavior change — docs only. The wheel size and the suite total are unchanged
(189KB, 1059 passed + 1 skipped).

## [0.7.18] - 2026-09-18

### Fixed

- **`mcptoon quickstart` proposed five dead npm packages.** The zero-config list
  sent `npx` after names that no longer exist on the npm registry —
  `@modelcontextprotocol/server-fetch`, `-time`, `-git`, `-docker` and
  `-sqlite` — so on a clean machine the very first `quickstart` came back with
  `npm error 404` / `PROCESS_DIED` for five of the eight servers it had just
  recommended. The official reference servers are split by ecosystem:
  `filesystem`, `memory` and `sequential-thinking` are npm packages, while
  `fetch`, `time`, `git` and `sqlite` are Python packages on PyPI. The npm list
  now contains only packages verified to exist there, the Python servers are
  offered through `uvx` and only when `uvx` is installed, the unmaintained
  `docker` guess is gone, and `mcptoon init`'s sample config no longer ships the
  dead `fetch` entry. This was the same bug class as the 2026-09-05 `demo.py`
  fix; that fix deliberately left the discovery candidates alone, which is why
  `quickstart` kept advertising them.
- **A server that logged more than one pipe buffer deadlocked the `spec="auto"`
  probe (#19).** `_spawn_stdio()` opened the child with
  `stderr=subprocess.PIPE`, and nothing read that pipe while the server was
  alive: a server logging more than a few KB blocked inside `write()`, stopped
  reading stdin and stopped answering stdout, and every request then timed out
  as `RESPONSE_TIMEOUT ... server went silent`. One `server/discover` probe was
  enough to trigger it — the Python reference servers answer that unknown method
  with ~6.8 KB of pydantic validation warnings (measured: 6,793 bytes from
  `uvx mcp-server-time`) — which made `uvx mcp-server-fetch|time|git` look dead
  on a fresh machine while `spec="legacy"` worked, because legacy never probes.
  stderr is now drained continuously on a background thread, in 8 KB chunks via
  `read1` (so a single huge line with no newline is drained too, which line
  iteration would not), and the bounded drained ring feeds `_stderr_tail()`.
  The post-mortem pipe read it replaces was both the reader that was missing and
  a race against process exit.

The release also re-pins the footprint claims, because the fixes moved them: the
wheel is **189KB** (194,028 bytes) and `src/mcptoon/*.py` is **15,697** physical
lines, and the suite total moves to **1,061 tests** (1,060 passed, 1 skipped).
Both README badges, the landing pages, `DEVELOPERS.md`, `ROADMAP.md`,
`docs/comparison.md`, `docs/tiktoken-benchmarks.md` and the shipped skill cards
were updated together — the footprint guard reads all of them, so a partial
update is a red CI.

## [0.7.17] - 2026-09-18

### Added

- **`mcptoon bench` — prove the savings on your own machine, in one command.**
  The README's token claims had a proof, but it needed a clone: the scripts live
  in `scripts/`, which the wheel does not ship. `bench` is inside the wheel, so
  `pip install mcptoon && mcptoon bench` measures both halves at once — tool
  schemas against the name index, and every `SKILL.md` against the resident
  pointer and one lookup. tiktoken is used when present (exact numbers, the ones
  the README quotes); without it the table says "estimate" rather than passing a
  guess off as a measurement. It is read-only: it reads the schema cache and the
  skill index and never writes the usage ledger.
  - The skill half counts one level deep, excludes `_index`, and **de-duplicates
    roots by real path**. On a machine whose agent folders are junctions onto one
    catalog — the common multi-agent layout, and this one — a naive walk counted
    the same catalog four times (3,710,031 tokens instead of 931,339). The skipped
    duplicate count is printed, not hidden.
  - `mcptoon bench --json` emits the same numbers for scripts; `--roots` points
    it at any catalog.

### Changed

- **Both READMEs were rewritten around the two halves of one toolbox.** The old
  text led with MCP and treated skills as an add-on bolted on later. The
  subtitle, the definition, `How it works` and `Works with every AI agent` now
  describe one gateway managing both, in the same words, and a new Technical
  specification section pairs the two sides feature by feature.
  - The self-proof block no longer tells a reader to `git clone`; it runs
    `mcptoon bench`.
  - Three evidence links (Anthropic's engineering blog, Firecrawl, Scalekit)
    became plain-text citations: the evidence stays, the outbound clicks do not.
    No competitor product page is linked anywhere in the README.

### Fixed

- **The wheel-size claim said 180KB; the wheel is 188KB.** This release adds
  `src/mcptoon/bench.py` (~13KB) on top of `skills.py`, and the README — which is
  embedded in the wheel METADATA — grew by ~10KB when it began documenting the
  skills family. `python -m build` now yields 192,988 bytes (188.46 KB),
  identical across builds. All eighteen surfaces that stated the old figure are
  corrected, including the two shipped `SKILL.md` cards and the Claude plugin.
- **The suite total was stale on eight surfaces** after `bench` brought tests of
  its own: `README.md`, `README.zh-CN.md`, `DEVELOPERS.md`, `ROADMAP.md`, both
  landing pages and `docs/tiktoken-benchmarks.md` now read 1049 passed, 1 skipped
  (the passed count, matching the badge convention), and the module/line counts
  moved to 25 / 15,656.


- **Skills became a managed catalog, not just a search index.** v0.7.16 taught
  `mcptoon skills` to index and route a skill catalog. This release adds the
  other half — distribution and lifecycle — so the same one-source-of-truth
  model that already governs MCP servers now governs skills too:
  - `mcptoon skills sync [SRC] [VIEW ...]` distributes a source catalog into
    every agent's skill folder. Views are **links** (a junction on Windows, no
    admin needed), so one edit at the source is instantly visible everywhere and
    there is no second copy to drift. `--copy` forces real directories, `--dry`
    prints the plan without writing. A real directory where a link belongs is
    **archived, never deleted**; removal happens at the source and the views
    follow; a link owned by another manager is reported and left untouched.
  - `mcptoon skills add <name> [--desc D]` and `mcptoon skills remove <name>`
    manage the source. Removal **moves** the skill into a dated archive beside
    the source — a wrong removal is a `mv` back, not a re-clone.
  - `mcptoon skills list [--usage] [--all]` lists the catalog; `--usage` adds
    per-skill hit counts. Counts cover skills mcptoon routed (via
    `resolve`/`route`); a skill an agent loaded directly is invisible, and the
    output says so rather than implying full coverage.

- **The gateway now has a voice.** `serve` returns an `instructions` field from
  the MCP initialize handshake — the protocol's official channel for a server to
  brief the model — so every client that honours it learns what mcptoon is
  without anyone editing a system prompt. The one-line end-of-turn disclosure it
  steers ("mcptoon saved ~N tokens this session") is backed by a new first-party
  tool, `mcptoon_usage`, which returns the real figures, so the model never has
  to estimate them. Turn it off with `mcptoon config set footer off`; the setting
  persists and suppresses the field entirely on the next connection.

- **`mcptoon config [get|set]`** reads and writes gateway settings
  (`~/.mcptoon/settings.json`, separate from server config so a settings write
  can never corrupt a server definition). Unknown keys fail loudly.

- **The catalog manager reached parity with the script it replaces.** Taking over
  from a long-running sync script means matching it byte for byte, not just
  approximately — a derived view that differs by a line ending is a diff the next
  sync has to fight. Four capabilities close the gap, each one learned from a real
  failure in that lineage:
  - `mcptoon skills sync --version-gate` blocks a skill whose content changed but
    whose frontmatter `version` did not, and prints why. It reads the **same**
    ledger file the other manager wrote (`skill_versions.json`, overridable with
    `MCPTOON_SKILLS_LEDGER`), so during a hand-over both reach the same verdict on
    the same bytes. `--force` is the escape hatch (lets the change through and
    rebaselines); a skill with no `version` is warned about rather than blocked;
    the ledger's own files are excluded from the hash so the tool that owns the
    ledger cannot gate itself forever.
  - `mcptoon skills sync --derived roo|opencode|all` regenerates the flat
    `<slug>.md` views (plus each skill's `.py` attachments as `<slug>_<file>.py`)
    that Roo and OpenCode read. Output is byte-identical to the incumbent's — 422
    files per view verified against the live folders — including the platform line
    endings a text-mode write produces. Stale entries are moved to the graveyard,
    never deleted.
  - `mcptoon skills remove --tombstone` commits the removal so a two-way git sync
    cannot resurrect a deleted skill. The commit is **path-scoped**; a whole-repo
    `git add -A` is refused on purpose, because the repo holding a real skill
    source routinely has hundreds of unrelated edits in flight and sweeping them
    into a "tombstone" is how one manager silently commits another session's work.
  - `--archive DIR` points drift and removals at a shared graveyard, so a
    rollback is the same `mv` whichever manager performed the removal.

### Fixed

- **`mcptoon skills` was invisible in `mcptoon help`.** The command family worked
  and was tested, but the top-level usage block never listed it — so the headline
  feature of this release could not be discovered from the CLI at all. The block
  now carries the four common forms (`list`, `resolve`, `sync`, `add|remove`), and
  `tests/test_command_coverage.py` fails the build if a command the help advertises
  is missing from either README.

- **Both READMEs never documented the skills catalog.** The `skills` family was
  absent from the "All commands" block and had no section of its own, even though
  it is what this release is about. `discover`, `init`, `health` and `policy` were
  missing from the list too. All are now documented, and the new coverage guard
  keeps the README and the CLI in step.

- **The wheel size claim said 156KB; the wheel is 179KB.** This release adds
  `src/mcptoon/skills.py`, a new ~68KB module, which grew the wheel from 155.5 KB
  to 179.4 KB (measured with `python -m build`, identical across builds). Thirty-odd
  surfaces still advertised the old figure — README (both languages), the landing
  pages, `docs/comparison.md`, `docs/tiktoken-benchmarks.md`, the shipped skill card
  and the Claude plugin scripts. All are corrected, and the footprint guard's
  `WHEEL_KB` constant with them, so the guard stops pinning a stale number.

- **The landing pages advertised v0.7.16 to crawlers.** Both `docs/index.html` and
  `docs/index-zh.html` still carried `"softwareVersion": "0.7.16"` in their JSON-LD
  block while the visible copy said 0.7.17.

- **`_index` is no longer published as a skill.** The vault keeps its index card
  at `skills/_index/SKILL.md`; it carries a SKILL.md but is not a skill. mcptoon
  walked into it and would have written a phantom `_index.md` into every derived
  view — caught by the byte-parity check against the live `~/.roo/commands`, which
  had 371 files to mcptoon's 372. The name is now skipped everywhere a tree is
  walked, matching the incumbent's behaviour in all 13 of its walkers.

- **The footprint guard could not see a comma-glued test total.** Its regex
  required whitespace before the separator, so a line reading `956 passed, 1
  skipped` never matched and a stale suite total hid in the README for two days.
  The pattern now tolerates optional whitespace on both sides, and a regression
  test pins every separator spelling.

## [0.7.16] - 2026-09-17

### Fixed

- **A dead server now reports why it died.** When a configured server's command
  fails at startup — the common case being `npx` on a package that no longer
  exists on npm (E404) — the write to its dead stdin raised `[Errno 22]` on
  Windows, and the real cause was sliced away by three stacked truncations: the
  stderr reader kept the *first* 500 bytes, the error cell capped at 100 chars,
  and the manifest printer at 60. A failing `npx` prints a wall of Node
  `NODE_TLS_REJECT_UNAUTHORIZED` warnings first and its `npm error 404` last, so
  users saw the warning and never the diagnostic. `client._salient_stderr()`
  now drops that boilerplate and keeps the end of stderr (where process errors
  are printed), and the caps are widened to 300/200. Found 2026-09-17 during the
  Windows first-install field test, where 3 of 13 configured servers died this
  way. Pinned by `tests/test_dead_server_diagnostics.py`.

## [0.7.15] - 2026-09-17

### Added

- **`docs/llms.txt` is published on the Pages site.** Agents that look for the
  llms.txt convention can now discover the project, the measured numbers and the
  canonical entry points without scraping the landing page.
- **`server.json` now carries `title` and `websiteUrl`.** The MCP Registry record had
  only the five required-ish keys; the schema also defines `title` (display name) and
  `websiteUrl` (homepage), and the landing page now exists to point at. Note for the
  next teardown: the schema has **no `license` field** — an earlier note that said to
  add one was reading a different registry's schema. Both new fields are pinned by
  `tests/test_registry_sync.py` so a later edit cannot quietly drop them.
- **Both READMEs carry the mcpservers.org badge.** The directory approved the listing
  on 2026-09-15 and asks listed projects to show the badge; it was deliberately held
  back until a release so the README was not touched outside one.

### Changed

- **Both READMEs lead with the two things a reader is deciding on.** The hero now
  states the two pain points — tool schemas eating the context window, and the same
  MCP servers being configured once per agent — before the badges, and the install
  line sits directly under them. Everything below is unchanged in substance.
- **The demo no longer contradicts itself.** One screen used to promise "Install
  1,000 MCP tools, 0 token schemas" while the table below it measured 255 tools at
  581 tokens. The banner now carries the measured pair, each tier keeps its own
  number, and a guard fails if the retired claim comes back.

### Fixed

- **The suite total was stale on six surfaces.** `README.md`, `README.zh-CN.md`,
  `DEVELOPERS.md`, `ROADMAP.md` and both landing pages advertised `925 passed` while
  the suite had moved on — the guard added in the previous change brought tests of its
  own. All six now read the current total; the two landing pages were regenerated
  through the documented pipeline rather than hand-edited.
- **The suite-total guards now allow only what a skip can explain (one),** down from a
  gap of five. The wide gap was what let the stale total above pass unnoticed, and the
  tighter bound caught a second drift while this change was being written. Both the
  README badge guard and the all-surfaces guard were tightened. The number they judge
  is the collection count, so it does not vary with which tests a given OS skips.
- **A version guard no longer breaks Python 3.10.** The check added on 2026-09-17 read
  `pyproject.toml` with `tomllib`, which only exists on 3.11+, so CI went red on the
  two 3.10 jobs the moment it landed. It now parses the version with a regex, the way
  `test_registry_sync.py` already did for exactly this reason.

## [0.7.14] - 2026-09-14

### Added

- **`serve` now publishes three tools of its own.** `mcptoon_manifest`, `mcptoon_servers`
  and `mcptoon_health` answer from state the bridge already holds: no upstream servers, no
  API keys, no subprocesses, all three declared `readOnlyHint`. Until now `tools/list`
  carried only what configured servers exposed, so a gateway started with an empty config
  - every first run, and every registry that introspects us - looked like a tool-less
  server. An upstream tool that claims one of these names still wins.
- **The demo server's eleven tools declare what they return.** Each carries an
  `outputSchema` whose fields are documented one sentence at a time, and answers
  `tools/call` with `structuredContent` beside the text block, as MCP pairs them. The
  notes are short so that they pass the gateway's budget whole and reach a client
  unchanged. Tests assert the schema against the handlers, so a field that stops being
  returned fails the suite rather than shipping as a lie.

### Changed
- **`tools/list` descriptions are no longer cut to their first sentence.** The old rule
  kept one sentence and hard-cut at 120 characters, which deleted the guidance an agent
  selects tools with — "when to use it", "call the other tool instead", "this will not
  tell you X" are never the first sentence — and could stop mid-word, leaving a fragment
  that was no longer a claim. The budget is now two tiers: 360 characters / up to 3
  sentences for a tool, 200 / up to 2 for a parameter (a schema repeats that allowance
  once per property). Sentences are taken in the server's own order and only whole ones,
  short text passes through byte-identical, and no keyword ranking is used, because
  scoring on English words would quietly rank non-English descriptions lower. Measured
  on this repo's demo corpus (tiktoken `cl100k_base`): `tools/list` costs 83.9% of the
  native listing instead of 76.7% — 7.2 points of savings traded for more than double
  the surviving description text. Schema keys are still stripped, `call_tool` still
  validates against the full schema, and the `--slim` / `--compact` CLI figures are
  untouched (`slim_toon` never carried descriptions). ADR 0006 carries the amendment.

### Fixed
- **`serve` stops erasing declared MCP fields from `tools/list`.** The compactor
  rebuilt every definition from three fields, so a server's `title`, its
  `outputSchema` and the `openWorldHint` annotation vanished in transit: the client
  asked for the contract and got a shorter version of it instead, with the return
  shape left to guesswork. Those fields now pass through (the schema inside
  `outputSchema` is still compacted, and a server that declares nothing gains
  nothing).

## [0.7.12] — 2026-09-14

### Added
- **`mcptoon demo-server` — a built-in MCP server that needs nothing but Python.**
  Eleven tools, standard library only, speaking MCP over stdio: echo, TOON
  encode/decode, format comparison, token estimation, tool-schema slimming, manifest
  indexing, benchmark rows, agent config targets, config validation, runtime
  description. Add it with
  `mcptoon add demo --stdio python -m mcptoon demo-server`.

  Why it is in the package at all: hosted quality scores are computed by a sandbox
  that starts your server and calls `tools/list`. Ours was seeded with
  `npx -y @modelcontextprotocol/server-everything`, and the Python-only image has no
  Node in it — the seed resolved to **zero tools**, so the exam was handed a blank
  sheet (measured 2026-09-14). The same sandbox, same PATH, same empty home directory:
  the old seed lists 0 tools, `demo-server` lists 11.

  It changes nothing about the architecture. It registers no server, writes no
  config, opens no file, spawns no process, and touches no network; `mcptoon serve`
  with an empty config still lists zero tools, because the bridge is still a proxy and
  not a runtime. Both properties are pinned by tests, not by promises. The tool
  descriptions were written against the published TDQS rubric (verb first, a named
  sibling as the boundary, parameters described, limits disclosed) and the mechanical
  part of that rubric is now asserted in CI.

### Changed
- Footprint claims refreshed to measured values: 146KB wheel (was 128KB), 22 modules
  (was 21), 12,634 physical lines (was 11,750). Both READMEs, `DEVELOPERS.md`,
  `docs/`, the skill files and `tests/test_footprint_claims.py` move together.
- Both READMEs state the one exception to "mcptoon bundles nothing": the package ships
  a self-demo, and it reaches your context only if you add it deliberately.

### Testing
- `tests/test_demo_server.py` — 43 cases, 104 subtests: handshake, protocol fallback,
  notifications, stateless `tools/list`, every tool called in-process, the error paths,
  a real subprocess over stdio (including non-ASCII under a cp1252 console), the TDQS
  hard gates with a negative control proving the guard fires, the inlined benchmark
  rows compared against `assets/benchmark_tiktoken.json`, and a source-level check that
  the module imports no I/O, process or config machinery.

## [0.7.11] — 2026-09-14

### Fixed
- **`--help` no longer runs the command you asked about.** `mcptoon quickstart --help`
  executed the entire onboarding flow and wrote what it discovered straight into
  `~/.mcptoon/config.json` (measured on this machine: 4 servers in, 13 out);
  `mcptoon manifest --help` ignored the flag too and went out to every configured
  server, still running two minutes later. A newcomer probing the CLI was mutating
  their machine, or waiting on a network round trip, before reading a single line of
  help. Any `-h`/`--help` after a command now prints help and returns; `demo` and
  `serve` keep their own, richer help pages. (`cli.py`, `tests/test_help_shortcircuit.py`)
- **Real flags stopped being warned about.** `demo --quick`, `demo --keep` and
  `serve --auth` are implemented inside their own modules but were absent from the
  central registry, so `mcptoon demo --quick` — the exact line the demo prints as its
  own usage — opened with `mcptoon: unknown option '--quick' ignored`. `KNOWN_FLAGS`
  is now pinned against flag literals across the whole package, not just `cli.py`.
- **The copy-paste example on the front page installed a package that no longer
  exists.** `@modelcontextprotocol/server-fetch` is gone from npm (E404 confirmed
  against registry.npmjs.org on 2026-09-14), yet it was still the "add any MCP
  server — one command" line in both READMEs, in `docs/tiktoken-benchmarks.md`, in
  `DEVELOPERS.md`, and in the two places the CLI itself tells a server-less user what
  to run next. `demo.py` has carried a comment forbidding it since 2026-09-05; nothing
  kept the *prose* honest. Examples now use `@modelcontextprotocol/server-everything`
  (npm 2026.8.31), each one re-run end to end before it was written down.
- `serve`'s non-loopback refusal named a `--host` flag that has never existed; it
  names `--listen`, which is what it gates.

### Added
- README (EN + zh-CN) prints the **verbatim output of `mcptoon demo --quick`** — the
  30-second proof can now be read before it has to be trusted.

### Documentation
- `DEVELOPERS.md` (stuck on v0.7.5 / 730 tests) and `ROADMAP.md` (stuck on v0.7.2)
  headers refreshed; test-count badges follow the suite.

## [0.7.10] — 2026-09-12

### Fixed
- `manifest --full` now surfaces each parameter's `enum` and `default`
  (`{url|back|forward|reload}`, `=png`). Before, the human-readable full view
  dropped them, so an agent could emit a syntactically-valid but *semantically
  inert* call — e.g. `navigate_page` without `type=url`, a silent no-op. Costs
  +87 tokens on `--full` (still ~68% under native); the default compact/`--slim`
  tiers are unchanged.

### Added
- `validate_args` now rejects a scalar value that is not in the property's
  `enum` (previously required + type only), closing a serve-mode gateway blind
  spot where a wrong discriminator (`colorScheme:"PINK"`) was forwarded verbatim.
- Schema cache now stores a **content fingerprint** (sha256 of tool names +
  required-arg lists, hardened against malformed/`null` schemas).
  `set_cached_tools` reports whether the callable surface actually changed, and
  `serve`'s parallel manifest refresh logs tool-set drift from that signal — no
  payload diffing. (`cache.py`, `serve.py`, `tests/test_cache.py`)


## [0.7.9] — 2026-09-11

### Fixed
- `mcptoon health` no longer crashes on HTTP-transport servers: health passed
  `http_url=` to `MCPClient`, which only accepts `http=`, so every HTTP server
  check died with `TypeError` instead of reporting a status (#18, reported by
  @examosa). Regression tests now construct a real `MCPClient` with the exact
  kwargs health passes — the old suite stubbed the whole class, which is how
  this slipped past 792 green tests.

### Added
- `mcptoon doctor` prints a one-time GitHub star hint after a fully healthy
  run. Human output only: at most once per machine (cache marker), never in
  CI, suppressible via `MCPTOON_NO_STAR_HINT=1`; failing runs and structured
  outputs stay untouched.

## [0.7.8] — 2026-09-09

### Added
- `mcptoon demo` next-steps now push `mcptoon sync` (push the config into the
  agents you already run) before the star ask — the trial→adoption move from
  the conversion playbook. Pinned by `tests/test_demo.py`.
- **Per-tool compression policy** (`mcptoon policy`): pin how each tool's
  results are compressed — `raw`/`json` protects results that must never be
  compressed (images, base64, binary), `toon`/`compact`/`slim` forces a shape
  for one chatty tool, `server:*` sets a server-wide default. Applies to
  explicit `mcptoon call` runs and to the `mcptoon serve` bridge; explicit
  format flags always win. Stored in `~/.mcptoon/compression.json`
  (`MCPTOON_COMPRESSION_FILE` redirects it).
- README (EN+zh): "The industry converged on the same answer" — Anthropic's
  advanced-tool-use numbers (TST -85% definitions, PTC -37% orchestration) and
  MuleSoft's gateway adopting TOON as external validation, with source links.
- `skills/mcptoon/SKILL.md` at the repo root: the cross-agent distribution
  copy of the plugin skill (skills.sh-compatible layout), guarded to stay in
  sync with the plugin's trigger surface.

### Fixed
- publish-mcp.yml now waits for PyPI to list the released version before
  publishing the registry record — kills the race that needed manual
  workflow_dispatch retries on 0.7.6 and 0.7.7.

## [0.7.7] — 2026-09-08

### Fixed — the 0.7.6 wheel reported the wrong version

`pip install mcptoon==0.7.6` produced a wheel whose metadata said 0.7.6 but
whose `mcptoon --version` printed 0.7.5: the release bumped
`pyproject.toml` and `server.json` but missed the hardcoded `__version__`
in `src/mcptoon/__init__.py`. Caught by the post-release smoke test (fresh
venv against the official index) — which is now part of the written
release checklist, not just habit.

- `__version__` is 0.7.7 and matches the packaged metadata.
- `tests/test_registry_sync.py` now pins `mcptoon.__version__` against
  pyproject, so the next bump updates all of them or fails CI.

## [0.7.6] — 2026-09-08

### Added — stateless-first serve bridge + SEP-2549 CacheableResult (2026-07-28 GA server surface)

v0.7.0 brought the client side of the 2026-07-28 revision (spec negotiation,
`_meta` requests, `Mcp-Method`/`Mcp-Name` headers, MRTR). The GA spec's
server-side surface is now covered by the bridge (`mcptoon serve`):

- **Stateless-first**: the initialize handshake is no longer required. A
  modern client may call `tools/list` without ever sending `initialize`
  (the handshake still works for legacy clients, unchanged). Requests are
  self-describing: `_meta` with `io.modelcontextprotocol/protocolVersion`
  (or the pre-GA draft `protocolVersion` key) is honored on any request,
  and an unsupported version there is rejected with `-32022`
  (UnsupportedProtocolVersionError).
- **`server/discover` RPC** (SEP-2575): advertises `protocolVersions`,
  `capabilities` (with the GA `extensions` field) and `serverInfo`. No
  config load, no server startup — safe to probe up front.
- **CacheableResult (SEP-2549)**: `tools/list`, `prompts/list`,
  `resources/list` and `resources/read` results carry `ttlMs` and
  `cacheScope`. Defaults: 300000 ms / `public`; override via
  `MCPTOON_LIST_TTL_MS` and `MCPTOON_LIST_CACHE_SCOPE` (invalid values fall
  back safely). Clients can cache tool catalogs across reconnects, keeping
  upstream prompt caches stable.
- **`resultType: "complete"`** on every ordinary result (initialize,
  discover, ping, health, tools/list, prompts/list, resources/list,
  resources/read, tool call results and tool errors) per the GA results
  taxonomy. `input_required` (MRTR) behavior is a client-side concern and
  unchanged.
- 19 new tests (`tests/test_v076_stateless_serve.py`); README badges and
  counts updated.

### Added — official Claude Code plugin (`claude-code-plugin/`)

The whole mcptoon experience, installable inside Claude Code in one line:

```
/plugin marketplace add activeing123/mcptoon
```

- **SessionStart hook** (`scripts/session_setup.py`): reports CLI status on
  every session start; on the very first session auto-installs the
  zero-dependency wheel via pip (seconds, nothing else pulled in) and
  writes a one-time marker. Never raises - a broken environment cannot
  break the session. Cross-platform: `commandWindows` ships in
  `hooks/hooks.json` for native Windows sessions.
- **`.mcp.json`** wires the `mcptoon serve` bridge into the host session,
  so tool discovery arrives pre-compressed.
- **`skills/mcptoon/SKILL.md`** teaches the agent when and how to use the
  CLI (`manifest` / `inspect` / `search` / `call --auto` / `doctor`),
  including the rule to never quote savings numbers it did not observe.
- **`/mcptoon-setup`** command for guided manual setup and repair.
- Root `.claude-plugin/marketplace.json` turns this repository into a
  one-command marketplace. Guarded by `tests/test_claude_plugin_package.py`
  (10 tests): JSON validity, Windows hook variant mandatory, frontmatter
  trigger words, canonical-claims-only (banned-number blacklist shared
  with `test_footprint_claims.py`).

### Changed — 0.7.5 compatibility layer rollout to 0.7.6

Nothing to roll back; see the entries above. Test count grew 759 → 769.

## [0.7.5] — 2026-09-05

### Fixed — the documented way to reproduce the numbers did not exist

`mcptoon manifest --compact --tokens` was quoted in README.md, README.zh-CN.md,
DEVELOPERS.md, both articles, `assets/benchmark.html` and both token charts as the
way to verify the headline figures. `--tokens` was never implemented, and the parser
dropped unknown long options silently — so the command printed a listing and no
count, and nobody noticed.

- Unknown long options now warn on stderr
  (`mcptoon: unknown option '--tokens' ignored - see 'mcptoon --help'`) and are still
  passed through unchanged, so no existing behaviour shifts.
- `tests/test_cli_flags.py` pins the allowlist against the CLI source in both
  directions: a new option missing from `KNOWN_FLAGS` fails, and a dead entry fails.
- `scripts/bench_tokens.py` is the real reproduction path. It measures the tool lists
  cached on your machine with tiktoken (`cl100k_base` and `o200k_base`) across raw
  JSON, `--slim` and `--compact`, and prints the savings per format. tiktoken is a
  dev-only import; the runtime package is still stdlib-only.
- Every "reproduce it yourself" line now points at that script.
- `mcptoon --version` / `-V` print the installed version; they used to fall through to
  "Unknown command: --version".

### Fixed — stale savings figures in shipped text

- `--slim` was described as saving 93% (the pre-2026-08-12 artifact figure) in three
  `cli.py` help strings, in `output.py`, in `docs/integrations/codex.md` and in the
  `mcptoon demo` next-steps hint. Measured it is **88.5%**.
- `--compact` was described as "~20 tokens for 96 tools"; measured it is
  **~2.3 tokens per tool** (581 for 255).
- `docs/tiktoken-benchmarks.md`: removed the row "Compact (30 names) = 63 tokens,
  99.8%", which measured a listing truncated at 30 entries, and labelled its 39,964
  baseline as *Sample A* against the canonical *Sample B* (71,929 → 581).
- `assets/benchmark.svg` still charted 90,804 → 117 ("99.9%"); every bar is now
  regenerated from `assets/benchmark_tiktoken.json`.

### Fixed — README links and images were dead on PyPI

Warehouse resolves relative targets against the project page, so all 15 relative
links and images in README.md resolved to `https://pypi.org/project/mcptoon/<file>`
and 404'd. They are absolute now, and `tests/test_readme_links.py` keeps them that way.

### Changed — the English README no longer embeds Chinese-language assets

- `assets/token-savings-en.svg`: English chart for README.md (the Chinese original
  stays with README.zh-CN.md).
- `assets/demo-en.gif`: English terminal demo, rendered from a real
  `pip install mcptoon` + `mcptoon demo` transcript captured on a clean virtualenv;
  `scripts/make_demo_gif.py` holds the transcript and does the rendering, so only the
  frame pacing is synthetic.
- `assets/benchmark.html` carries a "superseded snapshot" banner pointing at the
  current caliber instead of silently showing old numbers.

### Fixed — Windows-only flake in the HTTP auth suite

`tests/test_v073_http_security.py` failed about one run in five on Windows with
`ConnectionAbortedError [WinError 10053]`. The scenario is the point of the test: the
server answers 401 *before* reading the request body, and the Windows stack aborts the
connection while the client is still uploading, so urllib surfaces a transport error
instead of `HTTPError`. `_do()` now retries that abort — bare, or wrapped in `URLError`
— with a short backoff, keeping the assertion about the response the server produced
rather than how the transport reported a rejected upload. 15 consecutive green runs
verified.

## [0.7.4] — 2026-09-05

### Fixed — `mcptoon demo` broken on every machine without a stale npm cache

`demo.py` spawned `npx -y @modelcontextprotocol/server-fetch`, a package
that no longer exists on the npm registry (E404, verified 2026-09-05).
The server died instantly; the client surfaced a bare
`PROCESS_DIED failed writing ... [Errno 22]` (Windows) or broken pipe
(POSIX) with the real `npm error 404` swallowed by the error path.

- demo now runs the official `@modelcontextprotocol/server-everything`
  reference server and its `echo` tool — self-contained, no API key,
  no network fetch.
- `PROCESS_DIED` from the stdio write path now includes the server's
  stderr tail. The tail is drained once and cached (`_stderr_tail`) so
  every failure along the probe → legacy-handshake fallback chain
  carries the same diagnostic; the read runs in a 1s-capped helper
  thread so a live server can never block the request path.
- demo benchmark table aligned with `assets/benchmark_tiktoken.json`
  (255 tools: 71,929 → 581 tokens, −99.2%); the old hardcoded
  90,804 → 117 numbers predated the 2026-08-12 honest re-benchmark.

Tests: `tests/test_demo_dead_package.py` (6).

### Fixed — `mcptoon manifest --compact` truncated the tool index

For a manifest-shaped input (`{server: [tool names]}`), the compact encoder
fell through to `json.dumps(...)[:200]`, producing a headless JSON fragment
with ~9 tool names, no closing brace and no "more" hint — an agent using
`--compact` for discovery silently saw only the first handful of tools.
The manifest shape now expands to the FULL `server: n1, n2 · …` name index
(no truncation, no JSON), matching the documented −99.2% claim (581 tokens
for 255 tools). Scalar/dict-without-name behavior is unchanged.

Tests: `tests/test_output.py::TestRender` (3 regression tests).

### Docs — benchmark numbers unified to the measured 581 / −99.2% caliber

The "255 tools = 123 tokens" figure was a 30-item truncation artifact from
the benchmark harness; the full name index of the same 255-tool config
measures 581 tokens (−99.2% vs 71,929 raw JSON). README (en/zh), FAQ,
DEVELOPERS.md, comparison.md, articles (en/zh), token-savings.svg,
benchmark_tiktoken.json, server.json, plugin skill copy, pyproject
description and the demo table now all carry the measured 581 / 99.2%
figures. Historical CHANGELOG entries are preserved as-is.

### Fixed — stdio hang: silent servers can no longer freeze the client

Root cause found on 2026-09-03 while investigating "tool calls broke after
the v0.7.3 update": the update was innocent. The real defect was old —
`_stdio_request()` read server responses with a blocking
`stdout.readline()` that had **no deadline**. A server that stays silent on
the `server/discover` probe (e.g. `mcp_server_fetch` 2026.8.18, which sends
nothing at all — not even a `-32601` error) hung the client **forever**.
Any command that enumerates every configured server (`doctor`, `manifest`,
`discover`, `--auto`) could be permanently stuck by one dead config entry.

- **Response pump thread**: a background thread now owns stdout and routes
  every JSON-RPC response to a per-id queue (`_stdio_pump`, module-level
  and directly testable). Requests wait on the queue with a deadline —
  silence now surfaces as `MCPError("RESPONSE_TIMEOUT")` instead of a
  lifetime hang. Late responses for timed-out requests are parked in a
  lost-and-found deque instead of poisoning the next request.
- **EOF wakes all waiters**: a dead server process fails fast with
  `PROCESS_DIED` instead of holding requests until their full timeout.
- **Probe deadline capped at 10s**: `server/discover` probing uses
  `min(timeout, 10s)`, so `spec="auto"` fallback to the legacy handshake
  costs seconds, not the full request timeout. Servers answering the probe
  within 10s still negotiate modern mode (slow-but-alive is preserved).
- **Request-level timeout plumbing**: `_stdio_request(payload, timeout=)`
  accepts the per-request deadline (HTTP transport already did).

Tests: `tests/test_v074_stdio_timeout.py` (12) — real-subprocess
reproductions of the silent-server hang, EOF fail-fast, slow-probe
negotiation (3s stays modern / 12s falls back), lost-and-found parking,
plus fake-process pump routing unit tests. Suite total: 682 (+12).

## [0.7.3] — 2026-09-02

### Security — HTTP serve hardening (red-team findings, 2026-09-02)

Findings from an adversarial security review of `mcptoon serve --http`.
Found via line-level code audit; each fix ships with reproduction tests
(`tests/test_v073_http_security.py`, 30 tests).

- **Loopback-by-default binding**: bare `--http` / `--listen :8080` now binds
  `127.0.0.1` instead of `0.0.0.0`. A network-exposed, unauthenticated MCP
  gateway is no longer one flag away by accident.
- **Non-loopback bind requires auth**: `--listen 0.0.0.0:9090` without
  `--auth` is now refused outright (exit 2) instead of silently serving your
  tools to the whole LAN. The risky combination can no longer be constructed.
- **Bearer `--auth` without value auto-generates** a secure token
  (`secrets.token_urlsafe(32)`), printed to stderr exactly once
  (Jupyter-style). `MCPTOON_AUTH_TOKEN` env var still honored.
- **Auth checked on GET too, before body parsing**: `/health`, `/status`, `/`
  previously skipped the token check; POST parsed the request body before
  verifying auth. Both closed — a bad token now short-circuits with 401
  before any body is read.
- **Browser CSRF / DNS-rebinding guard**: `Origin` and `Host` headers are
  validated on every request (403 when they don't belong). curl, agents and
  scripts that send neither header are unaffected; the attack surface is
  browser pages, which always send both. Extra hostnames can be allowlisted
  via `MCPTOON_ALLOWED_HOSTS`.
- **Content-Type gate**: POST with `text/plain` or `multipart/form-data`
  (browser form-post CSRF carriers) → 415. `application/json`, absent
  headers and curl-style raw posts still accepted.
- **`prompts/get` poisoning guard**: plugin SKILL.md bodies returned by
  `prompts/get` previously bypassed the injection scanner entirely. The same
  heuristic now runs; a poisoned skill raises MCPError -32003.
- **`_check_poisoning` hardening**: full-text scan (the old first-5000-chars
  truncation was a bypass), NFKC normalization (defeats fullwidth homoglyphs),
  zero-width character stripping + density signal (defeats `ig\u200bnore`
  splitting), and a Chinese indicator list. Still documented as a heuristic
  safety net, not a security boundary.

### Changed

- `run_serve --help` exits via `SystemExit(0)` (was plain return)
- New test-suite total: 660 passed (+30 security tests)

## [0.7.2] — 2026-09-01

### Added — first-run delight (beginner-friendly output)

- **`mcptoon quickstart` celebration**: after a successful setup, quickstart now
  closes with a big-number payoff — "🎉 N tools ready across M servers!" —
  followed by a two-command "Now you can" block (`sync` to write configs into
  every agent, `serve` to expose all servers as one stdio gateway).
  `--dry` mode stays sober (no celebration, plain next-steps only).
- **`mcptoon demo` before/after headline**: the token comparison now leads with
  one plain sentence — "📊 SAME data, X% fewer tokens: 12,400 → 117" — before
  the detailed table, and the benchmark ends with a "Now you can" checklist
  (one config for every agent, one gateway, zero schema tokens).
- **One-line installers**: `install.sh` (macOS/Linux/WSL, pipx → pip --user →
  PEP 668 venv fallback) and `install.ps1` (Windows, py launcher detection,
  PATH fix-up) — both end by handing off to `mcptoon quickstart`:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/activeing123/mcptoon/main/install.sh | bash
  ```
  ```powershell
  irm https://raw.githubusercontent.com/activeing123/mcptoon/main/install.ps1 | iex
  ```
- **Official first-party plugin** `plugin/mcptoon-skills`: three SKILL.md files
  (connect / authoring / triage) that teach any agent how to drive mcptoon.
  Install it and the skills appear as MCP prompts through `mcptoon serve` —
  mcptoon eats its own Agent Plugins dog food.

### Fixed

- Plugin skills are exposed as MCP prompts by `mcptoon serve`
  (`prompts/list`, `prompts/get`; capability advertised in initialize) —
  shipped in 0.7.1 codebase, documented from 0.7.2.

## [0.7.1] — 2026-08-31

### Added — Agent Plugins Specification 1.0.0 support

mcptoon now installs, validates and manages the new cross-vendor AI agent
plugin standard (https://agent-plugins.org — backed by Amazon, Cursor,
Microsoft, OpenAI and Vercel). The spec deliberately leaves installation,
distribution and cross-agent sync undefined — mcptoon fills exactly that gap:
install once, every agent can use it.

- **`mcptoon plugin scan <dir>`**: strict read-only validation per spec 1.0.0 —
  closed manifest schema (`$schema` pinned to 1.0.0; 1.1.0 drafts rejected),
  name rules (1-64 chars, no `--`/`..`), three-variant closed union for
  `mcpServers` (stdio / streamable-http / sse), single-token commands
  (no shell strings, no expansion), HTTPS-only non-loopback URLs, no
  credentials in headers, path-escape checks on `./` commands.
  Failure boundaries follow the spec: structural problems are fatal;
  a broken server entry skips that entry only.
- **`mcptoon plugin install <dir> [--force] [--no-sync]`**: scan → copy to
  `~/.mcptoon/plugins/<name>/` → merge `mcpServers` into `config.json` under
  collision-free `<plugin>:<server>` namespaces → trigger the existing sync
  flow to every agent. **The pivot**: mcptoon is the installer, so
  `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` are pre-expanded into absolute paths at
  merge time — agents need zero plugin-loader support.
- **`mcptoon plugin list` / `mcptoon plugin remove <name>`**: registry-backed
  (`~/.mcptoon/plugins.json`); removal prunes the namespaced entries from
  mcptoon config AND every agent config it reached (sync merges, it never
  deletes — pruning closes that gap). The persistent data dir
  `~/.mcptoon/plugins-data/<name>/` is kept across `--force` upgrades and
  removal, per spec §PLUGIN_DATA.
- **stdio `cwd` support** end to end: config entries may carry `cwd`, the
  client passes it to the spawned process, and sync forwards it to agent
  configs (needed by plugins that pin a working directory).
- **Env-var injection**: plugin servers get `PLUGIN_ROOT` / `PLUGIN_DATA`
  injected at start, as the spec requires.
- 41 new tests (610 total) + 19-point acceptance livefire: scan → install →
  list → verify expanded absolute paths in a real Claude Desktop config →
  remove → verify everything cleaned. README (EN + zh-CN) carries an
  Agent Plugins badge and section.

## [0.7.0] — 2026-08-29

### Added — MCP 2026-07-28 support (latest spec, stateless revision)

- **MCP Registry ready**: the package README now carries the
  `mcp-name: io.github.activeing123/mcptoon` ownership marker required by the
  official MCP Registry (registry.modelcontextprotocol.io).
- serve help text: replaced an internal tool name with a neutral description
  ("for Claude Code and other local agents").

- **Automatic version negotiation** (`spec="auto"`, the new default): the client
  probes every server with the 2026-07-28 `server/discover` RPC first. Servers
  that answer get stateless modern semantics; anything that rejects the probe
  silently falls back to the classic `initialize` handshake (now declaring
  `2025-06-18` instead of `2024-11-05`). Zero configuration change for
  existing users — mixed fleets of new and old servers just work.
- **Stateless request annotation**: in modern mode every request carries
  `_meta` with `io.modelcontextprotocol/protocolVersion`,
  `io.modelcontextprotocol/clientCapabilities` and
  `io.modelcontextprotocol/clientInfo` — no initialize handshake, no session.
- **Streamable HTTP 2026-07-28 headers**: requests carry the required
  `Mcp-Method` (and `Mcp-Name` for `tools/call`); `Mcp-Session-Id` is never
  sent in modern mode. Legacy mode keeps session capture/replay.
- **MRTR — Multi Round-Trip Requests** (SEP-2322): a `resultType:
  "input_required"` result raises `MCPInputRequired` (code `INPUT_REQUIRED`)
  carrying `input_requests` / `request_state`. Answer and retry with
  `call_tool(..., input_responses=..., request_state=...)` (API) or
  `mcptoon call <server> <tool> --input-responses '<json>'
  --request-state <token>` (CLI) — the retry echoes `params.requestState`
  so a stateless server can correlate the two rounds. The router error
  envelope exposes the same detail for Agent integrations.
- **`UnsupportedProtocolVersionError` handling** (`-32022`): in auto mode the
  client falls back to the legacy handshake once and replays the request.
- **Per-server spec pinning**: `spec: "auto" | "2026-07-28" | "legacy"` in
  `~/.mcptoon/config.json`; `spec="2026-07-28"` fails loudly
  (`NO_MODERN_SUPPORT`) when a server can't keep up instead of guessing.
- `MCPClient.server_info` / `MCPClient.server_capabilities` now populated in
  both modes; `PROTOCOL_VERSION` alias moved to `2025-06-18` (was
  `2024-11-05`); new constants `LATEST_PROTOCOL_VERSION`,
  `LEGACY_PROTOCOL_VERSION`, `SUPPORTED_PROTOCOL_VERSIONS`.
- 21 new tests (`tests/test_v07_spec2026.py`): negotiation, stateless shaping,
  header/session semantics, MRTR raise + retry (incl. `requestState` echo),
  -32022 fallback, pool spec config, string-command leniency. Live-fire
  battery against a spec-accurate 2026-07-28 HTTP server, a real stdio
  subprocess server and `mcptoon serve`: 10/10. Suite: **569 passed**.

### Fixed

- `MCPClientPool._make_client` accepts a bare string `"command": "python"`
  (wrapped as `["python"]`) instead of crashing with `TypeError: can only
  concatenate str (not "list") to str` — the old failure surfaced downstream
  as a silent `0 tools` tool index in `mcptoon serve`.
- `MCPClientPool.call/call_full` only forward `input_responses`/
  `request_state` when provided, keeping subclasses with pre-0.7 signatures
  working.

## [0.6.1] — 2026-08-27

### Added — Latest MCP spec compatibility (2025-06-18)

- **`structuredContent` native parsing**: when a new-spec server returns
  structured output, `call_tool()` now prefers it over text content
  automatically — no flags needed. Old-spec servers behave exactly as before.
- **`mcptoon call <server> <tool> --envelope`**: new flag returning the
  complete MCP `tools/call` result envelope as JSON — `structuredContent`,
  `_meta`, `resultType`, `isError`, `content` all intact. Works with
  `--auto` routing too.
- **Library API**: `MCPClient.call_tool_full()` and `MCPClientPool.call_full()`
  for envelope-level access from Python.
- 8 new tests (548 total). README (EN + zh-CN) documents the compatibility
  matrix with a prominent spec badge.

## [0.6.0] — 2026-08-26

### Added — Usage dashboard & per-tool toggle

- **`mcptoon stats`**: token-savings dashboard with per-server/per-tool breakdowns.
- **`mcptoon toggle <server> <tool>`**: flip a single tool on/off without touching
  the server config; `toggle --list` shows what is disabled. Tool-level control
  no competitor offers at the CLI layer.
- `TOGGLE_FILE` (`~/.mcptoon/toggles.json`) with safe-load defaults.

## [0.5.6] — 2026-08-26

### Changed — Error envelope & usage-tracking hardening

- **Richer error envelope**: `make_error()` now records which component
  raised the error (`component`, legacy `source=` accepted as alias) and
  groups extra keyword context under `_error.detail` instead of spreading
  it at the top level of the result dict.
- **New helpers**: `error_code(obj)` / `error_message(obj)` for reading
  the envelope without touching its internals (`error_message` aliases
  `get_error_message`).
- **Concurrent-safe usage tracking**: `track_call()` is now guarded by a
  thread lock and writes atomically (unique tmp file + `os.replace`), so
  concurrent agent processes can never corrupt `usage.json`; tracking
  failures are swallowed so they never break a live tool call.

## [0.5.5] — 2026-08-25

### Added — Continuous sync (`mcptoon sync --watch`)

- **`--watch` flag**: `mcptoon sync --watch` keeps every detected agent's MCP
  config aligned with `~/.mcptoon/config.json`. Pure-stdlib polling
  (os.stat fingerprinting) — no watchdog dependency, identical behavior on
  Windows, macOS and Linux.
- **Drift detection**: external edits to agent config files are detected.
  Merge mode (default) re-syncs while preserving manually-added servers;
  `--watch-mode strict` warns instead of touching the file.
- **Debounced writes**: burst saves from editors collapse into one sync round.
- **Failure guard**: aborts with exit code 1 after 5 consecutive failed rounds.
- **Flags**: `--interval N`, `--quiet`, `--watch-mode merge|strict`.
- 18 new tests (total 531).
- New docs page: `docs/comparison.md` — setup, token and safety numbers for
  every approach to cross-agent MCP management, category by category.
- README rewritten in English and Chinese: zero-setup positioning,
  tiktoken-verified benchmarks, illustrated how-it-works diagram.
- PyPI/repo description aligned to the measured 99.8% figure (was 99.9%).

## [0.5.4] — 2026-08-24

### Added

- **`sync` command**: write mcptoon's unified config to each detected agent's
  native format (Claude Desktop, Cursor, Cline, Windsurf, VS Code Copilot,
  Codex), merging without clobbering manual entries.
- **`health` command**: check all configured servers with per-server timeout;
  JSON output plus non-zero exit code for CI/CD pipelines.
- Shell completion fixes.

## [0.5.3] — 2026-08-22

### Fixed — PyPI publish workflow

- **PyPI API Token BOM fix**: GitHub Secret `PYPI_API_TOKEN` was corrupted with a BOM character (`\ufeff`) causing `UnicodeEncodeError: 'latin-1' codec can't encode character` during publish. Token re-imported from Bitwarden without BOM.
- **Version sync**: `pyproject.toml` and `__init__.py` both updated to 0.5.3.
- Removed stale `# -*- coding: utf-8 -*-` from source files (Python 3 default).
- Trailing whitespace cleanup in `output.py`.

## [0.5.2] — 2026-08-20

### Fixed — README and PyPI metadata corrections

- **Test count corrected**: README badge and text updated from 427 → 486 (tests added in v0.5.1 but count not updated)
- **Benchmark reference fixed**: Removed reference to non-existent `_benchmark.py` script
- **PyPI metadata fixed**:
  - `pyproject.toml` description updated to match GitHub description (99.87% token savings, not outdated 97%)
  - `[project.urls]` added with Homepage, Repository, Documentation, Changelog, Issues, PyPI links (was missing entirely)
  - TOML structure fixed: `requires-python`, `keywords`, `classifiers`, `dependencies` were incorrectly placed under `[project.urls]` section
- **GitHub repo description updated**: From "97% less tokens" to "99.87% less tokens on tool discovery"

## [0.5.1] — 2026-08-19

### Added — serve HTTP mode + demo command + 20 critical bug fixes

- **`mcptoon serve --listen` HTTP mode** — mcptoon serve now supports HTTP mode for remote/multi-agent access. Agents can connect via HTTP POST to `/mcp` endpoint. Health check at `/health`.
  ```bash
  mcptoon serve --listen :8080          # HTTP mode on port 8080
  mcptoon serve --http                   # Shorthand for --listen :8080
  mcptoon serve --listen 0.0.0.0:9090   # Bind to all interfaces
  ```
  - Multiple agents can connect simultaneously (unlike stdio which is single-connection)
  - JSON-RPC over HTTP, compatible with MCP HTTP transport
  - Health check: `GET /health` returns `{"status":"ok","servers":N,"tools":N}`

- **`mcptoon demo` command** — Zero-config one-command demo for the "aha moment":
  1. Starts a demo MCP server (fetch, no API key needed)
  2. Calls a tool and shows JSON vs TOON vs SLIM token comparison
  3. Shows the 255 tools benchmark (90,804 → 117 tokens)
  ```bash
  mcptoon demo                # Full demo, step by step
  mcptoon demo --quick        # Fast: skip step-by-step
  mcptoon demo --keep         # Keep demo server in config
  ```

- **Parallel manifest loading** — `MCPServerBridge` now uses `ThreadPoolExecutor` with 20 concurrent workers for manifest loading. 100 servers load in ~5s instead of 500s serial.
- **Per-call timeout** — Each tool call has a 30s timeout (configurable via `MCPTOON_CALL_TIMEOUT`), preventing hung servers from blocking the bridge.
- **Remote MCP support** — HTTP/SSE MCP servers are now handled transparently by the bridge.
- **18 new tests** for demo command — Total: 425 tests.

### Changed
- **Removed all 23 bundled server profiles** — mcptoon now ships zero bundled content. Users add exactly the servers they want via `mcptoon add` / `mcptoon install`. The `mcp/` directory and `_match_profiles()` discovery layer have been removed. This eliminates cognitive overhead: nothing pre-configured, nothing to ignore, nothing to explain.
- Discovery reduced from 5-layer to 4-layer (removed profile matching layer).
- Architecture simplified from 3-layer to 2-layer (CLI + actual MCP servers).
- `MCPClientPool._get_client` refactored to move `client.initialize()` outside the lock, allowing parallel server initializations.

### Fixed — 20 critical bug fixes

- **`installer.py` TypeError** — Removed invalid `name=` argument passed to `MCPClient()` constructor (2 call sites).
- **Version mismatch** — `pyproject.toml` was stuck at `0.2.3` while `__init__.py` had `0.5.0`. Synced to `0.5.0`.
- **HTTP serve stdout race condition** — Replaced global `sys.stdout` swap with thread-local `_response_capture` buffer. Concurrent HTTP requests no longer clobber each other's responses.
- **Streamable HTTP support** — `_parse_http_body()` now handles multi-event SSE streams (picks last response with `result`/`error`). `_http_request()` checks `Content-Type` header and handles both `text/event-stream` and `application/json`.
- **HTTP error handling** — `HTTPError` responses now parsed as JSON error objects before raising, allowing structured error propagation.
- **`resources/read` and `prompts/get`** — Bridge now responds to these MCP methods (previously returned `method not found`).
- **`logging/setLevel`** — Bridge acknowledges client logging level changes.
- **JSON-RPC batch support** — HTTP handler now accepts arrays of requests and returns array of responses.
- **`notifications/cancelled`** — Bridge now handles cancellation notifications gracefully.
- **HTTP authentication** — Added `--auth <token>` flag and `MCPTOON_AUTH_TOKEN` env var. When set, requests must include `Authorization: Bearer <token>` header.
- **Connection pool resource leak** — When two threads race to create the same client, the losing client is now properly closed (was: silently leaked subprocess).
- **`router.py` pool reuse** — Router now reuses a global `MCPClientPool` instead of creating a new pool (spawning all subprocesses) on every `call_tool()` invocation.
- **Cache file locking** — `cache.py` rewritten with in-process `threading.Lock` + atomic file writes (`os.replace`). Prevents data corruption from concurrent writes.
- **stdio multi-line response** — `_stdio_request()` now reads lines in a loop until it finds a JSON-RPC response with an `id` field, skipping notification lines and debug output. Previously only read one line, breaking on multi-line responses.
- **Auto-reconnect for stdio** — `_reconnect_if_dead()` checks if process has exited before each request and restarts it automatically. Clears tools cache on reconnect.
- **`close()` robustness** — Added `proc.wait(timeout=1)` after `kill()` and `finally: self._proc = None` to ensure cleanup even on exception.
- **Timeout subprocess kill** — When a tool call times out, the underlying subprocess is now killed (was: thread abandoned but subprocess kept running).
- **Demo token counting** — `_show_token_comparison()` now uses `tiktoken` if available for accurate token counts, with `len//4` fallback. Previously used only `len//4`.
- **Health endpoint honesty** — `_handle_health()` now returns `"starting"` when not initialized, `"degraded"` when some servers failed, `"error"` when all failed. Previously always returned `"ok"`.
- **Handler template imports** — Generated handler files now import from `mcptoon.client.MCPClient` instead of non-existent `daemon.py`/`mcp_client.py` modules.
- **Server alias resolution** — `resolve_server_name()` now checks config dynamically for prefix matches (e.g. `fs` → `filesystem`), not just static aliases.
- **`.gitignore`** — Added `local/`, `__pycache__/`, `_*.py`, `_*.txt` to prevent temp files and private layer from being committed.
- **Cleaned 40+ temporary scripts** — Removed `_1000stars.py`, `_benchmark.py`, `_check_shadowban.py`, etc. from project root.
- **`test_v02_features.py` syntax error** — Fixed method name with space (`test_slim_format Renders_tools` → `test_slim_format_renders_tools`).
- **`test_serve.py` health test** — Updated to accept `"starting"` status for uninitialized bridges.

### Planned
- awesome-mcp-clients PR submission
- `--watch` mode for long-running tool calls
- Connection pool reuse (keep stdio processes alive across calls)

## [0.5.0] — 2026-08-17

### Added — Install command + local handler architecture + forwarding layer

- **`mcptoon install` command** — One-command MCP server installation with auto-handler generation. Connects to the server, discovers tools, generates a Python handler, and registers it. No restart needed.
  ```bash
  mcptoon install brave-search --npm @anthropic/mcp-server-brave-search
  mcptoon install my-tool --pip mcp-my-tool
  mcptoon install remote-api --url https://example.com/mcp
  mcptoon install --list
  mcptoon install --remove brave-search
  ```

- **Local handler architecture** — Public core (`src/mcptoon/`) + private layer (`local/`) separation. The `local/` directory contains:
  - `cli_pro.py` — Enhanced CLI entry point with handler injection
  - `handlers/` — 30+ auto-generated handlers for MCP servers
  - `router.py` — Bridge router that checks local handlers before falling back to MCP
  - `daemon.py` — Background daemon for connection pooling
  - `core.py` — Remote execution core for SSH-based MCP calls

- **Forwarding layer** — `universal_call.py` forwards old CLI commands to the new `cli_pro.py` entry point, ensuring zero-disruption migration for existing skills and scripts.

- **`call --auto` now searches local handlers first** — Router prioritizes local handlers before MCP servers, ensuring faster response for registered tools.

- **Daemon fallback** — If daemon fails to start, `call` automatically falls back to single-shot mode for maximum reliability.

- **Skill Direct-Invoke mode** — Skills can directly call CLI commands without loading MCP schemas into context, achieving 0-token MCP usage.

- **ADR documentation** — Architecture Decision Records added in `docs/adr/`:
  - `0001-cli-mode-over-mcp-protocol.md` — Why CLI mode beats MCP protocol injection
  - `0002-public-core-private-layer-separation.md` — Dual-track architecture decision
  - `0003-toon-format-as-primary-output.md` — TOON as the default output format
  - `0004-forwarding-layer-for-backward-compatibility.md` — Forwarding layer for seamless transition

- **E2E test suite** — 10/10 tests passing, covering: echo, gbrain search, gbrain list_pages, servers, doctor, manifest, inspect (×2), call --auto, forwarding layer, install --list.

### Changed
- Bumped version to 0.5.0
- `router.py` now checks local handlers before MCP servers in `call_tool_auto`
- `daemon.py` startup path fixed for Windows, wait time reduced
- `installer.py` moved from `local/` to `src/mcptoon/` (public core)
- `installer.py` adapted to use `MCPClient` from public core

### Fixed
- Daemon startup path error on Windows
- `call --auto` not searching local handlers
- `UNKNOWN_SERVER` errors for gbrain, exa, tinyfish, github
- Double `try/except` nesting in handler bridge
- SSH remote script path for Windows targets

## [0.4.1] — 2026-08-14

### Added — Zero-config discovery + cross-server search + auto-routing + fallback-json + TOML

- **`discover.py` module** — Five-layer auto-discovery of MCP servers, zero dependency:
  1. **Config scanning** — imports from Claude Desktop, Cursor, Cline, Windsurf configs
  2. **Environment detection** — detects `GITHUB_TOKEN`, `BRAVE_API_KEY`, `EXA_API_KEY`, etc.
  3. **Local tool detection** — checks `npx`/`uvx`/`docker`/`sqlite3` in PATH, git repo
  4. **HTTP endpoint detection** — checks `MCP_HTTP_URL` env var for HTTP MCP endpoints
  5. **Profile matching** — matches bundled profiles against satisfied env vars

- **`mcptoon search <query>`** — Cross-server tool search with multi-factor scoring
- **`mcptoon call --auto <tool> [args]`** — Cross-server auto-routing
- **`--fallback-json` flag** — Degradation safety net
- **TOML config support** — `~/.mcptoon/config.toml`
- **`quickstart` command** — One-command onboarding
- **`init --auto` command** — Zero-config setup

### Tests — 97 new tests (309 → 407 total)

### Changed
- Bumped version to 0.4.1
- `discover` command now runs full auto-discovery (was: health check only)
- `init` command now accepts `--auto` flag for zero-config setup

## [0.4.0] — 2026-08-12

### Added
- **Standard TOON adoption** — Implemented `toon_encode()` / `toon_decode()` following the [TOON (Token-Oriented Object Notation)](https://github.com/toon-format/toon) spec. Uses YAML-style indentation for objects and CSV-style tabular layout for uniform arrays. Round-trip safe: `decode(encode(x)) == x`.
  ```python
  from mcptoon.output import toon_encode, toon_decode
  toon_encode({"name": "search", "count": 3})
  # → "name: search\ncount: 3"
  toon_encode([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
  # → "[2]{id,name}:\n  1,Alice\n  2,Bob"
  ```
- **TOON decoder** — `toon_decode()` reverses `toon_encode()`. Handles all types: strings (with CSV quoting/escaping), numbers, booleans, null, nested objects, uniform arrays, scalar arrays, mixed arrays.
- **31 cross-validation tests** — `tests/test_toon_cross_validate.py` validates TOON spec conformance: object encoding, scalar values, string escaping, array CSV-style, round-trip safety, token efficiency. Total tests: 293.
- **CLI flag separation** — `--toon` and `--mcptoon` are now properly separated in the CLI arg parsing chain (fixed `if` → `elif` bug).
- **`__main__.py` support** — `python -m mcptoon` now works as an alternative to the `mcptoon` command. Required for some CI/CD environments and Docker containers.
- **Error fix suggestions** — CLI errors now include actionable fix suggestions. 10 error codes covered: `SERVER_NOT_FOUND`, `CONFIG_MISSING`, `TOOL_NOT_FOUND`, `UNKNOWN_TOOL`, `CONNECTION_FAILED`, `TIMEOUT`, `DANGEROUS_OP`, `CREDENTIAL_LEAK`, `TOOL_POISONING`, `PARSE_ERROR`.
  ```bash
  $ mcptoon call nonexistent tool '{}'
  Error [SERVER_NOT_FOUND]: Server not found: nonexistent
    Fix: Try: mcptoon list | mcptoon add <name> --stdio npx -y <package> | mcptoon doctor
  ```
- **16 new tests** — `tests/test_v04_features.py` covers `__main__.py` and error fix suggestions. Total tests: 309.

### Changed
- Bumped version to 0.4.0
- `output.py` now exports `toon_encode` / `toon_decode` as the standard TOON API, alongside legacy `mcptoon_encode` / `mcptoon_decode`
- `pyproject.toml` classifier updated to `Production/Stable`
- Benchmark updated to v4: now compares 5 formats (JSON vs Standard TOON vs mcptoon vs SLIM vs Compact)
- CI lint step updated to use `toon_encode` / `mcptoon_encode` instead of deprecated `toon` alias
- `errors.py` copyright year updated to 2025-2026

### Fixed
- **cli.py flag parsing bug** — `--toon` was parsed with `if` instead of `elif`, causing it to be in a separate if-chain from `--json`/`--compact`. Fixed to `elif`.
- **Legacy mcptoon format data loss** — Strings containing colons, pipes, or newlines were corrupted. Now properly escaped with `\c` (colon), `\p` (pipe), `\\` (backslash), `\n` (newline). Round-trip safe with `mcptoon_decode()`.

### Benchmark Results (v4, 255 tools)

| Tools | JSON | Std TOON | mcptoon | SLIM | Compact |
|-------|------|----------|---------|------|---------|
| 5 | 1,897 | 981 (-48%) | 785 (-59%) | 111 (-94%) | 16 (-99%) |
| 50 | 17,790 | 8,776 (-51%) | 6,981 (-61%) | 1,203 (-93%) | 117 (-99%) |
| 93 | 33,191 | 16,426 (-51%) | 13,086 (-61%) | 2,231 (-93%) | 117 (-100%) |
| 255 | 90,804 | 44,863 (-51%) | 35,735 (-61%) | 6,174 (-93%) | 117 (-100%) |

## [0.3.0] — 2026-08-12

### Fixed
- **TOON scalar substitution honesty** — Removed `∅` (null→∅) and `↲` (newline→↲) substitutions that tiktoken-verified as **worse** than original (2 tokens vs 1). Kept `true`/`false` as-is (1 token either way). Savings now come from structural compression only (removing JSON braces, quotes, brackets). Verified with tiktoken o200k_base + cl100k_base.
- **README benchmark data** — Updated all TOON savings claims with tiktoken-verified numbers. Added tokenizer version notes. Honest about what saves tokens (structure) vs what doesn't (scalar substitution).

### Changed
- `_toon_scalar()`: `null` stays `null` (not `∅`), `true`/`false` stay as-is (not `T`/`F`), newlines kept as-is (not `↲`), colons → `_` (not `＿`)

## [0.2.3] — 2026-08-12

### Added
- **Credential leak detection** — Scans tool results for 12 credential patterns (AWS Access Keys, AWS Secret Keys, GitHub PATs, GitHub Fine-grained PATs, OpenAI API Keys, Anthropic API Keys, Slack Tokens, Google API Keys, Private Key Blocks, Generic Credentials, Bearer Tokens, JWT Tokens). Blocks results before they reach agent context. Credentials are masked in error messages (`sk-abc...wxyz`).
  ```bash
  $ mcptoon call github get_file --toon
  # Error: CREDENTIAL_LEAK — potential OpenAI API Key leak detected: sk-abc...wxyz
  ```
- **23 security-audited MCP server profiles** — Each profile now includes a `security` block declaring `credential_safe`, `env_vars_required` (with sensitivity levels), and `permissions` (read/write scope). 3 new profiles added: `aws`, `cloudflare`, `tmux`.
- **Benchmark data with SVG chart** — Measured benchmark across 255 tools / 23 servers. 99.87% token reduction on tool discovery. SVG chart and interactive HTML page in `assets/`.
- **Third-party research citations** — README now references Anthropic, OpenAI, Cursor, Latent Space, and Simon Willison sources validating the token waste problem.
- **46 credential leak detection tests** — Full coverage of all 12 patterns, masking behavior, false positive edge cases. Total tests: 187.

### Changed
- Bumped version to 0.2.3
- `call_tool()` in `router.py` now scans results for credential leaks in both custom handler and MCP protocol paths
- `pyproject.toml` description updated to reflect credential leak detection feature
- README test count updated from 160 to 187
- README line count updated to ~2,500

### Security
- Credential leak detection prevents API keys, tokens, and private keys from entering agent context via MCP tool results

## [0.2.2] — 2026-08-11

### Added
- **`--slim` output format** — Ultra-compact tool manifest encoding (`tool_name|param:type*`). 93% token savings vs JSON for full tool schemas. Types: `s`=string, `n`=number, `b`=boolean, `a[type]`=array, `o{keys}`=object. `*` marks required params.
  ```bash
  mcptoon manifest --slim
  # → search|q:s*|n:n
  # → fetch|url:s*
  ```
- **20 unit tests for `slim_toon()`** — Full coverage of all type encodings, required markers, union types, array item types, nested objects. Total tests: 160.
- **README documentation** — `--slim` added to output format table, SLIM mode section with usage examples
- **CLI help text** — `--slim` flag documented in both docstring and `_print_help()`

### Changed
- Bumped version to 0.2.2
- `render()` function now supports `fmt="slim"` in addition to `json`/`toon`/`compact`/`raw`
- Test count updated from 98 to 160

## [0.2.1] — 2026-08-11

### Added
- **`completion` command** — Generate shell auto-completion scripts for bash, zsh, fish, and PowerShell. Auto-completes subcommands, server names (from config), and `--format` values.
  ```bash
  mcptoon completion bash >> ~/.bashrc
  mcptoon completion zsh >> ~/.zshrc
  mcptoon completion fish > ~/.config/fish/completions/mcptoon.fish
  mcptoon completion powershell | Out-File -Append $PROFILE
  ```

## [0.2.0] — 2026-08-11

### Added — Battle-tested features from production use

- **`--stdin` flag** — Read JSON arguments from stdin, bypassing OS command-line length limits (32,767 chars on Windows, ARG_MAX on Unix). Essential for large payloads like page content, code files, or multi-document operations.
  ```bash
  echo '{"content":"...30KB+..."}' | mcptoon call server tool --stdin --toon
  ```
- **`doctor` command** — Self-diagnose: checks Python version, config file, cache directory, server connectivity, and environment. One command to verify your entire mcptoon setup.
  ```bash
  mcptoon doctor
  ```
- **`discover` command** — Server discovery with health check. Lists all configured servers with their transport type, tool count, and connectivity status.
  ```bash
  mcptoon discover
  mcptoon discover exa    # filter by name
  ```
- **`--format` export** — Export tool manifest in agent-specific formats for cross-agent compatibility:
  - `--format openai` → OpenAI function calling definitions
  - `--format openapi` → OpenAPI 3.0 specification
  - `--format mcp` → MCP `tools/list` format
  - `--format json` → Raw JSON
  - `--format human` → Human-readable
  ```bash
  mcptoon manifest --format openai > functions.json
  mcptoon manifest --format openapi > openapi-spec.json
  ```
- **Tool poisoning guard** — Detects prompt injection patterns in MCP tool results (e.g., "ignore previous instructions", hidden `<!-- assistant:` directives, `[INST]` tags). Returns `TOOL_POISONING` error instead of passing injection to the agent. Can be bypassed with `skip_poisoning_check=True` for trusted sources.
- **Fuzzy match "Did you mean?"** — When a tool name is not found, suggests similar tool names using Levenshtein distance. Both in `inspect` and `call` commands.
  ```
  $ mcptoon call exa sarch '{"query":"AI"}'
  Error [METHOD_NOT_FOUND]: Unknown tool: sarch
  Did you mean: search, search_all
  ```
- **`inspect` server-level listing** — `mcptoon inspect <server>` (without tool name) now lists all tools for that server.
- **Enhanced error envelope** — All errors now include `server` and `tool` context fields for better debugging.

### Changed
- Bumped version to 0.2.0
- `--format` flag takes priority over `--toon`/`--json`/`--compact` when specified
- Natural language fallback now recognizes `discover`, `doctor`, `诊断`, `检查` keywords

### Real-world motivation

These features were battle-tested in production with 255+ MCP tools across 23+ servers. Key lessons:
- **`--stdin`**: Real MCP calls with document content or code snippets regularly exceed OS command-line limits. This is the #1 issue users hit.
- **Tool poisoning**: MCP servers return arbitrary content. Without a guard, a malicious or compromised server can inject instructions into the agent's context.
- **`doctor`**: When something doesn't work, users need a single command to check everything — not 5 different commands.
- **Fuzzy match**: Tool names from different MCP servers follow no naming convention. `search` vs `search_all` vs `web_search` — the agent needs help.
- **Export formats**: Users want to use mcptoon with non-CLI agents (OpenAI function calling, OpenAPI-based tools). Export makes this trivial.

## [0.1.0] — 2025-07-27

### Added
- **TOON output format** — Token-Optimized Object Notation, saves 40-60% tokens vs JSON
- **Dual transport support** — stdio (subprocess JSON-RPC) and HTTP (SSE + session)
- **Universal MCP client** — `MCPClient` class with context manager support
- **Connection pool** — `MCPClientPool` for managing multiple MCP servers
- **CLI interface** — `mcptoon` command with `init`, `list`, `manifest`, `inspect`, `call`, `add`, `remove`, `usage`
- **Server configuration** — `~/.mcptoon/config.json` with project-level override (`.mcptoon.json`)
- **Schema cache** — 5-minute TTL to avoid repeated `list_tools` round-trips
- **Usage tracking** — local-only call statistics per server and tool
- **Safety guard** — blocks dangerous operations (delete, remove, drop, etc.) unless `--destructive` flag is passed
- **Custom handlers** — `@register` decorator to bypass MCP for specific servers
- **Windows compatibility** — automatic `.cmd` resolution for npx/node executables
- **Adaptive format** — `MCPTOON_AGENT_TYPE` env var auto-selects output format per agent type
- **Output truncation** — `--max-chars N` and `--full` flags for output length control
- **98 unit tests** — full coverage of output encoding, client parsing, router, and config
- **Zero dependencies** — pure Python 3.10+ standard library
- Apache 2.0 license with NOTICE file for attribution protection

### Known Limitations
- HTTP transport does not support streaming responses (only first SSE event is processed)
- No reconnection logic for dropped stdio connections
- Schema cache is not invalidated when server config changes
