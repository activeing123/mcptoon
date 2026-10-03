---
name: mcptoon
version: 1.2.1
description: "Compress MCP tool discovery with the mcptoon CLI. Trigger when a session has a large MCP tool catalog (many servers/tools), when the user mentions token cost, tool discovery, mcptoon, or asks to list/call MCP tools efficiently. Also route here when the user says the MCP tool list is too large, the agent context window is filling up with tool schemas, or they need the same MCP servers configured across Claude Code, Cursor, Codex, Cline, Windsurf and other agents. Also covers managing an agent's skill catalog with `mcptoon skills` (list / resolve / sync / add / remove, plus a version gate, derived Roo/OpenCode views, and tombstoned removals). Also route here when the user's MCP tools seem to have gone missing: a gateway is mounted in COMPACT exposure by default, so it withholds the upstream tool list from `tools/list` (they stay callable) — explain the preset and switch back with `mcptoon config set exposure full`. Also route here when a tool *result* looks truncated, compressed, or \"lost data\": result compression is on by default, originals come back via `mcptoon_retrieve handle=<id>`, and it turns off with `mcptoon config set compress off`. mcptoon compresses 71,929 tokens of tool schemas to 581 (-99.2%) and serves as an MCP 2026-07-28 stateless-first bridge."
---

# mcptoon — MCP tool-catalog compression

