"""`docs/llms.txt` 是发给 AI 读者的站点索引（Context7 / llmref / awesome-llms-txt 一类目录都读它）。

它一旦写飘，错话会被 AI 直接引用出去，比 README 更难纠正，所以这里全部从仓里现测：
- 站点链接必须指向 docs/ 里真实存在的文件（索引不许腐烂）
- 外链只许落在白名单主机
- 提到的每个命令必须在 CLI 自己的帮助文本里存在（不许写幽灵命令）
- 数字只许用实测档位，禁发口径与串档写法一律拦下
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = "https://activeing123.github.io/mcptoon/"
LLMS = ROOT / "docs" / "llms.txt"
EXTERNAL_HOSTS = {"github.com", "pypi.org"}
BANNED = ("99.8", "90,804", "117 tokens", "123 tokens", "97%")


def _text():
    return LLMS.read_text(encoding="utf-8")


def _site_targets():
    """把站内链接映射成 docs/ 下应当存在的文件。"""
    out = []
    for url in re.findall(r"\]\((https?://[^)\s]+)\)", _text()):
        if not url.startswith(SITE):
            continue
        rel = url[len(SITE):].rstrip("/")
        if rel == "":
            out.append(("(root)", ROOT / "docs" / "index.html"))
        elif rel.endswith(".md") or rel.endswith(".html"):
            out.append((rel, ROOT / "docs" / rel))
        else:
            # 目录式 URL：Pages 找的是 <dir>/index.html
            out.append((rel + "/", ROOT / "docs" / rel / "index.html"))
    return out


def test_llms_txt_exists_and_is_not_empty():
    assert LLMS.exists(), "docs/llms.txt 不存在：Pages 站少了给 AI 读者的索引"
    t = _text()
    assert t.startswith("# mcptoon"), "llms.txt 必须按 llmstxt 约定以一级标题开头"
    assert len(t) > 800, "llms.txt 短得不像一份索引"


def test_every_site_link_resolves_to_a_real_file():
    missing = [rel for rel, path in _site_targets() if not path.exists()]
    joined = ", ".join(missing)
    assert not missing, f"llms.txt 指向了不存在的页面：{joined}"


def test_links_stay_on_allowed_hosts():
    bad = []
    for url in re.findall(r"\]\((https?://[^)\s]+)\)", _text()):
        host = url.split("/")[2]
        if host == SITE.split("/")[2]:
            continue
        if host not in EXTERNAL_HOSTS:
            bad.append(url)
    assert not bad, f"llms.txt 出现计划外主机的链接：{bad}"


def _help_text():
    """权威清单 = CLI 自己打出来的那份帮助，不是我们抄的。"""
    import contextlib
    import io

    from mcptoon import cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._print_help()
    out = buf.getvalue()
    assert "Usage:" in out, "_print_help() 没打出帮助，这条测试要跟着 CLI 结构调整"
    return out


def test_named_commands_all_exist_in_cli_help():
    real = set(re.findall(r"mcptoon ([a-z][a-z-]+)", _help_text()))
    assert real, "CLI 帮助文本里一个命令都没解析出来"
    named = set(re.findall(r"`mcptoon ([a-z][a-z-]+)", _text()))
    ghost = sorted(named - real)
    assert not ghost, f"llms.txt 写了帮助里没有的幽灵命令：{ghost}"


def test_canonical_measurement_is_present_and_tiers_stay_separate():
    t = _text()
    assert "581" in t and "71,929" in t, "llms.txt 少了那条唯一的对外实测口径"
    for line in t.splitlines():
        if "--full" in line and any(k in line for k in ("88.5", "581", "99.2")):
            snippet = line.strip()[:90]
            raise AssertionError(f"把 compact/slim 档的数字挂到了 --full 上：{snippet}")
        if "--slim" in line and "99.2" in line:
            snippet = line.strip()[:90]
            raise AssertionError(f"slim 档是 8,282（−88.5%），不许写 −99.2%：{snippet}")


def test_banned_claims_never_enter_the_ai_surface():
    hits = [b for b in BANNED if b in _text()]
    assert not hits, f"llms.txt 出现禁发口径：{hits}"
