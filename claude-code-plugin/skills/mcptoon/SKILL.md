---
name: mcptoon
version: 1.1.0
description: Compress MCP tool discovery with the mcptoon CLI. Trigger when a session has a large MCP tool catalog (many servers/tools), when the user mentions token cost, tool discovery, mcptoon, or asks to list/call MCP tools efficiently. Also route here when the user says the MCP tool list is too large, the agent context window is filling up with tool schemas, or they need the same MCP servers configured across Claude Code, Cursor, Codex, Cline, Windsurf and other agents. Also covers managing an agent's skill catalog with `mcptoon skills` (list / resolve / sync / add / remove, plus a version gate, derived Roo/OpenCode views, and tombstoned removals). Also route here when the user's MCP tools seem to have gone missing: a gateway is mounted in COMPACT exposure by default, so it withholds the upstream tool list from `tools/list` (they stay callable) — explain the preset and switch back with `mcptoon config set exposure full`. mcptoon compresses 71,929 tokens of tool schemas to 581 (-99.2%) and serves as an MCP 2026-07-28 stateless-first bridge.
---

# mcptoon — MCP tool-catalog compression

mcptoon is a zero-dependency CLI. If it is not installed yet, one command sets
it up: `pip install mcptoon` (227KB, installs in seconds, nothing else pulled
in). It gives you a compressed view of the user's MCP tools and calls them
back.

## When to use what

| Situation | Command |
|---|---|
| User asks "what tools do I have" / you need the tool catalog | `mcptoon manifest` (compact names only — ~2.2 tokens/tool) |
| You need one tool's real parameter schema before calling | `mcptoon inspect <server> <tool>` |
| Find a tool by capability | `mcptoon search <query>` |
| Call a tool | `mcptoon call <server> <tool> '{"arg":"value"}'` |
| You don't know which server owns the tool | `mcptoon call --auto <tool> '{...}'` |
| Huge JSON argument | `mcptoon call <server> <tool> --stdin` |
| Tool returns images/base64 that must never be compressed | `mcptoon policy set <server> <tool> raw` (one-time; applies to every later call) |
| Prove the token savings on this machine (tools + skills, one table) | `mcptoon bench` (`--roots DIR` for any catalog; `--json` for scripts) |
| Diagnose connectivity/config | `mcptoon doctor` |

## Managing a skill catalog (mcptoon as the skill center)

Skills and MCP servers are the same shape — one source, many agent views — so
`mcptoon skills` manages both halves of a session's toolbox.

| Situation | Command |
|---|---|
| See what skills exist | `mcptoon skills list` (`--usage` adds per-skill hit counts) |
| Find the right skill for a task | `mcptoon skills resolve "<task>"` (offline, instant, no LLM) |
| Distribute one source to every agent's skill folder | `mcptoon skills sync [SRC] [VIEW ...]` (`--dry` to preview, `--copy` for real dirs) |
| Refuse "edited but forgot to bump the version" | `mcptoon skills sync --version-gate` |
| Regenerate the flat `.md` views (Roo / OpenCode) | `mcptoon skills sync --derived roo\|opencode\|all` |
| Create / retire a skill | `mcptoon skills add <name> --desc "…"` / `mcptoon skills remove <name>` |
| Retire a skill so a git sync cannot revive it | `mcptoon skills remove <name> --tombstone` |
| Park drift/removals in a chosen graveyard | add `--archive DIR` to `sync` or `remove` |

Sync views are **links** by default (a junction on Windows, no admin needed), so
one edit at the source is live everywhere and there is no second copy to drift.
Two safety rules hold: a real directory where a link belongs is **archived, never
deleted**, and a view that is *itself* a whole-directory link to the source is
left completely alone. `remove` **moves** the skill to a dated archive — a wrong
removal is a `mv` back, not a re-clone. `--usage` counts only skills mcptoon
routed; a skill an agent loaded directly is invisible there, and the output says
so rather than implying full coverage.

### When another manager already runs the catalog

mcptoon is designed to take over from an incumbent sync script **without a
cutover**, by matching it byte for byte first:

- `--version-gate` reads the **same** ledger the incumbent wrote
  (`skill_versions.json`; override with `MCPTOON_SKILLS_LEDGER`), so both reach
  the same verdict on the same bytes. A skill whose content moved while its
  frontmatter `version` did not is blocked with a printed reason; `--force` lets
  it through and rebaselines. An unversioned skill is warned about, not blocked.
