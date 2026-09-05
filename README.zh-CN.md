<div align="center" markdown="1">

# mcptoon — MCP 工具发现只要 114 个 token，不是 14,113 个

**你装了几个 MCP 服务器，然后 Agent 变差了：更慢、更健忘、更容易答非所问。这不
是模型的锅。每个 MCP 工具都自带一份完整的 JSON Schema，而你的 Agent 必须先把它们
全读一遍，才有资格挑一个。**

**50 个工具就是 14,113 个 token——128K 上下文的 11%，你还没打字就没了。mcptoon
递过去的是名字：114 个 token，同样的工具，−99.2%。255 个工具那一档是 71,929 → 581，
超过半个窗口；按 agentic 用法算，每月 $25 到 $128 只花在"读说明书"上。**

*两行都是实测配置，不是拿一个数上下缩放（tiktoken `cl100k_base`，
`assets/benchmark_tiktoken.json`）。你的组合会不同——
[在浏览器里算你自己的数](https://activeing123.github.io/mcptoon/tools/token-tax/)，
30 秒，不上传任何东西；或者精确测量：`python scripts/bench_tokens.py`，
需要先 clone（这个脚本在仓库里，不在 wheel 里）。*

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/hero-powerstrip-zh.svg" width="820" alt="mcptoon 万能插排：把 MCP 工具插一次，Claude、Cursor、Codex 或任何 AI 都能用 —— 零手写配置、零重启">
</p>

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-738%20passed-brightgreen)](#开发者)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](#mcp-规范兼容性2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)

[English](https://github.com/activeing123/mcptoon/blob/main/README.md) ·
[开发者文档](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md) ·
[更新日志](https://github.com/activeing123/mcptoon/blob/main/CHANGELOG.md) ·
[提 Issue](https://github.com/activeing123/mcptoon/issues)

</div>

---

## 装一次，所有 Agent 都能用

```bash
pip install mcptoon          # 纯标准库，128KB wheel，零依赖

mcptoon quickstart           # 自动发现你已经配好的 MCP 服务器
mcptoon demo                 # 在你自己机器上现场对比，不用信任何人
```

不想折腾 Python？一行搞定，脚本全包：

```bash
curl -fsSL https://raw.githubusercontent.com/activeing123/mcptoon/main/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/activeing123/mcptoon/main/install.ps1 | iex
```

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/demo.gif" width="700" alt="mcptoon demo：pip install 后跑一条命令演示，眼看工具清单从 schema 转储塌缩成一份名字目录">
</p>

Windows · macOS · Linux · Python 3.10+ · Apache-2.0

---

## 它解决什么

每个 MCP 工具都自带一份说明书：它叫什么、干什么、接受哪些参数、每个参数能填什么。
你的 Agent 在挑用某个工具之前，得把这些全部读一遍——每个会话、每个 Agent 都重读一次，
而且是在任何活开始干之前。就是这一步把它的上下文窗口塞满，让它变慢、变健忘。

| | 没有 mcptoon | 有 mcptoon |
|---|---|---|
| 找一个工具 | 读完每份说明书 | 读一份名字清单 |
| 加一个服务器 | 逐个改每个 Agent 的 JSON，重启 | `mcptoon sync`，不用重启 |
| 多个 Agent | 每种格式各存一份配置 | 一份唯一事实来源，同步到各处 |
| 死服务器 | 等到调用时才发现 | `mcptoon health`，带 CI 退出码 |

换成协议术语："说明书"就是 JSON Schema，"名字清单"就是名字索引。mcptoon 是一个零依赖
CLI，把任意 Agent 接到每一个 Model Context Protocol 服务器上——包括根本不支持 MCP 的 Agent。

---

## 它是旋钮，不是开关

你的 Agent 要读多少，是你每次调用自己选的。下面**两列都是实测配置**，不是拿一个
数上下缩放：

| 档位 | 你的 Agent 读什么 | 50 工具 | 255 工具 | 你放弃了什么 |
|---|---|---:|---:|---|
| 默认 | 每个工具的完整 JSON Schema | 14,113 | 71,929 | 什么都不放弃——这就是你今天一直在付的账单 |
| `--slim` | 名字 + 参数类型 | 1,624 | 8,282 | 描述和约束 |
| `--compact` | 只有名字 | **114** | **581** | 除了名字全都放弃 |

省下来的比例不随规模缩水——`--slim` 两档都是 −88.5%，`--compact` 两档都是 −99.2%，
全部实测。随规模长大的是**赌注**：50 个工具
占 128K 窗口的 11%，255 个占 56%。而且每开一个新 Agent 都要重发一遍清单，按每天 20 次、
每百万输入 token $3 算，光是"读"这一步，小配置**每月 $25**，大配置**每月 $128**。

<p align="center">
  <img src="https://raw.githubusercontent.com/activeing123/mcptoon/main/assets/token-savings.svg" width="700" alt="同一份 255 工具配置的柱状图：原始 JSON schema 71,929 tokens，slim 8,282，compact 581">
</p>

这些说明书留在磁盘上的 `~/.mcptoon/config.json` 里，你的 Agent 不主动要就永远读不到。
这就是全部机关，也是为什么它**不是压缩**：压缩器把完整载荷送进窗口、之后再解包，
成本最终还是要落地。mcptoon 干脆不发。想要完整 schema 时，`--json` 随时都在。

**需要真说明书、但还想省钱？** `mcptoon serve` 返回的是**精简但仍然合法**的
JSON Schema——`type`、`properties`、`required` 和一句话描述都保留，任何 MCP 客户端
照样能正确调用工具；被剪掉的是 `examples`、`$ref`、`format`、`pattern` 和那些 500 字的
长描述，而参数校验用的是 mcptoon 中间层里的**完整** schema，转发给底层服务器之前就拦。
这一档能省多少，取决于你的服务器描述写得多啰嗦——**量你自己的配置，别信任何现成数字**。

> **关于数字。** 本 README 早期版本宣传过 97%，后来又写 99.8% / 123 tokens。两个都错：
> 123 是我们自家 benchmark 脚本把清单截断到 30 条产生的伪影，不是完整名字目录。
> 上面这些是校准后、可复现的数字，而且是**我们自己审计出来的**（提交 `9760bbc`），
> 不是读者发现的——所以这次修正连着测试一起进仓库：某个作废数字一旦回来，CI 就红。
> 如果你又发现对不上的地方，
> [开个 issue](https://github.com/activeing123/mcptoon/issues)。

---

## 这些 token 到底花在哪

"14,113 → 114" 是一个数字在替整个论证站岗。这里是一份工具清单**物理上**由什么组成——
用同一个分词器逐字段量，样本是这台机器上的 12 工具真实缓存：

| 一个工具条目的组成部分 | tokens | 占账单 |
|---|---:|---:|
| 工具的**名字** | 26 | **2.2%** |
| 给人看的描述 | 232 | 19.9% |
| 参数 schema（`type`、`properties`、`required`） | 635 | **54.5%** |
| JSON 键名、花括号、每个工具的信封 | 273 | 23.4% |
| **合计** | **1,166** | 100% |

掉出来两件事，都不是大家以为的那件。

**名字只占账单的 2.2%。** Agent 用来*决定*该用哪个工具的全部信息，花掉它百分之二。
剩下 97.8% 是它*正确调用*一个工具所需的信息——而它只需要这一件事的那**一个**工具，
不是十二个，更不是二百五十五个。mcptoon 的全部机关就是把后一半从"开场白"变成"要了再查"。

**贵的不是文字。** 描述占 19.9%，参数 schema 占 54.5%。账单的大头是机器形状的 JSON——
`{"type":"string","description":…}` 给每个工具的每个参数重复一遍。这也解释了为什么
`--slim` 还能省 88.5%：它砍掉文字、留下骨架，而骨架本来就是更贵的那一半。

这个样本很小、而且是我们自己的：12 个工具，被一个浏览器服务器占多数。请把百分比当成
成本的**形状**，不是你的数字。你的形状取决于你那些服务器描述写得多啰嗦。

### 省下来的是一个比率，永远不是一个固定数

与上面表格同源，实测每工具 token 数：

| 配置 | raw 每工具 | `--compact` 每工具 |
|---|---:|---:|
| 5 工具 | 303.8 | 2.20 |
| 50 工具 | 282.3 | 2.28 |
| 255 工具 | 282.1 | 2.28 |
| 活的 12 工具缓存 | 97.2 | 3.50–4.58 |

raw 比率稳得惊人（两份基准配置都是 282 token/工具），所以计算器拿它当默认值。
名字索引的比率**不是**常数：基准配置 2.20，活缓存高到 4.58——因为名字长短不一，
`opencli_profile_list` 在索引里就是比 `echo` 贵。所以任何"N 个 token 封顶"式说法都是
错的；诚实的写法永远是**比率 × 你的工具数**。

### 每一档留下什么

| 档位 | 留下 | 砍掉 | 50 工具 | 255 工具 |
|---|---|---|---:|---:|
| 默认 | 全部 | — | 14,113 | 71,929 |
| `--slim` | 名字、参数名与类型 | 描述、枚举、约束 | 1,624 | 8,282 |
| `--compact` | 只有名字 | 其余一切 | **114** | **581** |
| `serve` | 精简但仍合法的 JSON Schema | `examples`、`$ref`、`format`、`pattern`、长文字 | 看你 | 看你 |

`serve` 放最后、而且故意不给数字：它省多少完全取决于你的服务器描述有多啰嗦，
我们宁可什么都不印，也不印一个你复现不出来的数。

### 同一张账单换成钱

写长一点，每一步你都能自己核：

```text
50 工具    raw 14,113 − compact 114  = 每次清单省 13,999 tokens
13,999     × 每天 20 次 × 30 天       = 每月 8,399,400 tokens
8,399,400  × 每百万输入 token $3      = 每月 $25.20
255 工具   raw 71,929 − compact 581  = 71,348  →  每月 $128.43
```

三个输入里有两个归你定：每天列几次（每来一个任务就重开一个 Agent，一天能列 20+ 次；
一个一直开着的聊天只列一次），以及你模型的输入单价。第一行是唯一属于我们的，
而且是实测。

> **误差棒，实测的。** 在一份活的 12 工具缓存上，真实节省量出来是 **96.1%**，
> 而计算器对同一份配置估的是 **97.5%**——乐观了 1.4 个百分点。小配置省得比模型说的
> 略少一点。大配置是直接量的，不是估的。

---

## 三大动作

**1 · `sync`——配一次就够**

```bash
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
mcptoon sync                 # 把原生配置写进每个检测到的 Agent
mcptoon sync --watch         # 你边改它边对齐
mcptoon sync --dry           # 预览要写什么
```

合并而非覆盖：你手工配好的服务器原地保留。漂移检测能抓住在 mcptoon 之外做的编辑。

**2 · `manifest`——一份名字清单，不是一摞说明书**

```bash
$ mcptoon manifest --compact
bsk-tools: resolve, map_list, map_get · echo: echo, add, delete_item
```

真实输出、真实配置。你的 Agent 拿到的是"有什么"的清单，定义留在磁盘上，等它要时再取。

**3 · `serve`——所有服务器只开一扇门**

```bash
mcptoon serve                  # stdio，单 Agent
mcptoon serve --listen :8080   # HTTP，多 Agent 或远程
```

所有已配置服务器合成一个 MCP 端点，带连接池和按 Agent 隔离的 API Key。

**而且这是别人没有的部分：你一行配置都不用手写。** 原生 MCP 意味着给每个 Agent 各改一份
JSON，而且格式各不相同——`claude_desktop_config.json`、`.claude.json`、
`.cursor/mcp.json`，如此类推。mcptoon 是你的 Agent 本来就会运行的程序：

```text
你：  "我们有哪些工具？然后把 https://example.com 抓下来总结一下。"
Agent: $ mcptoon manifest --compact
Agent: $ mcptoon call fetch fetch '{"url":"https://example.com"}'
```

能跑 shell 命令的 Agent，配置到此为止：没有 `mcpServers` 条目，没有插件 API，什么都不用
重启。不能跑的——Claude Desktop 和任何 GUI 客户端——由 `mcptoon sync` 替它写原生 JSON。
两条路加起来，**需要你亲手打字的配置文件是零个**。mcptoon 自己的清单在
`~/.mcptoon/config.json`，由 `mcptoon quickstart` 扫描本机已有配置填上。

这也是 mcptoon 能到达 MCP 到不了的地方的原因：shell 脚本、CI 流水线、cron 任务、aider、
纯终端环境——任何能执行命令的东西。

---

## 为什么是 CLI，不是库、也不是代理

MCP 的前提是：每一项能力都是一个*服务器*，而你的 Agent 必须被配置成能够到它。
正是这个前提，导致加一个工具就得给每个 Agent 各改一份 JSON、格式还各不相同、
然后全部重启——也导致每个 Agent 在干任何活之前，都要重付一次完整的 schema 成本。

命令行是所有 Agent 都已经有的那一个接口。模型是在数十亿条 CLI 样本上训练出来的，
它们不需要人教怎么用 `mcptoon`。而且这个形态本身就更便宜，这与 mcptoon 做了什么无关：

- Firecrawl 的基准：同一任务 **CLI 花 1,365 tokens，MCP 花 44,026——差 32 倍**（[出处](https://www.firecrawl.dev/blog/mcp-vs-cli)）
- Scalekit 的基准：CLI **便宜 10–32 倍，可靠性 100%，MCP 是 72%**（[出处](https://www.scalekit.com/blog/mcp-vs-cli-use)）

**为什么不做成库？** 库需要一个能 import 它的宿主进程，还得是宿主说的语言。CLI 只需要一个
shell——而这恰恰是每个 Agent、CI runner、cron 任务都已经有的东西。

**为什么不做成代理？** 代理是又一个要跑起来、再让 Agent 指向它的服务。mcptoon 零安装即可试用，
平时不挡路；真需要代理形态时，`mcptoon serve` 就是那个模式。

---

## 为什么这是个真问题（不是我们自己说的）

下面每一条都对照原页面逐字核验过：

| 来源 | 原文实际说了什么 |
|---|---|
| [Anthropic — Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | "reduces the token usage from 150,000 tokens to 2,000 tokens — a time and cost saving of 98.7%"（把 token 用量从 150,000 降到 2,000，节省 98.7%） |
| [Firecrawl — MCP vs CLI](https://www.firecrawl.dev/blog/mcp-vs-cli) | CLI "~200 tokens per command" vs MCP "~44K tokens (full schema loaded upfront)" |
| [Scalekit](https://www.scalekit.com/blog/mcp-vs-cli-use) | "CLI won on every efficiency metric — 10 to 32× cheaper, 100% reliable versus MCP's 72%" |
| [MCP-Zero（arXiv:2506.01056）](https://arxiv.org/abs/2506.01056) | 按需工具检索可实现与工具数量近乎无关的常数成本 |
| [ProMCP — ACL 2026 Findings](https://doi.org/10.18653/v1/2026.findings-acl.1967) | 对 MCP Agent 的 token 流与延迟成本做同行评审过的量化分析 |
| [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576) | MCP 官方在途提案，正打算削减 schema 冗余——上游已承认这个问题 |

测过这件事的不是我们一家；协议自己的工作组现在也在提修复方案。mcptoon 是**今天就能用**、
**一次覆盖所有 Agent**、不用等那个提案落地的那一个。

---

## MCP 规范兼容性（2026-07-28）

| 规范特性 | 状态 |
|---|---|
| 无状态自动协商 | ✅ |
| 结构化工具输出 | ✅ 原生解析 |
| MRTR 多轮补参 | ✅ |
| `server/discover` 探测 | ✅ |
| 长轮询 SSE 响应 | ✅ |
| 向后兼容（2024-10-07 → 2025-11-25） | ✅ |

规范发布按兼容性矩阵对待，不当 changelog 看：每一版都带对真实服务器的线路级测试。
详见 [DEVELOPERS.md](https://github.com/activeing123/mcptoon/blob/main/DEVELOPERS.md)。

## Agent Plugins 1.0.0

扫描、安装、同步这套跨厂商插件标准（Amazon / Cursor / Microsoft / OpenAI / Vercel）
到每个 Agent，一条命令：`mcptoon plugin install <目录>`——包括没有原生插件加载器的
Agent。

## 安全，应用于每一次调用

MCP 服务器在你机器上跑代码，并把任意文本送回你 Agent 的上下文。mcptoon 在它进去之前
逐条检查：

| 检查项 | 拦什么 |
|---|---|
| 提示词注入 | 藏在工具输出里的 `"ignore previous instructions"` |
| 凭据泄漏 | 输出里的 `sk-…`、`AKIA…`、`ghp_…` 特征 |
| 危险操作 | 除非你显式传 `--destructive`，否则拦 `delete` / `drop` / `purge` |

零依赖本身就是安全叙事的一部分：没有 npm 子树、没有 postinstall 脚本、要审计的只有
11,400 行可读 Python。无遥测、无统计、无外呼。API Key 从你的配置或环境变量透传，
mcptoon 从不存储。

## 支持哪些 Agent

**Claude Desktop · Claude Code · Cursor · Cline · Windsurf · VS Code Copilot · Codex ·
Gemini CLI · OpenCode**——外加 aider、shell 脚本、CI 任务，以及任何能执行命令的东西，
包括完全没有 MCP 支持的环境。

最后那半句才是重点：正因为 mcptoon 首先是个 CLI，它才能走到 MCP 客户端到不了的地方。

<details markdown="1">
<summary><strong>这和逐 Agent 配置、或者工具搜索代理有什么区别？</strong></summary>

| | 逐 Agent 配置 | 工具搜索代理 | mcptoon |
|---|---|---|---|
| Agent 侧设置 | 每个 Agent 改 JSON + 重启 | 跑一个服务，再逐个指向它 | **零——它就是一条命令** |
| 要维护的文件 | 每个 Agent 一份 | 每个 Agent 一份 | **一份，同步到各处** |
| 发现成本 | 完整 schema | 先搜索，按需加载 | **名字目录；schema 永不出盘** |
| 死服务器检测 | — | 看实现 | 内建，带 CI 友好退出码 |
| 输出检查 | — | 看实现 | 每次调用都做注入 + 泄漏检查 |
| 接入成本 | 需要原生支持 | 要跑一个服务 | `pip install mcptoon` |

它们还能叠加：想要代理形态时用 `serve` 模式就行。

</details>

## 值得问的问题

### 这不就是压缩吗？
不是。压缩把完整载荷送进上下文、之后再解包——成本最终仍要落地。mcptoon 干脆不发
schema：它留在磁盘上，你要的时候 `--json` 随时给。

### Claude Code 不是已经延迟加载工具了？
是，而且两者可叠加。延迟加载决定定义*什么时候*进上下文，只管一个 Agent。mcptoon
决定一次清单*值多少钱*，一次覆盖所有 Agent，还额外提供 sync、health 和输出检查。

### 99.2% 是不是格式花招？
不是 `null` → `∅` 这类替换。那个误解来自早期 TOON 风格实验，那些替换在 v0.3.0 就被
删掉了，因为 tiktoken 证明其中两个比原样更贵。可选的 `--toon` 工具*结果*编码再省约
34%，默认关闭。

### 我少装几个 MCP 服务器不行吗？
行——这正是今天 MCP 用户在做的取舍：为了腾出上下文先卸一个，等要用那周再装回来。
它管用，但也正因为如此，上面那一列「50 工具」比「255 工具」更值得你看。mcptoon 让你
全都留着，窗口里还剩得下干活的地方。

### 我要把 API Key 交给它吗？
不注册、不遥测、不外呼。Key 从你自己的配置或环境变量透传，mcptoon 从不存储。而且能
藏东西的地方也少：11,400 行纯标准库 Python，零第三方 import 是评审阶段的硬规则。

### 我到底放弃了什么？
`--compact` 放弃名字以外的一切——Agent 要先要一份 schema 再来组参数。`--slim` 放弃
描述和约束。两个都是同一条命令上的单次开关，所以这是你按 Agent 逐个拧的旋钮，
不是一次迁移。

### 跟 McpHub 之类的 MCP 网关有什么不同？
网关是一个你要跑起来、然后把 Agent 指过去的服务。比如
[mcphub](https://github.com/samanhappy/mcphub)，它自己存一份服务器清单，对外提供
`http://localhost:3000/mcp`（还有 `/mcp/{group}`、`/mcp/{server}` 路由），每个 Agent
都要加一条指向它的配置。团队想要一个可审计的大门时，那是对的形态。mcptoon 没有门可以
指：能跑 shell 命令的 Agent 直接敲 `mcptoon call <server.tool>`，所以没有服务要养，
也没有逐 Agent 的条目要加。token 账单的差别也在同一处——网关把多个服务器聚合到一个
端点后面，Agent 仍然要从它那里收到合并后的 `tools/list`。**聚合不会让清单变短，
不发它才会。**

### 所以你们到底有没有配置文件？
有：`~/.mcptoon/config.json`。它是扫描本机已有配置写出来的——`mcptoon quickstart`
会读 Claude Desktop、Cursor、Cline、Windsurf 的配置，加上环境变量和本地工具——
不是你写的。而不能跑 shell 命令的 Agent，由 `mcptoon sync` 替它写原生 JSON。
本 README 的主张是"**你从来不用手写配置文件**"，这句话经得起 `ls ~/.mcptoon`；
"没有配置文件"经不起，所以不说。

<details markdown="1">
<summary><strong>诚实局限</strong></summary>

- `--compact` 只列工具**名字**——没有描述和参数细节。要签名用 `--slim`，要全部用 `--json`。
- token 数用 tiktoken `cl100k_base` 量。其他分词器会有差异（±10–25%）；主要那笔节省——
  schema 不进上下文——与分词器无关。
- 百分比取决于你的工具集——配置越小摊得越薄。在一份 12 工具的配置上我们量到 −96.1%，不是 −99.2%。
- 每次 stdio 调用会起一个进程（冷启动约 300ms）。热路径请用 `serve` 模式。
- 终端优先。没有 GUI。

</details>

---

## 开发者

```python
from mcptoon.client import MCPClient

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    result = c.call_tool("fetch", {"url": "https://example.com"})
```

```bash
git clone https://github.com/activeing123/mcptoon.git && cd mcptoon
pip install -e . --no-build-isolation && pip install pytest
python -m pytest tests/ -v          # 738 passed, 1 skipped
```

零第三方 import 是评审阶段强制的硬规则；新行为必须带测试。11,400 行 Python、
21 个模块——见
[CONTRIBUTING.md](https://github.com/activeing123/mcptoon/blob/main/CONTRIBUTING.md)。

## 许可证

Apache 2.0——见
[LICENSE](https://github.com/activeing123/mcptoon/blob/main/LICENSE) 与
[NOTICE](https://github.com/activeing123/mcptoon/blob/main/NOTICE)。

<div align="center" markdown="1">

*Model Context Protocol 的独立第三方客户端，与 Anthropic、Cursor、微软均无关联。*

**不信？很好。`pip install mcptoon && mcptoon demo` 只要 30 秒，跑在你自己机器上。**

<sub>点个 ⭐，是让下一个人找到这份 README 的唯一办法。</sub>

</div>
