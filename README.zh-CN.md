<div align="center" markdown="1">

# mcptoon

**本地添加 1,000 个 MCP 工具和 1,000 个技能，也不用担心 token 上下文。**（本人实测：255 个工具 / 371 个技能）

MCP 工具 + Agent 技能，压缩说明书 71,929 token → 581（省 99.2% token，实测）。mcptoon 是一个 189KB 的零依赖 CLI，自动同步给你的每个 AI，你一行配置都不用手写。调用结果加 `--toon` 无损往返。

**① 省 token** —— 它把 MCP 工具 schema 和技能文件都挡在 Agent 上下文之外。工具：**71,929 → 581 token**（255 个工具，实测 −99.2%）；技能：**92.6 万 → 501 token** 就能定位到该用哪个，常驻只占 **39 token**（实测 −99.9%）；调用结果加 `--toon` 再省约 34%。

**② 省配置** —— **装一次 mcptoon，你电脑上所有 AI 都能用上全部 MCP 工具和技能。** 以后新增工具或者技能立刻生效，无需重启任何 Agent。

[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon/stargazers)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-1069%20passed-brightgreen)](#贡献)
[![Manages](https://img.shields.io/badge/manages-MCP%20%E5%B7%A5%E5%85%B7%20%2B%20Agent%20%E6%8A%80%E8%83%BD-8250df)](#工具箱的另一半技能)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)
[![AllMCPs](https://allmcps.com/api/badge/mcptoon?style=directory)](https://allmcps.com/mcp/mcptoon?verify=7eb0d0d6-5d4e-41a3-a048-2fe3c91a36ed)
[![MCPVault: verified](https://mcpvault.io/badge/mcptoon.svg)](https://mcpvault.io/servers/mcptoon/health?utm_source=external_badge&utm_medium=referral&utm_campaign=mcp_health_report)
[![mcptoon on AI Agents Listing](https://aiagentslisting.com/mcptoon/badge.svg)](https://aiagentslisting.com/mcp/mcptoon)
[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/activeing123/mcptoon)

**👉 眼见为实，这条命令可以测试你自己机器上的 agent 工具和技能吃掉你多少上下文，30 秒：`pip install mcptoon && mcptoon bench` —— 在你机器上测试出工具和技能吃掉多少 token。**

**👉 或先看它跑一遍：`uvx mcptoon demo --quick` —— 255 个工具，说明书 71,929 token → 名字清单 581 token（−99.2%）。**（demo 需要 Node）

**👉 [English](README.md) · [开发者文档](DEVELOPERS.md) · [反馈问题](https://github.com/activeing123/mcptoon/issues)**

![Benchmark: 255 tools, 71,929 → 581 tokens](assets/benchmark.svg)

</div>

```bash
pip install mcptoon

# 30 秒自证，跑在你自己机器上——不动你的服务器，不要 API key：
mcptoon demo --quick
```

---

## 这不是我们自说自话

上面那些数字是我们测试出来的，但"schema 全量进上下文很贵"这件事，不是只有我们这么说：

- **[Anthropic 官方工程博客](https://www.anthropic.com/engineering/code-execution-with-mcp)**：工具 schema 全量进上下文是真实痛点，一个例子就从 150,000 token 降到 2,000（省 98.7%）
- **[Firecrawl 基准](https://firecrawl.dev/blog/mcp-vs-cli)**：同一任务，CLI 花 1,365 token，MCP 花 44,026——差 32 倍（全量 schema 一次性加载）
- **[Scalekit 基准](https://scalekit.com/blog/mcp-vs-cli-use)**：CLI 便宜 10–32 倍、可靠性 100%，MCP 只有 72%
- [MCP-Zero（arXiv:2506.01056）](https://arxiv.org/abs/2506.01056)：按需工具检索可实现与工具数近乎无关的常数成本
- [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576)：MCP 官方在途提案，正打算削减 schema 冗余——上游自己承认了这个问题

测过这件事的不是我们一家。mcptoon 是**今天就能用**、一次覆盖所有 Agent 的那一个。

---

## 30 秒上手

```bash
pip install mcptoon                          # 纯标准库，189KB，零依赖

# 添加任意 MCP 服务器——一条命令：
mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything

# 查看所有可用工具（默认就是名字索引，255 个工具只需 581 token）：
mcptoon manifest

# 调用工具（默认输出 JSON；想更省加 --toon）：
mcptoon call everything echo '{"message":"hi"}'
```

### 用你自己的技能目录，30 秒自证省了多少

这些是最容易被怀疑的数字——"92.6 万 token？"——所以别信我们，自己测试一遍。
不要 API key、不碰你的服务器、不用配置、**也不用克隆仓库**——`bench` 就在安装包里：

```bash
pip install mcptoon          # bench 是内置命令，不用克隆仓库
pip install tiktoken         # 可选：不装的话，bench 会标"estimate"而不是"实测"
mcptoon bench
```

`mcptoon bench --roots <目录>` 可指向任意技能目录。工具那几行是**你本机缓存**的 schema，
数字会不同；下面技能那几行是单根（`~/.claude/skills`）的数。

它把**两半放进同一张表**——工具 schema 对名字索引、全部 `SKILL.md` 对常驻指针和一次
查询——让你看清每个数字到底是什么，而不是信一句口号。在写这份 README 的机器上：

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

*（表尾的 query / 口径 / 128K 窗口数已省略。`query` 很关键：resolve 那一行是按 `make a PDF` 测的。）*

**注意它替掉了什么。** 让一个 Agent 不用 mcptoon 去找"该用哪个技能"——它没有索引，
只能一个接一个读 `SKILL.md` 直到找到。在这台机器上全套是 926,232 token：**装不进
128K 窗口**，于是被截断，而掉出去的那个正好是你要的。用 mcptoon，同一个问题只要
**501 token**——`mcptoon bench` 会指向你自己的目录，让你自己验一遍。

一张表里两种口径，是故意的：工具那几行是**你本机缓存**的 schema；账 1 引用的是固定的
255 工具基准，这样那个数字不会漂。技能那几行按"只数一层、排除 `_index`、根目录按真实
路径去重"统计——所以就算你几个 Agent 目录是指向同一份目录的软链，也不会被数成四份。

### `mcptoon demo` 真跑出来是什么样子

不要 API key、不碰你自己的服务器、不用配置：它拉起官方 "everything" 参考服务器，
调一个工具，然后把 token 账算给你看。下面这段是真身输出，一字未改
（Windows + Python 3.12；只剪掉了开头的字符画横幅和结尾那句求 star）：

```text
$ mcptoon demo --quick

  Starting demo server...
  ✓ Demo server ready

  📊  SAME data, 19% fewer tokens:
              21  →          17   (SLIM)

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
  ✓ connect every agent with ONE config   →  mcptoon sync
  ✓ expose ALL servers as ONE stdio server →  mcptoon serve
  ✓ never paste tool schemas again         →  mcptoon manifest --slim

  Schemas are fetched, not injected — you pay for a listing, not for every turn
  255 tools listed once: 581 tokens (71,929 → 581, −99.2%, measured)
```

表格边距会跟着你的终端宽度变，数字不会。第一张表是这次真调用的实测，第二张是仓库里
存档的 255 工具基准（`docs/tiktoken-benchmarks.md`），每次跑都一模一样。

机器上没有 Node？`mcptoon demo-server` 就是同一场演示、且什么都不用下载：11 个纯标准库
写的 MCP 工具，不联网、不要密钥。

用 Claude Code？连终端都可以跳过：

```bash
/plugin marketplace add activeing123/mcptoon
```

插件自动装好 CLI（SessionStart 钩子）、通过 `.mcp.json` 接好 `mcptoon
serve` 桥，并自带一份技能说明书让 Agent 知道什么时候压缩。`/mcptoon-setup`
是手动兜底。

**或者让 mcptoon 自动发现你机器上已有的服务器：**

```bash
mcptoon quickstart     # 自动发现 + 配置 + 展示工具——一条命令搞定
```

就这些。不用手写 JSON 配置。不用调试 MCP 协议。不污染上下文窗口。wheel 只有 189KB、
零依赖；mcptoon 本体不需要任何 API key，也不向任何云端打电话——服务费 $0，一切都在
你自己的机器上跑。

---

## 工具箱的另一半：技能

一个 Agent 技能就是一个 `SKILL.md` 文件。Agent 加载它的方式，和加载 MCP 工具 schema
一模一样：开工前先塞进上下文窗口。在写这份 README 的机器上，**371 个技能要 926,232 token
——超过 7 个 128K 上下文窗口。** 装不下，所以一定会丢东西；丢掉的，正好是你那天要用的那个技能。

`mcptoon skills` 补上的，是所有技能管理器都没碰的那一半。市面上有一打工具在*整理*技能——
安装、浏览、跨 IDE 同步。它们没有一个去测试"这个目录到底花多少 token"，也没有一个把它挡在上下文外面。
mcptoon 两件事一起做，用的是和 MCP 服务器同一套"单一真源"模型：

```bash
mcptoon skills list                      # 目录里有什么（--usage 附带命中次数）
mcptoon skills resolve "做个 PDF"        # BM25 短名单——离线、不调 LLM、不烧 token
mcptoon skills sync ~/skills             # 分发到每个 Agent 的技能目录
mcptoon skills sync ~/skills --dry       # 只预览计划，一个字节都不写
mcptoon skills add my-skill --desc "…"   # 在真源里新建技能
mcptoon skills remove my-skill           # 退役——移进带日期的墓地
```

视图默认是**链接**（Windows 上用 junction，不需要管理员权限），所以改一次真源，
处处即时生效，也没有第二份副本会走样。三条安全规则兜底：本该是链接的位置上如果是真实目录，
**只归档、绝不删除**；视图本身就是指向真源的链接时，**完全不碰**；`remove` 是把技能
**移进**墓地，删错了是一条 `mv` 搬回来，而不是重新克隆。需要时再加生命周期开关——
`--version-gate` 拦下"内容变了但 `version` 没跟着改"的技能，
`--derived roo|opencode|all` 重生成部分 Agent 读的扁平 `.md` 视图，
`--archive DIR` 把漂移停进你指定的墓地，`remove --tombstone` 把删除提交成 git 墓碑
（按路径限定），让双向 git 同步无法把它复活。

---

## 解决什么问题？

每个 MCP Agent（Claude Code、Cursor、Codex 等）都会在开始工作前把**所有工具的 schema
塞进你的上下文窗口**：

```
50 个工具  → 14,113 token 的 schema → 128K 上下文：11% 没了
255 个工具 → 71,929 token 的 schema → 128K 上下文：56% 没了
```

于是你不用的时候卸载服务器，用的时候再加载。来回折腾。想加个新服务器还得手写 JSON
配置——少个逗号就全崩了。

**mcptoon 解决这个问题。** 你的 MCP 服务器都配着，但它们的 schema **默认不进 Agent 的
上下文**。Agent 只跑 `mcptoon` 命令，只有你要的紧凑结果进上下文——名字索引轻到 581
token（50 工具 114，−99.2%）。

```
不用 mcptoon：255 个工具 → 71,929 token 占掉大半个窗口
用 mcptoon：  255 个工具 → 581 token。省了 99.2%。
```

*两行都是实测配置，不是拿一个数上下缩放（tiktoken `cl100k_base`，
`assets/benchmark_tiktoken.json`）。你的组合会不同——
[在浏览器里算你自己的数](https://activeing123.github.io/mcptoon/tools/token-tax/)，
30 秒，不上传任何东西。*

---

## 行业验证了问题——但把解法关进了自家围墙

工具上下文太重，不再是小众抱怨——它已经是官方盖章的工程问题。但目前每一个认真的解法，
都**长在别人的平台里**——对你真正在用的 agent 来说，等于没出：

- **Anthropic** 做出来了——但锁在 Claude 里。Tool Search Tool 和 Programmatic Tool
  Calling 干的正是这件事，可两者都是 Claude 平台 beta。你跑的其他 agent 上，工具*结果*
  仍然逐 token 进上下文。
- **MuleSoft** 产品化了——但锁在企业网关里。MCP Payload Optimization 把
  「清洗 → 蒸馏 → 压缩」做成了产品（压缩环节是 TOON），但只在 MuleSoft 网关内，
  MCP 规范还落后一代。

| 解法 | 跑在哪 | 门槛 |
|---|---|---|
| Anthropic 的 Tool Search Tool / PTC | Claude 平台 beta | 只有 Claude——其他 agent 仍要为结果逐 token 付费 |
| MuleSoft 的 MCP Payload Optimization | MuleSoft 企业网关 | 要过网关；MCP 规范落后一代 |
| **mcptoon** | **任何能跑 shell 命令的 agent** | 无——189KB，不要密钥、不要代理进程，MCP 2026-07-28 GA |

上面每一条都是一堵墙。mcptoon 是同一个答案，但没有墙：**今天就能跑、每个 agent 一次
到位**——「结果侧」的纪律，不收平台税，不收网关税。

---

## 安装 MCP 服务器——每条一个命令

```bash
# 从 npm 安装（大部分 MCP 服务器在这里）：
mcptoon install brave-search --npm @modelcontextprotocol/server-brave-search

# 从 pip 安装：
mcptoon install my-tool --pip mcp-my-tool

# HTTP/SSE 服务器：
mcptoon install remote-api --url https://example.com/mcp

# 列出已安装：
mcptoon install --list

# 卸载：
mcptoon install --remove brave-search
```

mcptoon 自动连接、发现工具、生成 handler、注册。不需要重启。
每次安装给 mcptoon 本体**新增 0 KB**——CLI 保持 189KB、零依赖，因为服务器是你的
机器直接运行的外部进程，不是打包进 mcptoon 的代码。四个步骤、一条命令、不用重启 Agent。

**支持任何 MCP 服务器：**

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest    # 直接就能用
```

---

## 作为 Agent 技能安装（支持 80+ Agent）

通过开放 Agent 技能生态，教会你的 Agent *使用* mcptoon——技能会被
Claude Code、Cursor、Codex、Cline、Windsurf 以及另外 75 个 Agent 自动识别：

```bash
npx skills add https://github.com/activeing123/mcptoon --skill mcptoon
```

---

## 想要图形界面？——ToonDeck

不想手写配置？**[ToonDeck](https://github.com/activeing123/toondeck)**
是 mcptoon 的本地控制台：所有 MCP 服务器和工具集中一屏，带真实健康检查；
一套技能目录同步到你所有的 Agent；启动 Agent 并实时看日志；
API 密钥存进系统钥匙串——绝不落明文文件。

```bash
pip install toondeck    # Web UI 直接打进 wheel——不需要 node，不需要构建
```

Pre-alpha；免费（Apache-2.0）。ToonDeck 负责驱动——mcptoon 始终是底下的唯一事实源。

---

## 所有 AI Agent 都能用

mcptoon 是 CLI 工具。**你的 Agent 能跑 shell 命令，就能用 mcptoon。** 不需要插件、
SDK、每个 Agent 单独配。

| Agent | 怎么用 |
|---|---|
| **Claude Code** | 在 SKILL.md 里写 `mcptoon` 命令 |
| **Codex (OpenAI)** | 在 AGENTS.md 里加 `mcptoon` |
| **Cursor** | 在 .cursorrules 里加 `mcptoon` |
| **OpenCode** | 在自定义命令里用 `mcptoon` |
| **任何 Agent** | 能跑 shell 命令就能调 `mcptoon` |

在 `~/.mcptoon/config.json` 配置一次，所有能跑 shell 命令的 Agent 共享同样的服务器和
工具和技能。不能跑的 GUI Agent？`mcptoon sync` 把原生 JSON 写进它们各自的位置。

```bash
export MCPTOON_AGENT_TYPE=claude   # 调用结果自动用 --toon
# export MCPTOON_AGENT_TYPE=openai   # 或保持默认 JSON
```

你的 AI 甚至可以自己加工具——不需要人介入：

```bash
# Agent 干活干到一半需要 GitHub 访问？它自己跑：
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon call github search_repos '{"query":"mcp"}'
# 完事。不用编辑 JSON。不用重启。上下文不丢。
```

---

## 数据

mcptoon 省 token 分三笔账，先分清是哪一段再对数字。发现工具：255 个工具的原生发现
要吃掉 71,929 token——128K 窗口的一半以上——同一套工具走名称索引只要 581，省 99.2%。
调用结果：`--toon` 比 JSON 小 34.0–34.2%。技能目录：926,232 token 的 `SKILL.md` 全文，
变成 39 token 的常驻指针 + 每次查询 501 token。所有数字都是实测配置（工具侧 tiktoken
`cl100k_base` + `assets/benchmark_tiktoken.json`，两半都可用 `mcptoon bench` 复现），
不是按比例放大的估算。

### 账 1 · 发现工具（`manifest`）：默认就省 99.2%

这一笔发生在**你的 Agent 决定"该用哪个工具"之前**。原生 MCP 先把所有工具的完整
schema 塞进上下文（50 工具 14,113 token、255 工具 71,929 token），mcptoon 只发名字
索引——这就是"114 不是 14,113"的来处。

| 工具数 | 原生 schema（JSON） | mcptoon 名字索引（默认） | 省多少 |
|-------|-------------------|------------------------|-------:|
| 5 | 1,519 | 11 | −99.3% |
| 50 | 14,113 | **114** | **−99.2%** |
| 255 | 71,929 | **581** | **−99.2%** |

零操作、默认开启：`mcptoon manifest` 不加任何 flag 就是这一档。
想多给 Agent 一点信息？`--slim`（名字+参数类型）是 8,282 tokens（−88.5%）；
`--full` 在此之上再加描述；`--json`（完整 schema）是基准线。

*两行都是实测配置，不是拿一个数上下缩放（tiktoken `cl100k_base`，
`assets/benchmark_tiktoken.json`）。你的组合会不同——
[在浏览器里算你自己的数](https://activeing123.github.io/mcptoon/tools/token-tax/)，
30 秒，不上传任何东西。*

### 账 2 · 调用结果（`call`）：可选项，--toon 省约 34%

这一笔发生在**工具把结果返回给你的 Agent 之后**。`mcptoon call` 默认输出 JSON——
对，默认是不省的。想让结果也变小，加 `--toon`（结构化编码，可逆）：

```
默认：  mcptoon call fetch fetch '{"url":"https://example.com"}'   → JSON（基准线）
更省：  mcptoon call fetch fetch '{"url":"https://example.com"}' --toon   → 省约 34%
```

34% 是 `assets/benchmark_tiktoken.json` 里 `toon_save` 的实测值（34.0–34.2%），
不是宣传数字。

**一句话记法：99.2% 是你"看有哪些工具"省下的，34% 是你"拿到结果"能再省的。**

### 账 3 · 技能目录（`skills`）：926,232 → 常驻 39 + 每次查询 501

同一笔账，算在工具箱的另一半上。Agent 只要读技能目录，就得为每个 `SKILL.md` 付账。
下面是写这份 README 那台机器上的真实数字——371 个技能文件，同样的 tiktoken `cl100k_base`。

| Agent 要加载的东西 | Tokens | 对比全量 |
|---|---:|---:|
| 每个 `SKILL.md` 全文 | **926,232** | — |
| 只取每个技能的 `description` | 27,292 | −97.1% |
| 只取每个技能的名字（纯名字索引） | 1,413 | −99.85% |
| `mcptoon skills resolve "<任务>" --k 5`（只返回最相关的 5 个） | **501** | **−99.95%** |
| `mcptoon skills manifest`（常驻的那个指针） | **39** | **−99.996%** |

再看一眼第一行：**926,232 token = 7.07 个完整的 128K 上下文窗口。** 目录根本装不进窗口，
这就是为什么 Agent 会悄悄丢掉技能，然后"忘记"你几个月前装好的能力。解法和账 1 一样——
按需取，绝不预加载：

```bash
mcptoon skills manifest                      # 39 token，常驻
mcptoon skills resolve "做个 PDF" --k 5      # 501 token，只返回最相关的 5 个
```

**最后两行是两件不同的事，别混着看。** **39 token** 的 `manifest` 是个*指针*——它只告诉
Agent 该怎么问，里面一个技能名字都没有。**501 token** 的 `resolve` 才是真干活：它返回
你这次请求真正相关的 5 个技能。如果你想要的是"技能当工具"那种常驻名字清单，那是
**1,413 token**——比加载全文仍然省 99.85%。不管哪种，你都不用付那 926,232。

*实测，不是估算。`mcptoon bench` 用你自己的目录复现上面两行——账 1 的工具行也在同一张表里。
完整方法、口径与"数量口径表"见
[`docs/skill-token-benchmarks.md`](https://github.com/activeing123/mcptoon/blob/main/docs/skill-token-benchmarks.md)。你的目录不一样，比例不会变。*

*规模体检：1,000 个技能的索引与路由在 0.5 秒内完成（`index` 0.49s / `list` 0.32s /
`resolve` 0.33s，用 1,000 个真实体量的合成技能实测）。上面那 371 个只是本机的目录。*

### 对比实例（账 1 的直观版）

一个工具的 schema 用原生 JSON 是 **37 token**，进 mcptoon 名称索引只要 **2 token**
——单工具直降 95%（我们的 tiktoken 实测，`cl100k_base`）。

**不用 mcptoon**（所有 MCP 客户端都会往上下文里塞的——37 token，tiktoken 实测）：

```json
[{"name":"search_web","description":"Search the web for information",
"inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"Search query"}}}}]
```

**用 mcptoon**（2 token）：

```
search_web
```

**用 mcptoon --slim**（6 token，名字+参数类型）：

```
search_web|query:s*
```

---

## 安全

三层防护，全部内置：

| 层 | 做什么 | 示例 |
|-------|-------------|---------|
| **危险操作拦截** | 默认拦截危险动作，除非显式加 `--destructive` | `db query '{"sql":"DROP TABLE users"}'` → 拦截 |
| **Prompt 注入防护** | 扫描结果中的注入模式 | `"ignore previous instructions"` → 拦截 |
| **凭据泄露检测** | 扫描结果中的暴露 key/token | `sk-abc...xyz` → 拦截，不进 Agent 上下文 |

- **没有遥测。** 没有分析、没有崩溃报告、没有回传。
- **不存凭证。** API key 从你的配置或环境变量直接传递。
- **没有依赖。** 纯 Python 标准库。没有供应链要审计。
- **没有守护进程。** 纯 CLI 不常驻、不监听端口、没有可被攻破的入口。

四个零：0 个遥测端点、0 个存储凭证、0 个第三方依赖、0 个监听端口——攻击面就是
一条 stdin 管道。

---

## 全部命令

```bash
mcptoon quickstart              # 一键上手（发现 + 配置 + 展示工具）
mcptoon discover                # 扫描本机遗留的 MCP 服务器（--write 保留，--health 探活）
mcptoon init                    # 生成示例配置（--auto 自动发现并填好）
mcptoon list                    # 查看已配置服务器
mcptoon manifest                # 所有工具名（默认即紧凑档，255 个工具只需 581 token）
mcptoon manifest --slim         # 名字+参数类型（8,282 对 71,929 = −88.5%）
mcptoon manifest --compact      # 只有名字（581 对 71,929 = −99.2%，实测）
mcptoon inspect <server> <tool> # 查看某个工具的 schema
mcptoon search <query>          # 跨服务器搜索工具
mcptoon call <server> <tool> '{"args":"here"}'   # 调用工具
mcptoon call --auto <tool> '{"args":"here"}'     # 自动找服务器
mcptoon call <server> <tool> --stdin             # 从 stdin 读大参数
mcptoon add <name> --stdio|--http <cmd|url>     # 添加任意 MCP 服务器
mcptoon remove <name>           # 移除一个服务器
mcptoon install <name> --npm|--pip|--url <pkg>  # 安装 + 自动生成 handler
mcptoon install --list          # 列出已安装
mcptoon install --remove <name> # 卸载
mcptoon sync                    # 同步原生配置到每个检测到的 Agent
mcptoon health                  # 健康检查所有 MCP 服务器（--json 任一死掉即退出码 1）
mcptoon policy                  # 逐工具压缩策略（raw / toon / slim）
mcptoon skills index [ROOT ...] # 构建磁盘索引（list/resolve 前必须先跑）
mcptoon skills list             # 列出技能目录（--usage 附带命中次数）
mcptoon skills resolve "<任务>" # 技能 BM25 短名单（离线、不调 LLM）
mcptoon skills route "<任务>"   # 先短名单，再让 LLM 挑（--model、--endpoint）
mcptoon skills stats            # 目录体检（重名、别名、缺 description）
mcptoon skills manifest         # 常驻的一行指针（39 token）
mcptoon skills sync <src>       # 把技能目录分发到每个 Agent 的目录
mcptoon skills add|remove <name> # 在真源新建技能 / 退役进墓地
mcptoon bench                   # 本机自证省了多少（工具+技能，一张表）
mcptoon plugin install <dir>    # 安装 Agent Plugins 1.0.0 插件
mcptoon serve                   # 以 MCP server 形态运行（stdio/HTTP）——MCP 2026-07-28：无状态优先、server/discover、列表结果可缓存
mcptoon demo                    # 一条命令，本机现场演示
mcptoon doctor                  # 自检：Python、配置、连通性
mcptoon usage                   # 本地调用统计
mcptoon completion ps           # Shell 补全（bash/zsh/fish/powershell）
```

### 格式家族：四个档，默认 compact

发现工具和调用结果各有一组格式，都是可选的——默认就是最省的那档：

**manifest（发现工具）：默认 compact，想更详细再升级**

| 档 | 输出形态 | 比原生 schema 省 | 原创性 |
|---|---|---|---|
| **compact（默认）** | 仅工具名 `search_web` | **99.2%** | 通用设计 |
| **slim** | 名字+参数类型 `search_web\|query:s*` | 88.5% | **mcptoon 原创** |
| **full** | 完整 schema 带参数 | 基准线 | 原生 MCP |

**为什么默认 compact 而不是 full？** Agent 决定"用哪个工具"只需要名字
（255 个工具 581 token 就够）；要到真正调用时才需要参数细节，那时用
`inspect` 或 `manifest --full` 按需取。默认塞满 full schema，等于把省掉的
99.2% 又送回去。

**推荐用法（这条是刚需，不是建议）。** compact 名字清单是"目录"，不是"调用合同"。
本机 41 个真实工具实测（金标准=完整 schema，每档单一推理模型）：只凭名字瞎猜参数的
agent，调用合法率只有 **4/41 ≈ 10%**——栽就栽在 `account`、`pageId` 这类猜不到的参数名；
而对一轮真正要用的 2~3 个工具各跑一次 `inspect` 的 agent，命中率 **41/41 ≈ 100%**，
和一次性塞全部 schema 完全持平。一轮任务只碰几个工具，几次按需 `inspect` 的开销远低于
全量 dump：**~99% 的 token 节省和满分的调用准确率，两个都拿到**。给 agent 的铁律：
**用 `manifest` 选工具，调用前先 `inspect`。**


**call（调用结果）：默认 JSON，--toon 才省**

| 档 | 输出形态 | 比 JSON 省 | 原创性 |
|---|---|---|---|
| **（默认）** | JSON | 基准线 | 通用 |
| **--toon** | 结构化编码（可逆） | 约 34% | 集成开源 TOON 标准 |
| **--mcptoon** | 旧版管道格式 | — | mcptoon 原创（legacy） |

**这几种格式哪里来的**

- **compact**：工具名列表，任何工具管理器都能做，不是专属设计。
- **slim**（`name|param:type*` 签名）：**mcptoon 原创设计**，实现在 `output.py`
  （`slim_toon`，Apache 2.0）；NOTICE 已注明。
- **full**：完整 JSON Schema，MCP 协议原生就是它。
- **toon**（结果编码）：集成开源 **TOON 开放标准**
  （[toon-format/toon](https://github.com/toon-format/toon) v4.1，MIT），
  vendored 自 python-toon，NOTICE 已致谢——不是我们的发明，我们不自居。

---

## 技术规格

下面每一条都能用 `mcptoon --version` 和它读的文件核对。工具箱的两半共用一套引擎、
一份配置、一种索引格式。

| | MCP 工具 | 技能 |
|---|---|---|
| **单位** | 一个工具 = 一份 JSON Schema | 一个技能 = 一个 `SKILL.md`（YAML frontmatter + 正文） |
| **真源** | `~/.mcptoon/config.json`（服务器） | 一个技能根目录（默认 `~/.claude/skills`、`~/.agents/skills`、`~/.codex/skills`、`~/.cursor/skills`） |
| **怎么挡在上下文外** | 纯名字 manifest（255 个工具 581 token） | BM25 索引 + 一行 39 token 的指针（每次查询 501 token） |
| **发现** | `mcptoon manifest` · `inspect` · `search` | `mcptoon skills resolve` · `route` |
| **分发** | `mcptoon sync`（给每个 Agent 写原生 JSON） | `mcptoon skills sync`（给每个 Agent 建链接） |
| **增删** | `install` · `add` · `remove` | `skills add` · `skills remove --tombstone` |
| **体检** | `mcptoon health` | `mcptoon skills stats` |

**运行时。** Python ≥ 3.10（CI：3.10–3.13 × Linux、Windows、macOS）。25 个模块、
15,697 行 Python、**189KB** wheel、**零第三方依赖**——只用标准库，由 CI 的
`scripts/check_zero_deps.py` 强制。没有守护进程、没有监听端口、没有遥测、不存凭证。

**工具格式。** `compact`（只有名字，默认）· `slim`（`name|param:type*`，mcptoon 原创）
· `full`（原生 JSON Schema）· `toon`（开源 TOON 标准，可逆）。它们全部只活在输出层
——线上协议永远是标准 JSON-RPC，服务器一个非标准的字节都看不到。

**技能内部。**
- **索引** —— `~/.mcptoon/skills-index.json`（`version: 1`），由 `mcptoon skills index`
  生成；`list` / `resolve` / `route` / `stats` **必须先有它**（否则报
  `no skills index yet. Run: mcptoon skills index`）。
- **检索** —— 对每个技能的 slug + `description` + 触发词跑 BM25，并把所有指向它的
  别名合并进来，所以用别名也能命中正主。全程离线：不调 LLM、不联网。`--k` 默认 **5**。
- **指针** —— `mcptoon skills manifest` 只打一行，里面**没有任何技能名**；它是告诉
  Agent"该怎么问"的指令，不是索引。
- **同步** —— 视图是**链接**（Windows 上用 junction，不需要管理员）。本该是链接的位置
  上若是真实目录，**只归档、绝不删除**；视图本身已指向真源时**完全不碰**；`remove`
  把技能**移进**带日期的墓地，删错了是一条 `mv` 搬回来，而不是重新克隆。
- **生命周期** —— `--version-gate` 拦下"内容变了但 `version` 没跟着改"的技能；
  `--derived roo|opencode|all` 重生成部分 Agent 读的扁平 `.md` 视图；`--archive DIR`
  指定漂移停放的墓地；`remove --tombstone` 把删除提交成 git 墓碑（按路径限定），
  让双向 git 同步无法把它复活。

**环境变量覆盖**（测试和"跑多套目录"时用）：
`MCPTOON_SKILLS_ROOTS`、`MCPTOON_SKILLS_VIEWS`、`MCPTOON_SKILLS_INDEX`、
`MCPTOON_SKILLS_USAGE`、`MCPTOON_SKILLS_ENDPOINT`、`MCPTOON_SKILLS_MODEL`、
`MCPTOON_SKILLS_LEDGER`、`MCPTOON_SKILLS_DERIVED`、`MCPTOON_CONFIG_FILE`、
`MCPTOON_AGENT_TYPE`。

**复现这些数字。** `mcptoon bench`——两半一张表，随包发布。克隆仓库后还可用 `scripts/bench_tokens.py` 与 `scripts/bench_skills.py`（精确、需 tiktoken）。
方法与口径见
[`docs/tiktoken-benchmarks.md`](https://github.com/activeing123/mcptoon/blob/main/docs/tiktoken-benchmarks.md)
与
[`docs/skill-token-benchmarks.md`](https://github.com/activeing123/mcptoon/blob/main/docs/skill-token-benchmarks.md)。

---

## 自研格式会破坏 MCP 兼容吗？——不会，三层理由

"自研格式 = 兼容炸弹"是合理的警惕，但这里不成立，原因有三层：

**1 · 协议层永远是标准 JSON-RPC，格式只在展示层。**
mcptoon 与 MCP 服务器之间永远说标准 MCP 协议（initialize / tools/list /
tools/call——2026-07-28 GA 桥升级后还支持 server/discover 与无状态请求；
旧客户端的 initialize 握手照常保留）。compact/slim/toon 只作用于"mcptoon → Agent"的输出渲染，不进入
与服务器的任何字节。服务器看到的永远是标准 JSON——它甚至不知道这些格式存在。

**2 · --toon 本身不是自研，是开源标准。**
TOON（Token-Oriented Object Notation）是外部开放标准
（[toon-format/toon](https://github.com/toon-format/toon) v4.1，MIT，
官方 TypeScript 参考实现）。我们集成的是 python-toon（MIT），
`tests/test_toon_cross_validate.py` 逐条验证 `decode(encode(x)) == x` 可逆性。

**3 · 有兜底，最坏情况回退 JSON。**
`--toon` 解码失败自动回退 JSON（`--fallback-json`）；而且调用结果默认就是 JSON，
`--toon` 只是可选项。想回到完整 schema？一个 `--full` 就是原生 MCP，没有任何
锁定。

**一句话：协议上零改动，格式全在输出层，最坏情况回退 JSON。** 担心的"服务器
听不懂自研格式"不会发生——跟服务器说话的永远是标准 JSON-RPC。

---

## 原理

mcptoon 是 **CLI 工具**，不是 MCP 客户端库。你的 Agent 不直连 MCP 服务器——它跑
`mcptoon` 命令。schema 存在磁盘上的 `~/.mcptoon/config.json`，默认不进上下文窗口。

技能目录故意做成同一个形状：一个真源根目录、磁盘上一份 BM25 索引
（`~/.mcptoon/skills-index.json`）、上下文里一行 39 token 的指针。同一套"一个真源、
多份视图"，同一条"按需取、绝不预加载"的规则——整个工具箱之所以像一件事，因为它本来
就是一件事。

**两层解耦：**

```
第 1 层: mcptoon CLI (189KB, 零依赖)
         在 Agent 的 shell 里运行。schema 默认不进上下文。
                    │
第 2 层: 实际 MCP 服务器 (npm/pip 包)
         只有调用工具时才启动。不用就零开销。
```

- 1,000 个服务器配好 → 0 个在运行，直到你用其中一个
- mcptoon 不捆绑任何服务器——你加你想要的，一条命令加一个
- 删掉 mcptoon？你的 MCP 服务器照常独立运行

---

## 为什么是 CLI，不是代理

MCP 的前提是：每一项能力都是一个*服务器*，而你的 Agent 必须被配置成能够到它。
正是这个前提，导致加一个工具就得给每个 Agent 各改一份 JSON、格式还各不相同、然后
全部重启——也导致每个 Agent 在干任何活之前，都要重付一次完整的 schema 成本。

命令行是所有 Agent 都已经有的那一个接口。而且这个形态本身就更便宜，这与 mcptoon
做了什么无关：

- Firecrawl 的基准：同一任务 **CLI 花 1,365 tokens，MCP 花 44,026——差 32 倍**
- Scalekit 的基准：CLI **便宜 10–32 倍，可靠性 100%，MCP 是 72%**

真需要代理形态时，`mcptoon serve` 就是那个模式——所有已配置服务器合成一个 MCP 端点，
带连接池和按 Agent 隔离的 API Key。

---

## 贡献

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 1069 passed, 1 skipped
```

零依赖是硬规则，我们的测试门槛是每次改动先跑绿全套 1069 个测试。见
[CONTRIBUTING.md](CONTRIBUTING.md)、[DEVELOPERS.md](DEVELOPERS.md)。

项目本体：15,697 行 Python、25 个模块，零第三方依赖——供应链里 0 个要审计的环节。

---

## 生态

- **[ToonDeck](https://github.com/activeing123/toondeck)** — mcptoon 的 GUI 控制台（pre-alpha）：MCP server、工具、模型、API key 一桌管理，引擎就是 mcptoon。不想敲命令？用图形界面的它。

---

<div align="center">

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*

**省下的是你自己的 token。点个 star——小工具就是靠这个被更多人找到的。**

[![Star History Chart](https://api.star-history.com/svg?repos=activeing123/mcptoon&type=Date)](https://star-history.com/#activeing123/mcptoon&Date)

</div>
