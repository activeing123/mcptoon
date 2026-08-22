<div align="center">

# mcptoon

**本地装 1,000 个 MCP 工具。token 不浪费，配置不用管，换 Agent 不用重来。**

mcptoon 站在你的 AI Agent 和 MCP 服务器之间。装 1,000 个工具——上下文窗口还是空的。工具 schema 永远不进上下文，只有你要的紧凑结果会进去，而且比 JSON 小 30-93%。一个配置文件通吃所有 Agent。换 Agent，配置跟着走。删掉 mcptoon，服务器照常运行。

**工具是你自己的。** mcptoon 不携带任何服务器——只是一个 ~250KB 的 CLI。你按需从 npm/pip/HTTP 添加想要的服务器，一条命令加一个。

[![PyPI](https://img.shields.io/pypi/v/mcptoon?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/mcptoon/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/mcptoon/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/依赖-零-orange)](#隐私)
[![Tests](https://img.shields.io/badge/Tests-486%20passed-brightgreen)](#贡献)

**👉 `pip install mcptoon`** · [English](README.md) · [中文文档](README.zh-CN.md) · [反馈问题](https://github.com/activeing123/mcptoon/issues)

</div>

## mcptoon 对比你现在的 MCP 管理器

| | 你现在的 MCP 管理器 | mcptoon |
|---|---|---|
| **agent 配置** | 在 agent 配置文件里编辑 `mcpServers` JSON。一个拼写错误全挂。 | 跑 `mcptoon` shell 命令。不用碰 agent 配置。 |
| **schema token** | 启动时所有 schema 加载进上下文。10 个服务器 = 5万-10万 token 没了。 | 零。schema 不进上下文。只有你请求的压缩结果才进。 |
| **全新 agent** | 下载 agent。找配置文件。编辑 JSON。加服务器。重启。每个 agent 来一遍。 | 下载 agent。跑 `mcptoon call`。1000 个工具秒就绪。完事。 |
| **切换 agent** | 每个 agent 有自己的 MCP 配置格式。迁移靠手动，疼。 | 无需配置，默认任意全新 agent 直接调用。 |
| **服务器生命周期** | agent 启动时所有配置的服务器都启动。不用也在跑。吃内存。 | 懒加载。只有调用工具时才启动。调用前 0 个在跑。 |
| **添加服务器** | 找包名。编辑 JSON。检查语法。重启 agent。 | `mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch` |
| **返回结果大小** | 完整 JSON 响应直接进你的上下文窗口。 | TOON/SLIM 编码。比 JSON 小 30-93%。 |
| **100 个服务器** | 35万+ token 的 schema。还没开始干活上下文就满了。 | 0 token schema。上下文干干净净。工具在磁盘上等着。 |
| **安全防护** | 看 agent 实现。大多数没有内置防护。 | 提示词注入拦截 + 凭证泄露检测 + 危险操作阻断。 |

| | |
|---|---|
| **90,804** token | 255 个工具 schema 进上下文（你现在的 MCP 管理器） |
| **117** token | 255 个工具用 mcptoon `--compact`（少 99.9%） |
| **0** token | mcptoon 模式下 schema 占用（永远是 0） |

**一句话：** 你现在的 MCP 管理器拿上下文窗口交 schema 税，不管用不用都得扣。mcptoon 把工具放在 agent 外面，按需调用，压缩结果。你的上下文窗口是你自己的。

<div align="center">

![Benchmark: 255 tools, 90,804 → 117 tokens (tiktoken cl100k_base)](assets/benchmark.svg)

![Demo: mcptoon in action](assets/demo.gif)

</div>

---

## 30 秒上手

```bash
pip install mcptoon                          # 零依赖，~250KB

# 添加任意 MCP 服务器——一条命令：
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch

# 查看所有可用工具（255 个工具只需 117 token）：
mcptoon manifest --compact

# 调用工具——输出比 JSON 小 30-93%：
mcptoon call fetch fetch '{"url":"https://example.com"}' --toon
```

**或者让 mcptoon 自动发现你机器上已有的服务器：**

```bash
mcptoon quickstart     # 自动发现 + 配置 + 展示工具——一条命令搞定
```

就这些。不用编辑 JSON 配置。不用调试 MCP 协议。不污染上下文窗口。

---

## 谁在用

<!-- 在这里添加你的项目 — 欢迎 PR！ -->

*正在用 mcptoon 构建项目？[开个 issue](https://github.com/activeing123/mcptoon/issues) 登记在这里。*

---

## 解决什么问题？

每个 MCP Agent（Claude Code、Cursor、Codex 等）都会在开始工作前把**所有工具的 schema 塞进你的上下文窗口**：

```
10 个 MCP 服务器 → 50,000-100,000+ token 的 JSON schema → 128K 上下文：40-80% 没了
100 个服务器 → 350,000+ token → 上下文窗口死了
```

于是你不用的时候卸载服务器，用的时候再加载。来回折腾。想加个新服务器还得手写 JSON 配置——少个逗号就全崩了。

**mcptoon 解决这个问题。** 你的 MCP 服务器都配着，但它们的 schema **永远不进 Agent 的上下文**。Agent 只跑 `mcptoon` 命令，只有你要的紧凑结果进上下文——TOON 编码让它比 JSON 小 30-93%。

```
不用 mcptoon：255 个工具 → 90,804 token 的 schema 占满上下文（tiktoken cl100k_base）
用 mcptoon：  255 个工具 → 6,174 token（SLIM 格式）。省了 93%。
             255 个工具 → 117 token（compact，仅工具名）。省了 99.9%。
```

---

## 安装 MCP 服务器——每条一个命令

```bash
# 从 npm 安装（大部分 MCP 服务器在这里）：
mcptoon install brave-search --npm @anthropic/mcp-server-brave-search

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

**支持任何 MCP 服务器：**

```bash
mcptoon add my-server --stdio npx -y @any/mcp-package
mcptoon manifest --toon    # 直接就能用
```

---

## 兼容 Shell 型 AI Agent

mcptoon 是 **CLI 工具，不是 MCP Server**。它不能填入 `mcpServers` JSON 配置。你的 Agent 通过 shell 命令调用 `mcptoon`——schema 不进上下文。

**兼容（能跑 shell 的 Agent）：**

| Agent | 怎么用 |
|---|---|
| **Claude Code** | 在 SKILL.md 里写 `mcptoon` 命令 |
| **Codex (OpenAI)** | 在 AGENTS.md 里加 `mcptoon` |
| **Cursor** | 在 .cursorrules 里加 `mcptoon`（Agent 生成 shell 命令） |
| **OpenCode** | 在自定义命令里用 `mcptoon` |
| **任何 Agent** | 能跑 shell 命令就能调 `mcptoon` |

**不能替代原生 MCP 配置：**
- Cursor 的 `mcpServers` 设置 → 不受影响（mcptoon 是独立的，不是 server 条目）
- Claude Desktop 的 `claude_desktop_config.json` → 不受影响
- mcptoon 不输出 MCP JSON-RPC 协议流——它是客户端，不是服务端

在 `~/.mcptoon/config.json` 配置一次，所有 Agent 共享同样的服务器和工具。换 Agent？配置跟着你走。

```bash
export MCPTOON_AGENT_TYPE=claude   # 所有调用自动用 --toon
```

你的 AI 甚至可以自己加工具——不需要人介入：

```bash
# Agent 干活干到一半需要 GitHub 访问？它自己跑：
mcptoon add github --stdio npx -y @modelcontextprotocol/server-github
mcptoon call github search_repos '{"query":"mcp"}' --toon
# 完事。不用编辑 JSON。不用重启。上下文不丢。
```

---

## 数据

### Token 节省（255 个工具，tiktoken cl100k_base）

所有数据来自 `tiktoken.get_encoding("cl100k_base")`——OpenAI 官方 BPE 分词器。

| 工具数 | JSON | TOON | SLIM | Compact |
|-------|------|------|------|---------|
| 5 | 1,897 | 1,167 (-39%) | 111 (-94%) | 16 (-99%) |
| 50 | 17,790 | 10,688 (-40%) | 1,203 (-93%) | 117 (-99%) |
| 255 | **90,804** | **54,649 (-40%)** | **6,174 (-93%)** | **117 (-99.9%)** |

- `--compact` → 工具名：**省 99.9%**
- `--slim` → 工具 schema 带参数：**省 93%**
- `--toon` → 结构化结果（可逆）：**省 30-40%**

<details>
<summary><b>什么是 TOON？mcptoon 为什么用 TOON？</b></summary>

**TOON (Token-Oriented Object Notation)** 是一个开放数据格式规范，由 [Johann Schopplich](https://github.com/johannschopplich) 创建（[toon-format/toon](https://github.com/toon-format/toon)，25K+ stars）。专为减少结构化数据喂给 LLM 时的 token 消耗而设计。

**为什么用 TOON 而不是 JSON/YAML/CSV？**

| 格式 | 对 LLM 的问题 |
|--------|-----------------|
| JSON | 花括号 `{}`、方括号 `[]`、引号 `""`、逗号——每个都是独立的 BPE token。255 个工具 schema = ~91K token。 |
| YAML | 缩进敏感，LLM 难以正确生成，没有数组长度提示。 |
| CSV | 不能嵌套，没有键值对，没有类型信息。 |
| TOON | YAML 风格键 + CSV 风格数组 + 长度提示 `[N]` + 类型字面量。比 JSON 少 30-40% token。 |

**mcptoon 使用了 TOON spec v4.1 的哪些部分：**

| 特性 | 用了？ | 示例 |
|---------|-------|---------|
| YAML 风格对象 (`key: value`) | ✅ | `name: search` |
| 表格数组 (`[N,]{fields}: rows`) | ✅ | `[2,]{id,name}:\n  1,Alice\n  2,Bob` |
| 内联标量数组 (`key[N]: v1,v2,v3`) | ✅ | `tags[3]: ai,ml,nlp` |
| 嵌套对象（缩进） | ✅ | `config:\n  host: localhost` |
| 类型字面量 (`true`/`false`/`null`) | ✅ | `active: true` |
| 字符串引号（仅在需要时） | ✅ | `desc: "hello, world"` |
| 反斜杠转义（引号字符串内） | ✅ | `desc: "say \\"hi\\""` |
| 长度标记（`#` 前缀） | ❌ 不需要 | — |
| 管道/制表符分隔符 | ❌ 不需要 | 只用逗号分隔符 |
| 根标量值 | ❌ 不需要 | MCP 数据总是对象/数组 |

**兼容性：**

- 编码器/解码器：**从 [python-toon](https://github.com/xaviviro/python-toon) v0.1.1 vendor**（MIT 许可证，作者 Xavi Vinaixa）——规范兼容实现
- 官方 TypeScript 参考实现：[toon-format/toon](https://github.com/toon-format/toon)（25K+ stars）
- 可逆：`decode(encode(x)) == x`，对所有 JSON 可序列化数据成立
- 非严格解码模式（对真实 MCP 输出的宽松解析）
- **已知细微差异：** 空容器输出 `{}`/`[]`（而规范输出空字符串）；3 个边界解码模式（键表格形式、嵌套字段组）——对 MCP 使用场景无影响
- 47/52 兼容性测试通过官方规范

**为什么不直接用官方 `toon-format` PyPI 包？**

官方 Python 实现（[toon-format/toon-python](https://github.com/toon-format/toon-python)）目前处于 beta 阶段——编码器会抛出 `NotImplementedError`。我们 vendor 了社区实现（`python-toon`，作者 Xavi Vinaixa），它是可用的且规范兼容的。等官方 Python 编码器稳定后我们会切换。

**TOON vs SLIM vs Compact——有什么区别？**

| 格式 | 来源 | 用途 | 节省 |
|--------|--------|----------|---------|
| `--toon` | 开放规范 (toon-format/toon v4.1) | 通用结构化输出，可逆 | 比 JSON 少 30-40% |
| `--slim` | mcptoon 专用 | 仅工具 schema (`name\|param:type*`) | 比 JSON 少 93% |
| `--compact` | mcptoon 专用 | 仅工具名 | 比 JSON 少 99.9% |

SLIM 和 Compact **不是** TOON 规范的一部分。它们是 mcptoon 专用的工具发现优化。TOON 是工具调用结果的通用格式。

</details>

复现：`pip install tiktoken && python _benchmark.py` → 输出 `assets/benchmark_data.json`

### 对比实例

**不用 mcptoon**（所有 MCP 客户端返回的——287 token）：

```json
[{"name":"search_web","description":"Search the web for information",
"inputSchema":{"type":"object","properties":{"query":{"type":"string","description":"Search query"}}}}]
```

**用 mcptoon**（5 token）：

```
search_web
```

**用 mcptoon --slim**（14 token，包含参数信息）：

```
search_web|query:s*
```

---

## 安全

三层防护，全部内置：

| 层 | 做什么 | 示例 |
|-------|-------------|---------|
| **危险操作拦截** | 默认拦截 `delete`/`drop`/`purge` | `docker_remove` → 拦截，除非加 `--destructive` |
| **Prompt 注入防护** | 扫描结果中的注入模式 | `"ignore previous instructions"` → 拦截 |
| **凭据泄露检测** | 扫描结果中的暴露 key/token | `sk-abc...xyz` → 拦截，不进 Agent 上下文 |

- **没有遥测。** 没有分析、没有崩溃报告、没有回传。
- **不存凭证。** API key 从你的配置或环境变量直接传递。
- **没有依赖。** 纯 Python 标准库。没有供应链要审计。

---

## 全部命令

```bash
mcptoon quickstart              # 一键上手（发现 + 配置 + 展示工具）
mcptoon init --auto             # 自动发现机器上的 MCP 服务器
mcptoon add <name> --stdio npx -y <package>   # 添加任意 MCP 服务器
mcptoon install <name> --npm <package>        # 安装 + 自动生成 handler
mcptoon list                    # 查看已配置服务器
mcptoon manifest --compact      # 所有工具名（255 个工具只需 117 token）
mcptoon manifest --slim         # 工具 schema（比 JSON 小 93%）
mcptoon manifest --toon         # 标准 TOON 格式
mcptoon inspect <server> <tool> # 查看某个工具的 schema
mcptoon search <query>          # 跨服务器搜索工具
mcptoon call <server> <tool> '{"args":"here"}' --toon   # 调用工具
mcptoon call --auto <tool> '{"args":"here"}' --toon     # 自动找服务器
mcptoon doctor                  # 自检：Python、配置、连通性
mcptoon usage                   # 本地调用统计
mcptoon completion bash         # Shell 补全（bash/zsh/fish/ps）
```

### 输出格式

| Flag | 输出 | 节省 |
|---|---|---|
| `--compact` | 仅工具名 | 比 JSON **省 99.9%** (tiktoken) |
| `--slim` | 工具 schema (`name\|param:type*`) | 比 JSON **省 93%** (tiktoken) |
| `--toon` | 标准 TOON (vendored python-toon v0.1.1, toon-format v4.1) | 比 JSON **省 30-40%**，可逆 |
| `--json` | 标准 JSON | 基准线 |
| `--raw` | 原始响应 | 全量 |
| `--head N` | 仅前 N 条 | 可变 |
| `--max-chars N` | 截断到 N 字符 | 可变 |
| `--full` | 禁用默认 4000 字符截断 | 全量 |
| `--stdin` | 从 stdin 读参数（大 payload） | — |
| `--fallback-json` | TOON 编码出错时回退到 JSON | 安全网 |

> **`--fallback-json` 说明：** 只捕获编码层面的错误（如不支持的数据类型）。不检测 LLM 是否成功解析了输出——这是调用者的责任。

---

## 原理

mcptoon 是 **CLI 工具**，不是 MCP 客户端库，也不是 MCP Server。你的 Agent 不连接 MCP 服务器——它跑 `mcptoon` 命令。Schema 存在磁盘上的 `~/.mcptoon/config.json` 里，不进上下文窗口。

**架构边界：**
- mcptoon 是 **MCP Client**——内部通过 stdio/HTTP 连接 MCP 服务器
- mcptoon **不**对外暴露 MCP JSON-RPC 端点
- `--json` 输出是工具列表片段，不是完整的 MCP 协议消息（没有 `initialize`、`id`、`method` 字段）
- 要在 Cursor/Claude Desktop 原生 MCP 里用：单独配它们的 `mcpServers`。mcptoon 只适用于能跑 shell 的 Agent。

**两层解耦：**

```
第 1 层: mcptoon CLI (~250KB, 零依赖)
         在 Agent 的 shell 里运行。schema 永远不进上下文。
                    │
第 2 层: 实际 MCP 服务器 (npm/pip 包)
         只有调用工具时才启动。不用就零开销。
```

- 1,000 个服务器配好 → 0 个在运行，直到你用其中一个
- mcptoon 不携带任何服务器——你加你想要的，一条命令加一个
- 删掉 mcptoon？你的 MCP 服务器照常独立运行

---

## Python API

```python
from mcptoon.client import MCPClient
from mcptoon.output import toon_encode, toon_decode

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    print(toon_encode(tools))         # 紧凑 TOON 输出
    result = c.call_tool("fetch", {"url": "https://example.com"})
    print(toon_encode(result))        # 紧凑 TOON 输出
    decoded = toon_decode(toon_encode(result))
    assert decoded == result          # 可逆
```

---

## 架构

```
src/mcptoon/
├── cli.py        # CLI 入口 + 参数解析
├── client.py     # MCPClient — stdio + HTTP 传输
├── installer.py  # 一键 MCP 服务器安装 + 自动 handler 生成
├── router.py     # 工具路由 + 注入/凭据泄露检测
├── config.py     # 服务器配置 (JSON + TOML)
├── manifest.py   # 工具发现 + 跨服务器搜索
├── discover.py   # 零配置自动发现 (4 层)
├── output.py     # 标准 TOON (vendored python-toon) + compact/slim 渲染
├── toon_vendored.py  # Vendored 规范兼容 TOON 编码器/解码器 (MIT, python-toon v0.1.1)
├── cache.py      # Schema 缓存 (5分钟 TTL)
├── usage.py      # 本地用量统计
└── errors.py     # 结构化错误 + 修复建议
```

约 6,400 行。486 个测试。零第三方 import。约 250KB 源码。

## Docker

```bash
docker build -t mcptoon .
docker run --rm mcptoon help
docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --toon
```

`manifest`、`list`、`inspect`、`doctor` 直接能用。`call` 和 `add --stdio` 需要镜像里有服务器运行时（如 `npx`）。

## 贡献

```bash
git clone https://github.com/activeing123/mcptoon.git
cd mcptoon
pip install -e . --no-build-isolation
pip install pytest pytest-cov
python -m pytest tests/ -v   # 486 个测试, 0.5s
```

零依赖是硬规则。新功能需要测试。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Apache 2.0。见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。

---

<div align="center">

*mcptoon 是独立的第三方 MCP 客户端，不隶属于 Anthropic。*

**觉得有用？点个 star 帮更多人发现它。**

</div>
