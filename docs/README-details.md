# mcptoon — full details

The README is deliberately short. Everything it used to carry lives here: the three
token bills in full, the benchmark output, the format family, the technical
specification, and the complete command reference.

Method and raw data:
[`tiktoken-benchmarks.md`](tiktoken-benchmarks.md) ·
[`skill-token-benchmarks.md`](skill-token-benchmarks.md)

---

## 1. Token savings, in full

mcptoon's savings are three separate bills. Know which one you are reading before
comparing numbers. All rows are measured configurations (tiktoken `cl100k_base` with
`assets/benchmark_tiktoken.json` for the tool rows, `mcptoon bench` for both), not
scaled estimates.

### Bill 1 — Tool discovery (`manifest`): 99.2% saved by default

This bill comes due **before your agent decides which tool to use**. Native MCP shoves
every tool's full schema into context (50 tools: 14,113 tokens; 255 tools: 71,929
tokens). mcptoon sends only the name index. That is where "114, not 14,113" comes from.

| Tools | Native schema (JSON) | mcptoon name index (default) | Saved |
|-------|-------------------|------------------------|-------:|
| 5 | 1,519 | 11 | −99.3% |
| 50 | 14,113 | **114** | **−99.2%** |
| 255 | 71,929 | **581** | **−99.2%** |

Zero action, on by default: `mcptoon manifest` with no flags is this tier. Want more
per tool? `--slim` (names + parameter types) costs 8,282 tokens (−88.5%); `--full` adds
descriptions on top; `--json` (full schema) is the baseline.