mcptoon is a zero-dependency CLI. If it is not installed yet, one command sets
it up: `pip install mcptoon` (341KB, installs in seconds, nothing else pulled
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
| One screen with every saving added up (tools + skills + cumulative) | `mcptoon report` |
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
| **`compact`** (default) | mcptoon's own tools only — **8** | **~2,607 tokens** |
| `full` (fallback) | + every upstream tool's simplified schema (104 listed) | ~18,686 tokens |

**The upstream tools are not gone under `compact`** — they are withheld from the
*listing*, not from callability. `mcptoon_manifest` names them, `mcptoon_inspect`
shows one schema, and `mcptoon_call` runs it. The gateway's initialize
`instructions` say this too.

### If the user says their tools disappeared

1. Say plainly what happened: **the default preset withholds the tool list to save
   ~16,000 tokens per turn; the tools still work**, and you can reach any of them
   right now via `mcptoon_manifest` → `mcptoon_inspect` → `mcptoon_call`.
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

## Install-time: takeover, and how to undo it

When `mcptoon quickstart` runs it finds the MCP servers already on the machine and
registers the gateway. By default it then **routes those servers through the
gateway** — it removes their direct entries from each agent config and reaches them
via mcptoon instead. This is the step that actually saves tokens: registering the
gateway *alongside* the direct entries saves ~nothing (the host keeps loading every
upstream schema). Measured on 12 servers / 96 tools: alongside ≈ 39,500 tokens per
turn, takeover ≈ 2,607.

**What takeover touches, and what it never touches.** It removes only servers
mcptoon manages — the ones in the user's mcptoon config. A server the user wrote by
hand that mcptoon does not know about is left exactly where it is. Before editing
any config file, mcptoon writes a `<config>.bak` holding the pre-mcptoon original.

**If the user asks "how do I put it back / undo this / get my old setup":**

```bash
mcptoon restore          # undo mcptoon's edits: drop the gateway, return your servers
mcptoon restore --dry    # preview which files would change
mcptoon off              # only removes the gateway entry; servers stay routed
```

`restore` is the true undo: it removes the gateway entry **and** puts back the
servers takeover dropped — the machine looks like it did before mcptoon. It is
surgical, not a file copy: anything the user added to a config after mcptoon's edit
is left exactly where it is. `off` is different: it removes only the gateway entry,
so the servers takeover dropped are **not** brought back. If a user says "I turned
it off and my servers didn't come back", that is expected — run `mcptoon restore`.

A host with an empty tool *panel* after install is the one case where `full`
exposure (above) is right rather than a preference.

## Result compression: on by default, and how to get the original back

Besides shrinking the *catalog* (the schemas), mcptoon shrinks the *results* a
tool returns. **It is on by default (`compress = smart`)** — a fresh install
compresses redundant results with nobody typing a flag. The footer's third line
reads `结果压缩（对话）— 已启用（自动）` when it is on.

**What it compresses, and what it never touches.** The safety gate keeps keys,
structure and scalars and only cuts payload from shapes that are repetitive:
lists of records, search results, directory trees, repeated log lines, many-key
objects. It **leaves alone** a single source file, one long prose answer, an
image/base64 blob, and any lone short value — those pass through byte-for-byte.
A compressed result is *reversible*: the full original is cached and the result
carries `full text: mcptoon_retrieve handle=<id>`; call the `mcptoon_retrieve`
tool with that handle to get it back exactly. Driving the **CLI** instead of an
MCP session? `mcptoon retrieve <handle>` reads the same store and prints the same
original — the handle is redeemable from either side (`mcptoon retrieve --list`
shows what the store holds). Cached originals **no longer expire
on a timer** — the store is bounded by size instead (`MCPTOON_CCR_MAX_BYTES`,
default 200 MB, evicted oldest-first), so an original stays retrievable for the
whole session. `MCPTOON_CCR_TTL` restores timer-based expiry for anyone who wants
it (`0`, the default, means never expire); `MCPTOON_CCR_DIR` moves the store.

**A result you were already given is not sent twice.** Inside one session, if a
tool returns byte-identical content to an earlier call, the body is replaced by a
reference line — `identical to an earlier result in this session — body not
resent` — which still carries the handle, so `mcptoon_retrieve` returns the
original as usual. Measured on a 60-row search result (`cl100k_base`): the first
send is 286 tokens, the repeat is 50. That is a saving on repeats only — a result
that never repeats pays nothing and saves nothing. If a summary was cut and there
is **no** handle, the line says so instead (`original not stored — this view is
all there is`), which means there is genuinely nothing to retrieve: run the tool
again rather than re-sending the handle.

**When a user says a result looks wrong, cut short, or "it lost my data":**

1. First, get the original back — that is the whole answer to "it lost my data":
   `mcptoon_retrieve handle=<id from the result>` returns the untouched payload.
   There is no data loss to repair; the original was never destroyed.
2. If the shape was one that should not have been compressed, pin that one tool
   to pass through: `mcptoon policy set <server> <tool> raw`.
3. If they want result compression off entirely: `mcptoon config set compress off`
   (back on: `mcptoon config set compress smart`).

```bash
mcptoon config set compress off      # no result compression at all
mcptoon config set compress smart    # the default
mcptoon policy set fs read_text_file raw   # keep one tool verbatim
```

**Be honest about the limit.** mcptoon cannot *detect* a bad compression: it
compresses before the model reads the result, so "did this hurt the answer?" is
not something it can observe. What it guarantees is the three layers above —
only safe shapes are compressed, the original is always retrievable, and one
setting turns it off. Do not promise the user automatic detection; offer the
retrieve handle and the off switch.

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
  341KB, installs in seconds). Confirm the upgrade before running it — pinning a
  version here would only go stale, but a bare `--upgrade` should be your call,
  not an automatic one.
- Source: this package is published to PyPI by GitHub Actions from
  `github.com/activeing123/mcptoon`. If an install prompt shows any other
  publisher or index, stop and check before continuing.
- Diagnose: `mcptoon doctor`.
- Undo — two different things, do not conflate them:
  - `pip uninstall mcptoon` removes the **CLI** only. It never edits an agent's MCP
    config, so a routing change made by `sync --takeover` survives it — undo that
    with `mcptoon restore` (or `mcptoon off` for the gateway entry alone).
  - `mcptoon restore` is the true undo of mcptoon's **agent-config edits**: it drops
    the gateway entry and returns the servers `sync --takeover` removed.
- Config location: mcptoon's own config is `~/.mcptoon/config.json` (plus an
  optional per-project `./.mcptoon.json`); remove those files, or drop a single
  server with `mcptoon remove <name>`.
- Claude Code users get one-command setup instead:
  `/plugin marketplace add activeing123/mcptoon` (installs the CLI, wires the
  bridge, and bundles this skill).
