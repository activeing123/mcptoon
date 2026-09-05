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

## Ecosystem channel ledger

What mcptoon has earned externally, and the standing obligation each one creates:

| Channel | Standing | Our obligation |
|---|---|---|
| numtide/llm-agents.nix | S-tier: packaged; bot auto-follows since init PR #7839 (zimbatm) | Release discipline above; after each release, confirm the bot PR merged |
| PyPI | every release | publish workflow green before announcing |
| MCP Registry (`server.json`) | listed | keep `server.json` in sync when commands/flags change |
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
- Competitive landscape and positioning → [competitive-intel-mcp-manager-tools.md](competitive-intel-mcp-manager-tools.md)
- Release history → [CHANGELOG.md](CHANGELOG.md)
