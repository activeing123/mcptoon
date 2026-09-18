# Skill-catalog token benchmarks — method

How the "Bill 3" numbers in the READMEs are produced, and exactly which number means
what. Tools-side numbers have their own method in
[`tiktoken-benchmarks.md`](tiktoken-benchmarks.md); this file is the skill-side twin.

Everything here is reproducible with one command against your own catalog.

## Why this file exists

The skill side produces a bigger headline than the tool side (926,232 → 39 reads as a
24,000× cut) because **the two sides are not the same kind of artifact**, and a headline
that does not say so is easy to misread — or to disbelieve. So this file states the
caliber, lists every row, and names which rows are comparable.

## Reproduce it

```bash
pip install tiktoken          # the measurement tool; NOT a runtime dependency
python scripts/bench_skills.py --roots ~/.claude/skills
```

`tiktoken` is deliberately a third-party install: it measures, it does not ship. mcptoon
itself stays zero-dependency (`scripts/check_zero_deps.py` enforces it).

> **Flag order matters.** `--roots` takes one or more paths, so it swallows anything
> that follows. Put `-k 5` *before* `--roots`:
> `python scripts/bench_skills.py -k 5 --roots ~/.claude/skills`.

## What is counted

| Row | What it is | Comparable to |
|---|---|---|
| **full text** | every `SKILL.md`, entire file, concatenated | the raw cost of loading the catalog |
| **descriptions only** | each skill's frontmatter `description` | a catalog listing that shows one line per skill |
| **names only** | just the skill slugs, space-joined | a names-only manifest, the way `mcptoon manifest` treats tools |
| **`skills manifest`** | the resident pointer (see below) | the pointer, **not** an index |
| **`skills resolve --k 5`** | one BM25 lookup, JSON result | the actual per-request cost |

### The two rows that are not comparable

This is the trap the caliber note exists to prevent:

- **`mcptoon skills manifest` = 39 tokens is a POINTER.** Its entire text is:
  `Skills: \`mcptoon skills resolve "<request>" --k 5\` returns the best-matching skills as JSON. Read only those SKILL.md files. Never load the whole catalog.`
  It contains **zero skill names** (measured: 1 of 379 slugs appears, as part of the word
  "skills"). Comparing 926,232 to 39 is comparing a catalog to an instruction on how to
  query it.
- **`mcptoon skills resolve --k 5` = 501 tokens is the real per-request cost.** This is
  the honest apples-to-apples line: loading everything vs. loading the five that matter.

If you want the skills-side number that *is* structurally comparable to the tool side's
name index, use **names only = 1,413 tokens** (every slug resident). Still −99.85%.

## The caliber (this machine, 2026-09-18)

Measured with `tiktoken` `cl100k_base`, source `~/.claude/skills`, **371 skills**
(one `SKILL.md` per top-level directory; the `_index` meta-directory is excluded, which
is why the count is 371 and not 372).

| What the agent loads | Tokens | vs full |
|---|---:|---:|
| Every `SKILL.md`, full text | **926,232** | — |
| Every skill description only | 27,292 | −97.05% |
| Every skill name only | 1,413 | −99.85% |
| `mcptoon skills manifest` (pointer) | **39** | −99.996% |
| `mcptoon skills resolve --k 5` (one lookup) | **501** | −99.946% |

The full catalog is **7.07 × a 128K context window** (926,232 ÷ 131,072).

### Count caliber, stated

Four different counts are all defensible and they mean different things:

| Count | What it includes |
|---:|---|
| **371** | top-level dirs with `SKILL.md`, excluding `_index` — **the number quoted everywhere** |
| 372 | the same, including `_index` (a meta-directory, not a usable skill) |
| 364 | distinct slugs after alias dirs collapse onto their canonical names |
| 401 | a recursive walk, which also catches nested sub-skills under bundles like `video-seedance/skills/` |

The READMEs quote **371** because that is what `scripts/bench_skills.py` counts and what
the token cost is charged against. If you quote a different number, say which caliber.

## Scale check

A 1,000-skill catalog was built in a sandbox (realistic ~4 KB bodies, 3.8 MB total) and
measured. Real files were hash-compared before and after and were unchanged:

| Operation | Worst of 3 runs |
|---|---:|
| `skills index` | 0.49 s |
| `skills list` | 0.32 s |
| `skills resolve -k 5` | 0.33 s |
| `skills stats` | 0.32 s |

So "1,000 skills" is a measured capacity claim, not an estimate. The 371 above is just
the catalog on this machine.

## Honesty notes

- **`skills resolve` writes a usage counter.** It bumps the hit count in
  `~/.mcptoon/skills-usage.json` via `record_skill_use()`. That is a *side effect of
  measuring*, not of loading, and it is redirected with **`MCPTOON_SKILLS_USAGE`** —
  point it at a scratch path and your real ledger stays untouched:
  `MCPTOON_SKILLS_USAGE=/tmp/scratch.json python scripts/bench_skills.py …`. This was
  found the hard way: an early measurement run against a synthetic catalog wrote into
  the real ledger because the variable was assumed not to exist. It does.
- **`skills list` / `resolve` / `stats` read the cached index, not the roots.** They do
  not re-scan `--roots`. To measure a different catalog end to end, override
  `MCPTOON_SKILLS_INDEX` too, or run `mcptoon skills index <root>` first.
- **Two decimals lie here.** `39 / 926,232` at two decimals is `100.0%`, which reads as a
  typo. The script uses three decimals (`99.996%`) on purpose.
- **The tool-side count in this session's cache was 1,109**, not the README's 255. The
  READMEs quote `assets/benchmark_tiktoken.json`, a fixed 255-tool configuration, so the
  two sides are never compared across different catalogs.
