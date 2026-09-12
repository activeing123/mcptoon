<div align="center" markdown="1">

# mcptoon

**本地添加 1,000 个 MCP 工具，也不用担心 token 上下文。**

mcptoon 是一个 128KB 的小命令，把 MCP 工具 schema 挡在 Agent 上下文之外。
发现工具直接省 **71,929 → 581 token（255 个工具，实测 −99.2%）**；调用结果加
`--toon` 再省约 34%。每条命令装一个服务器，零配置，本机所有 Agent 共享同一套工具。

[![GitHub Stars](https://img.shields.io/github/stars/activeing123/mcptoon?style=social)](https://github.com/activeing123/mcptoon/stargazers)
[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&color=1a7f37)](https://pypi.org/project/mcptoon/)
[![CI](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml/badge.svg)](https://github.com/activeing123/mcptoon/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/Tests-815%20passed-brightgreen)](#贡献)
[![MCP Spec](https://img.shields.io/badge/MCP_Spec-2026--07--28-blueviolet)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](https://github.com/activeing123/mcptoon/blob/main/LICENSE)

**👉 [English](README.md) · [开发者文档](DEVELOPERS.md) · [反馈问题](https://github.com/activeing123/mcptoon/issues)**

![Benchmark: 255 tools, 71,929 → 581 tokens](assets/benchmark.svg)

</div>

```bash
pip install mcptoon

# 加任何 MCP 服务器——一条命令：
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# 你的 Agent 实际读到的（只有名字——581 token，而不是 71,929）：
mcptoon manifest
```

**工具是你自己的。** mcptoon 不预装任何工具——它只是遥控器，不是运行时。
你想用的 MCP 服务器，用一条命令自己装（npm/pip/网址都行），装哪个、装多少都是你的事。
哪天不用 mcptoon 了，直接删掉它——你的 MCP 服务器是独立的，照常工作，一个都不会少。

**Mcptoon 是 MCP 工具的原生解耦层**，解决 MCP 协议工具列表大量消耗 token、多 AI Agent
重复配置工具的痛点。0 配置开箱即用：自动扫描接管本机所有 Agent——Claude Code、Cursor、
Codex、脚本、CI——的 MCP 工具，工具实例全局共享，大幅削减 token 开销。

</div>

---

## 这不是我们自说自话

上面那些数字是我们量的，但"schema 全量进上下文很贵"这件事，不是只有我们这么说：

- [Anthropic 官方](https://www.anthropic.com/engineering/code-execution-with-mcp)：工具 schema 全量进上下文是真实痛点，一个例子就从 150,000 token 降到 2,000（省 98.7%）
- [Firecrawl 基准](https://www.firecrawl.dev/blog/mcp-vs-cli)：同一任务，CLI 花 1,365 token，MCP 花 44,026——差 32 倍（全量 schema 一次性加载）
- [Scalekit 基准](https://www.scalekit.com/blog/mcp-vs-cli-use)：CLI 便宜 10–32 倍、可靠性 100%，MCP 只有 72%
- [MCP-Zero（arXiv:2506.01056）](https://arxiv.org/abs/2506.01056)：按需工具检索可实现与工具数近乎无关的常数成本
- [SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576)：MCP 官方在途提案，正打算削减 schema 冗余——上游自己承认了这个问题

测过这件事的不是我们一家。mcptoon 是**今天就能用**、一次覆盖所有 Agent 的那一个。

---

## 30 秒上手

```bash
pip install mcptoon                          # 纯标准库，128KB，零依赖

# 添加任意 MCP 服务器——一条命令：
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# 查看所有可用工具（默认就是名字索引，255 个工具只需 581 token）：
mcptoon manifest

# 调用工具（默认输出 JSON；想更省加 --toon）：
mcptoon call fetch fetch '{"url":"https://example.com"}'
```

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

就这些。不用手写 JSON 配置。不用调试 MCP 协议。不污染上下文窗口。wheel 只有 128KB、
零依赖；mcptoon 本体不需要任何 API key，也不向任何云端打电话——服务费 $0，一切都在
你自己的机器上跑。

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

## 行业验证了问题——但把解法锁在了门后

工具上下文太重，不再是小众抱怨——它已经是官方盖章的工程问题，同一个答案反复出现：

- **Anthropic**：[Tool Search Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
  把工具定义改为按需加载；[Programmatic Tool Calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
  把编排挪进代码。两者都是 Claude 平台 beta。
- **MuleSoft**：[MCP Payload Optimization](https://docs.mulesoft.com/gateway/latest/policies-included-mcp-payload-optimization)
  把「清洗 → 蒸馏 → 压缩」产品化（压缩环节是 TOON）。只在企业网关里，
  支持到 MCP 2025-06-18。

| 解法 | 跑在哪 | 门槛 |
|---|---|---|
| Tool Search Tool / PTC | Claude 平台 beta | 只管*定义*和编排；其他所有 agent 上，工具*结果*仍逐 token 进上下文 |
| MuleSoft 网关 | 企业网关 | 要过 MuleSoft；MCP 规范落后一代 |
| **mcptoon** | **任何能跑 shell 命令的 agent** | 无——128KB，不要密钥、不要代理进程，MCP 2026-07-28 GA |

方向已定。mcptoon 是这个答案里**今天就能跑、每个 agent 一次到位**的版本——
「结果侧」的纪律，不收平台税，不收网关税。

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
每次安装给 mcptoon 本体**新增 0 KB**——CLI 保持 128KB、零依赖，因为服务器是你的
机器直接运行的外部进程，不是打包进 mcptoon 的代码。四个步骤、一条命令、不用重启 Agent。

**支持任何 MCP 服务器：**

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest    # 直接就能用
```

---

## 作为 Agent 技能安装（支持 80+ Agent）

通过开放 Agent 技能生态，教会你的 Agent *使用* mcptoon——技能会被
Claude Code、Cursor、Codex、Cline、Windsurf 等 75+ Agent 自动识别：

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
工具。不能跑的 GUI Agent？`mcptoon sync` 把原生 JSON 写进它们各自的位置。

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

mcptoon 省 token 分两笔账，先分清是哪一段再对数字。先说短版：255 个工具的原生发现
要吃掉 71,929 token——128K 窗口的一半以上——同一套工具走名称索引只要 581 token，
省 99.2%；结果这一侧，`--toon` 在实测集上比 JSON 小 34.0–34.2%。两行都是我们的实测配置
（tiktoken `cl100k_base`，`assets/benchmark_tiktoken.json`），不是按比例放大的估算。

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
想多给 Agent 一点信息？`--full`（名字+参数类型）省 88.5%，`--json`（完整 schema）
是基准线。

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

**用 mcptoon --full**（6 token，包含参数信息）：

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
mcptoon list                    # 查看已配置服务器
mcptoon manifest                # 所有工具名（默认即紧凑档，255 个工具只需 581 token）
mcptoon manifest --full         # 工具 schema 带参数（比原生 schema 省 88.5%）
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

mcptoon 是 **CLI 工具**，不是 MCP 客户端库。你的 Agent 不连接 MCP 服务器——它跑
`mcptoon` 命令。Schema 存在磁盘上的 `~/.mcptoon/config.json` 里，默认不进上下文窗口。

**两层解耦：**

```
第 1 层: mcptoon CLI (128KB, 零依赖)
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
python -m pytest tests/ -v   # 814 passed, 1 skipped
```

零依赖是硬规则，我们的测试门槛是每次改动先跑绿全套 814 个测试。见
[CONTRIBUTING.md](CONTRIBUTING.md)、[DEVELOPERS.md](DEVELOPERS.md)。

项目本体：11,750 行 Python、21 个模块，零第三方依赖——供应链里 0 个要审计的环节。

---

## 生态

- **[ToonDeck](https://github.com/activeing123/toondeck)** — mcptoon 的 GUI 控制台（pre-alpha）：MCP server、工具、模型、API key 一桌管理，引擎就是 mcptoon。不想敲命令？用图形界面的它。

---

<div align="center">

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*

**省下的是你自己的 token。点个 star——小工具就是靠这个被更多人找到的。**

</div>
