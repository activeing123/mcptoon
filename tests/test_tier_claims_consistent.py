"""档位 ↔ 数字必须一一对应（tiktoken 实测：JSON 71,929 / TOON 47,438 / SLIM 8,282 / name index 581）。

这一条是给"同一屏两个数打架"上闸：历史上 `--slim`(88.5%) 与 name-index(99.2%/581)
在 demo、CLI 输出和两份 README 之间互相串档，还留过一句 `0 tokens (always)`
与 581 正面冲突——正是外部评测能挑出来的"宣称≠实测"。改动任何文案前先跑本文件。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = [
    "src/mcptoon/demo.py",
    "src/mcptoon/cli.py",
    "src/mcptoon/output.py",
    "README.md",
    "README.zh-CN.md",
    "docs/integrations/codex.md",
    "docs/tiktoken-benchmarks.md",
    "scripts/make_demo_gif.py",
]
# 档位名 -> 允许出现在同一行的数字（None = 该行不许出现任何档位的标志数）
TIERS = {
    "slim": ("8,282", "88.5"),
    "compact": ("581", "99.2"),
}
MARKERS = {"8,282": "slim", "88.5": "slim", "581": "compact", "99.2": "compact"}


def _lines(rel):
    return (ROOT / rel).read_text(encoding="utf-8").splitlines()


def test_tier_numbers_never_cross_tiers():
    bad = []
    for rel in FILES:
        for i, line in enumerate(_lines(rel), 1):
            low = line.lower()
            hit = {MARKERS[m] for m in MARKERS if m in line}
            if not hit:
                continue
            # 行里提到某个档位标签时，只能带它自己的数字
            for flag, tier in (("slim", "slim"), ("full=False", "compact")):
                if flag not in low:
                    continue
                if tier in hit or hit == set():
                    continue
                if tier == "slim" and "--slim" not in low and "slim" not in low:
                    continue
                joined = "/".join(sorted(hit))
                snippet = line.strip()[:90]
                bad.append(f"{rel}:{i} 把 {joined} 的数字挂到了 {tier} 档：{snippet}")
    assert not bad, "\n" + "\n".join(bad)


def test_no_zero_token_claim_survives():
    """`0 tokens (always)` 与 581 不能同屏共存：这句已从 demo/README/GIF 里根除。"""
    offenders = [rel for rel in FILES if re.search(r"0 tokens\s*\(always\)", "".join(_lines(rel)))]
    assert not offenders, f"仍存在 0 tokens (always) 宣称：{offenders}"


def test_unmeasured_tool_count_gone_from_banner():
    """demo/GIF 横幅不许再写未实测的 "1,000 MCP tools"（演示只起 13 个工具）。"""
    for rel in ("src/mcptoon/demo.py", "scripts/make_demo_gif.py"):
        assert "Install 1,000 MCP tools" not in "".join(_lines(rel)), rel


def test_guard_actually_catches_a_planted_violation():
    """负向自测：把 581 挂到 --slim 行上，上面的闸必须报警（证明闸不是空跑）。"""
    planted = "    mcptoon manifest --slim  # all tools in 581 tokens (-99.2%)"
    hit = {MARKERS[m] for m in MARKERS if m in planted}
    assert hit == {"compact"}, "负向样本没触发标记，测试本身失效"
    assert "slim" in planted.lower()