*We measured both rows ourselves, not one number scaled up and down (tiktoken
`cl100k_base`, `assets/benchmark_tiktoken.json`). Your mix will differ:
[compute your own numbers in the browser](https://activeing123.github.io/mcptoon/tools/token-tax/),
30 seconds, nothing uploaded.*

### Bill 2 — Call results (`call`): optional, `--toon` saves ~34%

This bill comes due **after a tool returns its result to your agent**. `mcptoon call`
outputs JSON by default, so the default saves nothing. To shrink results too, add
`--toon` (structured encoding, reversible):

```
Default:  mcptoon call fetch fetch '{"url":"https://example.com"}'   -> JSON (baseline)
Leaner:   mcptoon call fetch fetch '{"url":"https://example.com"}' --toon   -> ~34% saved
```

34% is the measured `toon_save` value in `assets/benchmark_tiktoken.json`
(34.0–34.2%), not a marketing number.

**One line to remember: 99.2% is what you save seeing which tools exist; 34% is what
you can further save on results.**

### Bill 3 — Skill catalog (`skills`): 926,232 to 39 resident + 501 per lookup

The same bill, charged for the other half of the toolbox. An agent that reads its skill
catalog pays for every `SKILL.md` it loads. These are the real numbers from the catalog
on the machine this document was written on: 371 skill files, same tiktoken
`cl100k_base` encoding as above.

| What the agent loads | Tokens | vs loading everything |
|---|---:|---:|
| Every `SKILL.md`, full text | **926,232** | — |
| Every skill's `description` only | 27,292 | −97.1% |
| Every skill *name* only (a names-only index) | 1,413 | −99.85% |
| `mcptoon skills resolve "<task>" --k 5` (returns the 5 that matter) | **501** | **−99.95%** |
| `mcptoon skills manifest` (the pointer that stays resident) | **39** | **−99.996%** |

Read the top row again: **926,232 tokens is 7.07 full 128K context windows.** The
catalog does not fit in the window, which is why agents silently drop skills and then
"forget" a capability you installed months ago. The fix is the same as Bill 1: fetch on
demand, never preload.

```bash
mcptoon skills manifest                      # 39 tokens, stays resident
mcptoon skills resolve "make a PDF" --k 5    # 501 tokens, returns the 5 that matter
```

**Read the two bottom rows as different jobs, because they are.** The **39-token**
`manifest` is a *pointer*: it tells the agent how to ask, and holds no skill names. The
**501-token** `resolve` is the actual work: it returns the five skills that matter for
your request. If you want a skills-as-tool manifest instead (every name resident), that
costs **1,413 tokens**, still −99.85% against loading the catalog. Either way you never
pay the 926,232.

*Measured, not estimated. `mcptoon bench` reproduces both rows from your own catalog,
the same way it reproduces Bill 1's tool rows, in the same table. Full method, caliber
and the count-caliber table:
[`skill-token-benchmarks.md`](skill-token-benchmarks.md). Your catalog differs; the
ratio will not.*

*Scale check: indexing and routing a 1,000-skill catalog takes under half a second
(`index` 0.49s, `list` 0.32s, `resolve` 0.33s, measured on a synthetic 1,000-skill
catalog, real bodies). The 371 above is just the catalog on this machine.*

### Side by side (Bill 1, made visible)

One tool's schema costs **37 tokens** as native JSON but only **2 tokens** as an mcptoon
name-index entry, a 95% cut on a single tool. We measured it with tiktoken
(`cl100k_base`).

**Without mcptoon** (what every MCP client stuffs into context, 37 tokens, measured with
tiktoken):

```json
[{"name":"search_web","description":"Search the web for information",
"inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"Search query"}}}}]
```

**With mcptoon** (2 tokens):

```
search_web
```

**With mcptoon --slim** (6 tokens, names + parameter types):

```
search_web|query:s*
```

---

## 2. Prove it on your machine

These are the numbers people doubt first, so measure them yourself before believing
them. No API key, no MCP server of yours, nothing to configure, and nothing to clone:
`bench` ships in the wheel.

```bash
pip install mcptoon          # bench is built in, nothing to clone
pip install tiktoken         # optional: without it, bench says "estimate", not "measured"
mcptoon bench
```

`mcptoon bench --roots <dir>` points it at any catalog. The tool rows are *your* cached
schemas, so they will differ; the skill rows below are one root (`~/.claude/skills`).

It measures **both halves in one table** (tool schemas against the name index, and every
`SKILL.md` against the resident pointer and one lookup), so you can see which number is
which instead of taking a headline on faith. On the machine this document was written
on:

```text
  half          what the agent loads                        tokens   vs native
  ----------------------------------------------------------------------------
  MCP tools (1109) native: every full schema                  139,863           -
                manifest (name index)                        5,406       96.1%
                manifest --slim                             16,396       88.3%

  Agent skills (371) native: every SKILL.md, full text          926,232           -
                skills manifest (pointer)                       39      100.0%
                skills resolve --k 5 (one lookup)              501       99.9%
```

*(The footer, meaning the query used, the caliber, and the 128K-window count, is
elided. `query` matters: the resolve row is measured against `make a PDF`.)*

**Watch what it replaces.** Ask an agent to find the right skill without mcptoon and it
has no index. It reads `SKILL.md` files until it finds one. On this catalog the whole
set is 926,232 tokens: it does not fit in a 128K window, so it gets truncated, and the
skill that falls off is the one you wanted. With mcptoon the same question costs **501
tokens**, and `mcptoon bench` points at your own folders to check that yourself.

Two calibers in one table, on purpose: the tool rows are *your* cached schemas, while
Bill 1 quotes the fixed 255-tool benchmark so that number cannot drift. The skill rows
count one level deep with `_index` excluded, and de-duplicate roots by real path, so a
machine whose agent folders are junctions onto one catalog is not counted four times.

### What `mcptoon demo` actually prints

No API key, no MCP server of yours, nothing to configure: it boots the official
"everything" reference server, calls one tool, and shows the token math on your screen.
This is that output, verbatim (Windows, Python 3.12). Only the ASCII banner and the
closing star-ask are cut.

```text
$ mcptoon demo --quick

  Starting demo server...
  ✓ Demo server ready

  📊  SAME data, 19% fewer tokens:
              21  ->          17   (SLIM)

  Format         Tokens    Savings
  ────────── ────────── ──────────
  JSON               21          -
  TOON               17        19%
  SLIM               17        19%

  Official benchmark: 255 tools, 50 servers, tiktoken cl100k_base:

  Format           Tokens    Savings
  ──────────── ────────── ──────────
  JSON             71,929          -
  TOON             47,438        34%
  SLIM              8,282      88.5%
  Compact             581      99.2%

  Now you can:
  ✓ connect every agent with ONE config   ->  mcptoon sync
  ✓ expose ALL servers as ONE stdio server ->  mcptoon serve
  ✓ never paste tool schemas again         ->  mcptoon manifest --slim

  Schemas are fetched, not injected. You pay for a listing, not for every turn.
  255 tools listed once: 581 tokens (71,929 -> 581, -99.2%, measured)
```

Column padding follows your terminal width; the numbers do not. The first table is one
live tool call measured on your machine; the second is the repo's committed 255-tool
benchmark (`tiktoken-benchmarks.md`), reproduced identically on every run.

No Node on the machine? `mcptoon demo-server` is the same proof with nothing to
download: an MCP server of 11 standard-library tools, no network, no API key.

---

## 3. Format family

Discovery and call results each have a set of formats. All are optional, and the default
is already the leanest tier.

**manifest (discovery): compact by default, upgrade only if you want more**

| Tier | Output | vs native schema | Origin |
|---|---|---|---|
| **compact (default)** | names only `search_web` | **99.2% smaller** | common design |
| **slim** | name + param types `search_web\|query:s*` | 88.5% smaller | **mcptoon original** |
| **full** | full schema with params | baseline | native MCP |

**Why compact by default, not full?** Deciding which tool to use only needs names (581
tokens for 255 tools). Parameter details matter at call time, fetched on demand via
`inspect` or `manifest --full`. Defaulting to full schemas hands the 99.2% right back.

**The recommended loop.** Compact names are a *catalog*, not a *calling contract*.
Measured on 41 live tools (full-schema gold standard, one inference model per
condition): an agent that guesses arguments from names alone lands **4/41 ≈ 10%** valid
calls, and the killers are non-guessable names like `account` and `pageId`. An agent
that runs `inspect <server> <tool>` once for the 2 to 3 tools a turn actually uses hits
**41/41 ≈ 100%**, identical to injecting every schema. A turn touches a handful of
tools, so a few on-demand `inspect` calls stay far below the cost of a full-schema dump:
you keep ~99% of the token savings *and* full call accuracy. The rule for agents:
**use `manifest` to choose, `inspect` before you call.**

**call (results): JSON by default, --toon to save**

| Tier | Output | vs JSON | Origin |
|---|---|---|---|
| **(default)** | JSON | baseline | common |
| **--toon** | structured encoding (reversible) | ~34% smaller | open TOON standard |
| **--mcptoon** | legacy pipe format | — | mcptoon original (legacy) |

**Where these formats come from**

- **compact**: a name list. Any tool manager can do it; nothing proprietary.
- **slim** (`name|param:type*` signatures): **an mcptoon original**, implemented in
  `output.py` (`slim_toon`, Apache 2.0); noted in NOTICE.
- **full**: full JSON Schema, what MCP speaks natively.
- **toon** (result encoding): integration of the open **TOON standard**
  ([toon-format/toon](https://github.com/toon-format/toon) v4.1, MIT), vendored from
  python-toon and credited in NOTICE. Not our invention, and we don't claim it.

---

## 4. Technical specification

Everything here is checkable against `mcptoon --version` and the files mcptoon reads.
Both halves of the toolbox share one engine, one config and one index format.

| | MCP tools | Agent skills |
|---|---|---|
| **Unit** | one tool = one JSON Schema | one skill = one `SKILL.md` (YAML frontmatter + body) |
| **Source of truth** | `~/.mcptoon/config.json` (servers) | one skills root (default `~/.claude/skills`, `~/.agents/skills`, `~/.codex/skills`, `~/.cursor/skills`) |
| **Kept out of context by** | names-only manifest (581 tokens @ 255 tools) | BM25 index + a 39-token pointer (501 tokens per lookup) |
| **Discovery** | `mcptoon manifest` · `inspect` · `search` | `mcptoon skills resolve` · `route` |
| **Distribution** | `mcptoon sync` (native JSON per agent) | `mcptoon skills sync` (links per agent) |
| **Add / remove** | `install` · `add` · `remove` | `skills add` · `skills remove --tombstone` |
| **Health** | `mcptoon health` | `mcptoon skills stats` |

**Runtime.** Python ≥ 3.10 (CI: 3.10–3.13 × Linux, Windows, macOS). 28 modules, 20,170
lines of Python, a **227KB** wheel, **zero third-party dependencies**, standard library
only, enforced in CI by `scripts/check_zero_deps.py`. No daemon, no listening port, no
telemetry, no stored credentials.

**Tool formats.** `compact` (names only, default) · `slim` (`name|param:type*`, an
mcptoon original) · `full` (native JSON Schema) · `toon` (the open TOON standard,
reversible). All of them live in the output layer. The wire protocol is always standard
JSON-RPC, so servers never see a non-standard byte.

**Skill internals.**

- **Index** — `~/.mcptoon/skills-index.json` (`version: 1`), built by
  `mcptoon skills index`, which is **required** before `list` / `resolve` / `route` /
  `stats` (without it: `no skills index yet. Run: mcptoon skills index`).
- **Retrieval** — BM25 over each skill's slug + `description` + trigger words, merged
  with every alias that points at it, so an alias name still reaches the canonical
  entry. Offline: no LLM, no network. `--k` defaults to **5**.
- **Pointer** — `mcptoon skills manifest` prints one line and contains **no skill
  names**; it is the instruction that tells the agent how to ask, not an index.
- **Sync** — views are **links** (a junction on Windows, no admin needed). A real
  directory where a link belongs is **archived, never deleted**; a view that already
  points at the source is left alone; `remove` **moves** the skill into a dated archive,
  so a wrong removal is an `mv` back, not a re-clone.
- **Lifecycle** — `--version-gate` refuses content that changed while `version` did not;
  `--derived roo|opencode|all` regenerates the flat `.md` views some agents read;
  `--archive DIR` chooses where drift is parked; `remove --tombstone` commits the
  removal (path-scoped) so a two-way git sync cannot revive it.

**Environment overrides** (used by the tests and by anyone running more than one
catalog): `MCPTOON_SKILLS_ROOTS`, `MCPTOON_SKILLS_VIEWS`, `MCPTOON_SKILLS_INDEX`,
`MCPTOON_SKILLS_USAGE`, `MCPTOON_SKILLS_ENDPOINT`, `MCPTOON_SKILLS_MODEL`,
`MCPTOON_SKILLS_LEDGER`, `MCPTOON_SKILLS_DERIVED`, `MCPTOON_CONFIG_FILE`,
`MCPTOON_AGENT_TYPE`.

**Reproduce the numbers.** `mcptoon bench`, both halves in one table, shipped in the
wheel. From a clone, `scripts/bench_tokens.py` and `scripts/bench_skills.py` are the
repository-side equivalents (tiktoken-only, exact). Method and caliber:
[`tiktoken-benchmarks.md`](tiktoken-benchmarks.md) and
[`skill-token-benchmarks.md`](skill-token-benchmarks.md).

---

## 5. Command reference

```bash
mcptoon quickstart              # one-shot start (discover + configure + list tools)
mcptoon discover                # scan this machine for MCP servers (--write to keep, --health to probe)
mcptoon init                    # create a sample config (--auto to discover and fill it)
mcptoon list                    # show configured servers
mcptoon manifest                # all tool names (compact by default; 255 tools = 581 tokens)
mcptoon manifest --slim         # names + param types (8,282 vs 71,929 = −88.5%)
mcptoon manifest --compact      # names only (581 vs 71,929 = −99.2%, measured)
mcptoon inspect <server> <tool> # inspect one tool's schema
mcptoon search <query>          # search tools across servers
mcptoon call <server> <tool> '{"args":"here"}'   # call a tool
mcptoon call --auto <tool> '{"args":"here"}'     # auto-find the server
mcptoon call <server> <tool> --stdin             # read large args from stdin
mcptoon add <name> --stdio|--http <cmd|url>     # add any MCP server
mcptoon remove <name>           # remove a server
mcptoon install <name> --npm|--pip|--url <pkg>  # install + auto-generate handler
mcptoon install --list          # list installed
mcptoon install --remove <name> # uninstall
mcptoon sync                    # sync native config to every detected agent
mcptoon health                  # health-check every MCP server (--json exits 1 if any is dead)
mcptoon policy                  # per-tool compression policy (raw / toon / slim)
mcptoon skills index [ROOT ...] # build the on-disk index (required before list/resolve)
mcptoon skills list             # list the skill catalog (--usage adds hit counts)
mcptoon skills resolve "<task>" # BM25 shortlist of skills (offline, no LLM)
mcptoon skills route "<task>"   # shortlist, then let an LLM pick (--model, --endpoint)
mcptoon skills stats            # catalog health (dupes, aliases, missing description)
mcptoon skills manifest         # the one-line resident pointer (39 tokens)
mcptoon skills sync <src>       # distribute a skill catalog to every agent's folder
mcptoon skills add|remove <name> # create a skill in the source / retire it to the archive
mcptoon bench                   # prove the savings on this machine (tools + skills, one table)
mcptoon plugin install <dir>    # install an Agent Plugins 1.0.0 plugin
mcptoon serve                   # run as an MCP server (stdio/HTTP) — MCP 2026-07-28: stateless-first, server/discover, cacheable list results
mcptoon demo                    # one command, live demo on your machine
mcptoon doctor                  # self-check: Python, config, connectivity
mcptoon usage                   # local call statistics
mcptoon completion ps           # shell completion (bash/zsh/fish/powershell)
```

---

## 6. Do custom formats break MCP compatibility? No, for three reasons

"Proprietary format = compatibility bomb" is a fair worry. It does not apply here.

**1 · The protocol layer is always standard JSON-RPC; formats live only in the
presentation layer.**
mcptoon speaks standard MCP to servers (initialize / tools/list / tools/call, and since
the 2026-07-28 GA bridge, `server/discover` and stateless requests too; the initialize
handshake remains for legacy clients). compact/slim/toon only affect the "mcptoon to
agent" output rendering, not a single byte toward the server. Servers always see
standard JSON; they don't even know these formats exist.

**2 · --toon isn't proprietary; it's an open standard.**
TOON (Token-Oriented Object Notation) is an external open standard
([toon-format/toon](https://github.com/toon-format/toon) v4.1, MIT, official TypeScript
reference implementation). We integrate python-toon (MIT);
`tests/test_toon_cross_validate.py` verifies `decode(encode(x)) == x` case by case.

**3 · There's a fallback; worst case you fall back to JSON.**
If `--toon` decoding fails it falls back to JSON automatically (`--fallback-json`); and
call results are JSON by default anyway, so `--toon` is optional. Want the full schema
back? One `--full` is native MCP. No lock-in.

**In one line: zero protocol changes, formats live in the output layer, worst case falls
back to JSON.** The feared "server can't understand the custom format" cannot happen.
Servers always hear standard JSON-RPC.
