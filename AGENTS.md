# AGENTS.md — rules for AI agents working on mcptoon

Any AI agent (Codex, Claude Code, Cursor, DSH, ...) writing code, docs, or cutting
releases in this repo follows the rules on this page. They exist because mcptoon is
now carried by external automation: numtide/llm-agents.nix packages this project and
an official bot auto-bumps it on every PyPI release. A careless release breaks that
channel; these rules keep it clean. Human contributors: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Hard rules

1. **Zero dependencies, always.** The `dependencies` field in `pyproject.toml` stays
   empty. Standard library only. CI enforces this via `scripts/check_zero_deps.py` —
   treat a red zero-deps job as a broken build, not a suggestion.
2. **Tests gate every change.** New behavior ships with tests in `tests/`. Run
   `python -m pytest tests/` and paste the real green output before claiming done.
3. **Windows is a first-class target.** Anything touching paths, subprocess, or npx
   must work on Windows; the CI matrix runs it on every PR.
4. **Conventional Commits** for every commit (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).

## Release discipline

A release is complete only when all five land together:

1. version bumped in `pyproject.toml`
2. `CHANGELOG.md` entry written for the new version
3. full test suite green
4. git tag `vX.Y.Z` pushed
5. PyPI publish green (`.github/workflows/publish.yml`)

The numtide bot turns PyPI releases into Nix bump PRs automatically. A version that
exists on main but not on PyPI (or the reverse) leaves a broken bump in that channel.
Breaking changes must land as deprecation warnings one minor version before removal.

### Batch the release, don't ship every finding (added 2026-10-02)

**A release is the unit of a finished topic, not of a single fix.** Ship one version per
topic once the topic is exhausted — not one version per discovery. Measured cost of the
alternative: **six releases on 2026-10-02** (0.8.6 → 0.8.11), each one a full ritual
(version in 5 places, 3 claim surfaces, CHANGELOG, tag, GitHub Release, 3 workflow runs,
tap dispatch, drift gate, ledger in 2 places) — roughly an hour of mechanical work per
version, and most of it repeated. Worse, every release resets the numtide grace window,
so the bot that packages us stayed pinned at 0.8.7 all day and could never catch up.

Rules that follow:

- **Finish the attack surface before you bump.** If you are probing one module (or one
  class of defect), keep finding and fixing until the probe reports nothing, *then*
  release once. 0.8.10 and 0.8.11 were both products of the same adversarial technique on
  adjacent code and could have shipped together.
- **Same topic, same version.** A fix and the test that pins it and the docstring it
  corrects belong to one release. Splitting them across versions is what "one finding,
  one release" looks like from the outside.
- **Cap the cadence at one release per day** unless a shipped defect is actively
  corrupting data or blocking installs. If a second release seems necessary the same day,
  the honest question is whether the first one should have waited.
- **Do not batch unrelated work into one version to satisfy this rule.** The rule is
  "finish the topic", not "hoard changes". A release with two unrelated themes is harder
  to reason about than two releases with one theme each.

### Step 6 (added 2026-10-01) — run the drift gate, don't eyeball the channels

```powershell
python scripts/release_sync.py --apply     # from the ops zone, not this repo
```

One command checks **every** distribution channel against PyPI as the baseline,
auto-repairs the Homebrew tap if it drifted, rewrites the channel ledger, and records
an op entry. **Exit code 2 means a channel that is supposed to be automatic has
drifted — fix it before calling the release done.** Exit 0 may still print 🟡 advisory
items (Chocolatey / winget / ClawHub): those need a human to build an artifact, so they
never block and never go quiet.

`scripts/release_sync.py` lives in the maintainer's ops zone (`mcptoon/scripts/`), not in
this repo — the public tree deliberately stays free of machine-local paths.

This step exists because of a measured failure, not theory: on 2026-10-01 the Homebrew
tap was found **four releases behind** (0.8.1 while PyPI was at 0.8.5, from 09-25) with
**zero errors anywhere**. The tap is a hand-written formula pinned to a `sha256`; it is
in no workflow and no bot watches it, so the release ritual had nothing to catch it.
It is now self-healing — `activeing123/homebrew-mcptoon` runs `.github/workflows/auto-bump.yml`
daily — but step 6 is what tells *you*, immediately, if that automation ever breaks.

Deliberate design limits, so the gate does not turn into noise:
- **Blocking** = only channels that are supposed to move automatically
  (MCP Registry / numtide / Homebrew / gemini manifest / GitHub Release), each with a
  grace window sized to its bot (2h tap, 24h registry, 72h numtide).
- **Advisory** = channels needing a human-built artifact. A gate that cries wolf daily
  gets ignored, and then the real signal dies with it.
- **ClawHub's version is a different numbering system** (skill `1.0.8` vs CLI `0.8.5`).
  It is displayed, never compared.
- Proving a gate still fires is part of using it:
  `release_sync.py --check --simulate-drift "Homebrew=0.8.1"` must exit 2.

Details that bit us during v0.7.4 (2026-09-05), so they are now part of the ritual:

- **The version lives in five places.** `pyproject.toml`, `server.json`
  (twice: top level and `packages[]`), the hardcoded `__version__` in
  `src/mcptoon/__init__.py`, and `gemini-extension.json`. 0.7.6 shipped with
  `mcptoon --version` printing 0.7.5 because the last one was missed — caught
  only by the post-release smoke test. `tests/test_registry_sync.py` pins the
  registry set and `tests/test_gemini_manifest.py` pins the extension; update
  every one on every bump and run both suites green.