- `--derived` output is byte-identical to the incumbent's, **including line
  endings** (a text-mode write turns the source's LF into CRLF on Windows), so a
  derived view does not become a diff the next sync has to fight.
- `--tombstone` commits a removal with a **path-scoped** `git add`. It will never
  run a whole-repo `git add -A`: a real skill repo has hundreds of unrelated edits
  in flight, and sweeping them into a "tombstone" commits another session's work.

Point mcptoon at sandbox views first with `MCPTOON_SKILLS_VIEWS` and run `--dry`
before any real sync. Do not run two managers against one view directory: during
a hand-over, one is the writer and the other is read-only.

## Tool exposure: the default, and how to switch back

When mcptoon is mounted as a gateway, it decides how much of the tool catalog it
hands the host. **The default is `compact` — the cheapest one — and it is
deliberate.** Know this before you tell a user something is broken:

| Preset | What `tools/list` returns | Cost per turn (12 servers / 96 tools) |
|---|---|---|
| **`compact`** (default) | mcptoon's own tools only — **6** | **~2,138 tokens** |
| `full` (fallback) | + every upstream tool's simplified schema (102 listed) | ~18,217 tokens |

**The upstream tools are not gone under `compact`** — they are withheld from the
*listing*, not from callability. `mcptoon_manifest` names them, `mcptoon_inspect`
shows one schema, and `mcptoon_call` runs it. The gateway's initialize
`instructions` say this too.

### If the user says their tools disappeared

1. Say plainly what happened: **the default preset withholds the tool list to save
   ~16,000 tokens per turn; the tools still work**, and you can reach any of them
   right now via `mcptoon_manifest` → `mcptoon_call`.
2. Prove it on the spot — do not argue from documentation. Run
   `mcptoon manifest` and show the user their real tool names.
3. Offer the second preset, and name the tradeoff honestly: it lists everything
   again (so a host's tool panel is populated, and a model that will not ask for
   the manifest sees the tools), at ~16,000 more tokens per turn.

```bash
mcptoon config set exposure full     # second preset; takes effect on next connection
mcptoon config set exposure compact  # back to the default
```

Do **not** edit the agent's MCP config to switch presets — it is one setting, in
one place, and `mcptoon off` still removes the gateway entirely. If the user's
host has an empty tool *panel* (a UI that reads `tools/list` to draw a picker),
that is the one case where `full` is the right answer rather than a preference.

## Making mcptoon visible in a session

`mcptoon serve` returns an `instructions` field from the MCP initialize
handshake, so a connected client learns what mcptoon is without anyone editing
a system prompt, and can close a turn with one honest savings line. The figures
come from the `mcptoon_usage` tool, never from the model's estimate. Users who
find the line noisy turn it off once:

```bash
mcptoon config set footer off   # persists; the next connection omits it entirely
```

Note this is advisory — it works only when the client honours `instructions`,
and only when `mcptoon serve` is actually registered with that agent.

## Rules

1. **Prefer `mcptoon manifest` over reading raw MCP tool listings** — same
   information, ~99% fewer tokens on large catalogs (255 tools: 71,929 → 581).
2. `manifest` output is a **name index**, not schemas. Keep it in context;
   fetch the one schema you need with `inspect`, then call.
3. Tool names in `call` are `server_tool` (namespaced). `--auto` resolves
   the server for you when the name is unambiguous.
4. Never claim savings percentages you did not observe; if you quote numbers,
   use the ones printed by the command itself — `mcptoon bench` prints them for
   this machine. It needs `tiktoken` for the exact figures; without it the table
   is labelled an estimate, so do not report those as measured.
5. If a Claude Code plugin install wired the `mcptoon serve` bridge via
   `.mcp.json`, tool discovery is already compressed for the host agent; use
   the CLI commands above in terminal contexts or when the bridge is not
   connected.

## Setup

- Install/upgrade: `pip install --upgrade mcptoon` (zero-dependency wheel,
  227KB, installs in seconds). Confirm the upgrade before running it — pinning a
  version here would only go stale, but a bare `--upgrade` should be your call,
  not an automatic one.
- Source: this package is published to PyPI by GitHub Actions from
  `github.com/activeing123/mcptoon`. If an install prompt shows any other
  publisher or index, stop and check before continuing.
- Diagnose: `mcptoon doctor`.
- Undo: `pip uninstall mcptoon` removes the CLI. Its config lives in
  `~/.mcptoon/config.json` (plus an optional per-project `./.mcptoon.json`); remove
  those files, or drop a single server with `mcptoon remove <name>`. Nothing outside
  them is touched.
- Claude Code users get one-command setup instead:
  `/plugin marketplace add activeing123/mcptoon` (installs the CLI, wires the
  bridge, and bundles this skill).