- **The publish workflows used to race each other.** `publish.yml` and
  `publish-mcp.yml` start on the same release event; the registry run
  validated the PyPI version while the wheel was still uploading and failed
  with 400. This happened on both 0.7.6 and 0.7.7. Root cause fixed in
  `publish-mcp.yml`: a wait step now polls PyPI's JSON API for the released
  version (up to 5 minutes) before pushing the registry record. If the wait
  step ever times out, retry with `gh workflow run publish-mcp.yml -f reason=...`.
- **Pushing a tag does not publish.** `publish.yml` triggers on `release: [published]`,
  so a GitHub Release must be created (`gh release create vX.Y.Z --notes-file …`).
- **Verify against the real index.** This machine's pip points at a mirror that lags —
  and its global `ALL_PROXY=socks5://` breaks fresh venvs (no PySocks). Confirm a fresh
  release with a clean venv, proxy vars cleared:
  `python -m venv .scratch/check && .scratch/check/Scripts/python -m pip install --no-cache-dir --index-url https://pypi.org/simple/ mcptoon`,
  then run `mcptoon --version` from that venv and compare with the tag.
- **Run the lint job locally** (`python -m ruff check src/mcptoon/ tests/`, ruff 0.15.20)
  before pushing — unpushed commits never see CI, and one UP037 turned the release red.
- **Update the `Tests-<n> passed` badges** in `README.md` and `README.zh-CN.md` (and the
  matching comment in their contributor sections) to the suite total of the release.
- **The MCP Registry record used to be pushed by hand.** 0.7.0 and 0.7.2 were published
  from a laptop; 0.7.3–0.7.5 never reached it, and `server.json`'s package version had
  drifted a release behind its own top-level version. `publish-mcp.yml` now publishes on
  every release, and `tests/test_registry_sync.py` fails CI if the versions, the
  `mcp-name:` marker in the PyPI README, or the workflow drift apart. Do not remove that
  marker when rewriting the README — it is invisible when rendered and load-bearing.

## Ecosystem channel ledger

What mcptoon has earned externally, and the standing obligation each one creates:

| Channel | Standing | Our obligation |
|---|---|---|
| numtide/llm-agents.nix | S-tier: packaged; bot auto-follows since init PR #7839 (zimbatm) | Release discipline above; after each release, confirm the bot PR merged |
| PyPI | every release | publish workflow green before announcing |
| MCP Registry (`server.json`) | listed; published automatically by `.github/workflows/publish-mcp.yml` on every release (OIDC) | keep `server.json` in sync — CI enforces the versions, the `mcp-name:` README marker and the workflow itself via `tests/test_registry_sync.py` |
| **Homebrew tap (`activeing123/homebrew-mcptoon`)** | personal tap, **not** Homebrew core (core rejects pip-installable Python CLIs) | **listed here on purpose** — it is a hand-written formula pinned to a `sha256`, invisible to every workflow and bot. It drifted four releases (0.8.1 vs PyPI 0.8.5) with zero errors until 2026-10-01. Now self-healing via that repo's daily `auto-bump.yml`; step 6 above is what reports it if that automation ever breaks. Never publish a release without checking it. |
| Chocolatey community package | listed and **approved at 0.8.5** (2026-10-02 verified: OData `Published=2026-09-30T12:07:12Z`, package page `Approved`) | manual: build the nupkg, `PUT` it, wait for moderation. **There is no automation** — `release_sync.py` lists this one as advisory, so a new release needs a human to push the package. Advisory-only in the drift gate |
| `microsoft/winget-pkgs` | PR #443014 open (0.8.3), awaiting a community moderator (validation pipeline already passed) | manual: needs a self-contained zip asset per version. Advisory-only in the drift gate. Say "PR submitted", never "on winget" until merged. **Decided 2026-10-02:** merge 0.8.3 first to claim the version number (version directories are immutable in winget), then file a fresh 0.8.5 manifest afterwards. Do not reopen the PR to change its version, and do not chase the moderator. |
| ClawHub skill listing | listed; its tag number is ClawHub's own counter (**not** the CLI version, **not** the SKILL.md frontmatter version) | manual republish when SKILL.md changes. Never compare its number to any other version line |
| apify/mcpc client comparison | listed in comparison table | none — leave the table alone |
| awesome-mcp-clients PR #283 | pending | do not nag maintainers until ≥500 stars |
| striki18/benchmark | third-party benchmark harness running mcptoon | external repo — read for intel, do not touch |

Auto-crawler listings (topic indexes, news aggregators) are noise: never report them
as traction. When reporting ecosystem progress, always pair listing counts with the
real adoption number — PyPI downloads (https://pypistats.org/api/packages/mcptoon).

## Where the older rules live (pointers — single source of truth, do not duplicate)

- Dev workflow, code style, project structure → [CONTRIBUTING.md](CONTRIBUTING.md)
- Architecture, the three core commands, token benchmarks → [DEVELOPERS.md](DEVELOPERS.md)
- What to build next and why → [ROADMAP.md](ROADMAP.md)
- What makes the CLI feel considered (messages, numbers, first-run paths) → [docs/experience-checklist.md](docs/experience-checklist.md)
- Marketing surface (landing pages + README) mission, readers, block duties, gates → [docs/homepage-framework.md](docs/homepage-framework.md)
- Competitive landscape and positioning → [competitive-intel-mcp-manager-tools.md](competitive-intel-mcp-manager-tools.md)
- Release history → [CHANGELOG.md](CHANGELOG.md)
