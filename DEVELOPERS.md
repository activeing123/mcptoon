# DEVELOPERS.md — mcptoon 技术文档

> 面向开发者和进阶用户。普通小白请看 [README.md](./README.md)。
> English: this document is technical; the beginner-facing README is at [README.md](./README.md).

mcptoon: 一个零依赖、零配置、CLI 优先的跨 Agent MCP 管理网关。
`README.md` 面向小白，本文件是完整的技术说明。

- 版本：v0.7.23 · 1410 passed + 1 skipped · 0 依赖 · 227KB wheel · 28 模块 · Apache 2.0
- 仓库：https://github.com/activeing123/mcptoon
- PyPI：https://pypi.org/project/mcptoon/

---

## 定位（一句话）

大厂 MCP 做**供给端协议**（Host→Client→Server，连接多样化数据源）；
mcptoon 站在 MCP 之上，做**调用端/管理端**——跨 Agent 免配置 + token 效率 + 安全。

对比详见 [docs/comparison.md](docs/comparison.md)。

---

## 核心概念

- **一份配置，处处同步**：`~/.mcptoon/config.json`（或 TOML）为唯一事实来源，`sync` 合并写进所有检测到的 Agent，`--watch` 持续对齐。
- **名字索引，schema 不出盘**：`manifest --compact` 只给名字索引；schema 留在磁盘，从不进上下文。
- **一个入口，串多服务器**：`serve` 提供 stdio（单 Agent）与 HTTP（多 Agent / 远程）代理形态。

---

## 三大核心命令（The three moves）

### 1 · Configure once — `sync`

```bash
mcptoon add everything --stdio npx -y @modelcontextprotocol/server-everything
mcptoon sync               # 一份配置 → 所有检测到的 Agent
mcptoon sync --watch       # 持续同步，配置一变所有 Agent 自动跟上
mcptoon sync --dry         # 预览将写入什么，不动真格
mcptoon sync --agent cursor # 只同步某个 Agent
```

`sync` 是合并不是覆盖：手动配置的服务器原样保留。`--watch` 提供漂移检测 + 合并/严格双模式。

### 2 · Pay for names, not schemas — `manifest`

```bash
mcptoon manifest --compact   # 名字索引（255 工具 = 581 tokens），schema 不出磁盘
```

| 工具清单开销（tiktoken cl100k_base） | tokens | 对比原始 JSON |
|-------------------------------------|-------:|--------------:|
| 完整 JSON schema（255 工具 / 50 服务器） | 71,929 | — |
| `--slim`（名字+参数类型） | 8,282 | −88.5% |
| `--compact`（仅名字） | 581 | **−99.2%** |

复现：`python scripts/bench_tokens.py`（读 `~/.cache/mcptoon/schema_cache.json`，需 `pip install tiktoken`）。 这是一个旋钮不是开关：需要零歧义时切回 `--json`。

### 3 · One door in front of every server — `serve`

```json
"mcptoon": { "command": "mcptoon", "args": ["serve"] }
```

```bash
mcptoon serve                  # stdio，单 Agent
mcptoon serve --listen :8080   # HTTP，多 Agent / 远程
mcptoon serve --http           # 等价 --listen :8080
```

- 并行 manifest 加载（20 并发，100 服务器 ≈ 5s）
- 5 分钟 schema 缓存（`MCPTOON_CACHE_TTL` 可配）+ **内容指纹漂移检测**：每条缓存存一个由
  "工具名 + 各工具 required 列表" 算出的 sha256 短指纹（对畸形/`null inputSchema` 服务器做
  了防御）。`set_cached_tools` 在写回时比对指纹、**只有可调用面真变了才返回 True**；`serve`
  的并行刷新据此在工具集变化时打一条漂移日志（无需自己 diff）。实现见 `cache.py`
  （`tools_fingerprint`），消费方见 `serve._refresh_servers_in_parallel`，测试见 `tests/test_cache.py`。
- 单次调用 30s 超时（`MCPTOON_CALL_TIMEOUT` 可配），一台服务器卡死不拖垮会话
- HTTP `/mcp` 端点 + `/health` 健康检查，兼容 MCP HTTP transport

---

## 其余命令

| 命令 | 干什么 |
|------|--------|
| `mcptoon call <server> <tool> '{…}'` | 调任意服务器的任意工具 |
| `mcptoon call --auto <tool> '{…}'` | 只给工具名，自动找服务器 |
| `mcptoon health` | 哪些服务器活着/死了/多快，CI 里全死退出码 1 |
| `mcptoon install <name> --npm <pkg>` | 一条命令装服务器并自动发现工具 |
| `mcptoon search <query>` | 跨服务器模糊搜索（带相关性评分） |
| `mcptoon doctor` | 自检 Python、配置、连通性 |
| `mcptoon skills sync` | 一份技能真源 → 所有 Agent 的技能目录（链接，改一次处处生效） |
| `mcptoon skills add/remove` | 在真源里新建/下架技能（下架进墓地，可反悔） |
| `mcptoon skills list --usage` | 列出技能 + 各自被路由过几次 |
| `mcptoon config set footer off` | 关掉会话末尾那行"省了多少 token"的播报 |
| `mcptoon quickstart` | 检测并导入已有配置，列出全部工具 |
| `mcptoon demo` | 现场前后对比 token 数字 |
| `mcptoon demo-server` | 跑一个内置的零依赖 MCP server（11 个纯标准库工具，stdio） |

### · 内置演示服务 — `demo-server`

`demo_server.py` 是包内自带的一个真 MCP server：11 个工具全部只做纯计算（TOON 编解码、
格式对比、token 估算、schema 瘦身、manifest 索引、配置校验……），**不联网、不落盘、
不起子进程、不碰用户配置**，`tests/test_demo_server.py` 从源码层面把这几条钉死。

存在的理由只有一个：外部质量评分（Glama/TDQS）的容器是纯 Python 镜像，旧的演示种子
`npx -y @modelcontextprotocol/server-everything` 在里面**列不出任何工具**（tools/list = 0），
等于交了白卷。同一无 Node 沙箱里 A/B 实测：旧种子 0 个工具，`demo-server` 11 个。

```bash
mcptoon add demo --stdio python -m mcptoon demo-server   # 显式添加才会生效
```

它不改变"遥控器不是运行时"的定位：不会自动注册任何东西，`mcptoon serve` 在空配置下
仍然返回 0 个工具（proxy 语义未变）。工具描述是按 TDQS 六维评分表写的，其中可机械判定的
硬闸（空描述/同义反复描述/描述与 `readOnlyHint` 矛盾/优先级操纵话术）已进 CI。

---

## 技能目录管理（Skills as a managed catalog）

技能和 MCP 服务器是同一类东西：**一个真源，多个 Agent 视图**。`sync` 早就用这个模型管
服务器，`skills sync` 把它套到技能上——所以两个子系统不各造轮子。

```bash
mcptoon skills sync ~/skills                 # 真源 → 所有 Agent 技能目录（默认建链接）
mcptoon skills sync ~/skills --dry           # 只打印计划，一个字不写
mcptoon skills sync ~/skills --copy          # 强制真拷贝（无链接的文件系统）
mcptoon skills add my-skill --desc "…"       # 在真源里新建
mcptoon skills remove my-skill               # 下架（进 _archive/removed，可反悔）
mcptoon skills list --usage                  # 列出技能 + 各自被路由过几次
```

**视图用链接（Windows 上是 junction，无需管理员）**：改一次真源，所有 Agent 立刻看到，
不存在第二份副本可漂移。三条安全纪律，每条都对应一种会毁用户数据的朴素做法：

1. **链接位置上出现真目录 = 漂移** → 归档进 `_archive/`，**永不删除**（可能是用户手写的）。
2. **下架只在真源发生**，视图下次 sync 自动跟随；`remove` 是 `mv` 不是 `rm`。
3. **别的管理器拥有的链接** → 报告并跳过，绝不抢夺（本机 `tongbu-skills` 就管着同一批目录）。

**使用计数只统计经 mcptoon 路由的**（`resolve`/`route`）；Agent 直接加载的技能这里看不见，
所以 `list --usage` 自己会说这句话，而不是假装全覆盖。

---

## 存在感：网关怎么"说话"（The gateway's voice）

MCP 的 initialize 握手有一个 `instructions` 字段——**协议官方给服务端向模型喊话的口子**。
`serve` 用它送一句话，于是每个守协议的客户端都知道 mcptoon 是什么，**无需任何人去改 system
prompt**。它引导的"末尾一行播报"由自报工具 `mcptoon_usage` 喂真实数字（模型不许自己估）。

```bash
mcptoon config set footer off   # 关掉播报（持久化；下次连接就不再发 instructions）
mcptoon config set footer on    # 打开
```

设置存在 `~/.mcptoon/settings.json`，与服务器配置分开——写设置永远不可能损坏服务器定义。

---

## 安全（每次调用都过）

| 检查项 | 拦截内容 |
|--------|---------|
| 提示词注入 | 工具输出里埋的 `"ignore previous instructions"` |
| 凭据泄漏 | `sk-…`、`AKIA…`、`ghp_…` 等密钥特征 |
| 危险操作 | 名带 `delete`/`drop`/`purge` 的工具，除非显式加 `--destructive` |

无遥测、无外呼、无统计上报。API Key 只从配置/环境透传，不存储。

---

## Works with

**Claude Desktop · Claude Code · Cursor · Cline · Windsurf · VS Code Copilot · Codex · Gemini CLI · OpenCode** —— 外加 aider、shell 脚本、CI、cron 和一切能执行命令的环境，包括完全不支持 MCP 的。

---

## For developers

```python
from mcptoon.client import MCPClient

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-everything"]) as c:
    tools = c.list_tools()
    result = c.call_tool("echo", {"message": "hi"})
```

```bash
git clone https://github.com/activeing123/mcptoon.git && cd mcptoon
pip install -e . --no-build-isolation && pip install pytest
python -m pytest tests/ -v          # 1410 tests, green expected

docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --compact
```

零第三方导入是 review 阶段硬性规则。新功能必须带测试。
19,520 行 Python（物理行）、28 模块。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 路线图

详见 [ROADMAP.md](ROADMAP.md)：

- **v0.7.0 (P0)**：Profile 系统、凭证安全存储(Keyring)、安装源追踪+update、同步扩展 13+ IDE
- **v0.8.0 (P1)**：Tunnel 共享、语义搜索、交互式 TUI、自然语言命令
- **v1.0.0 (P2)**：容器隔离、审计日志/OTel、策略引擎/RBAC、Gateway、K8s Operator

## License

Apache 2.0 —— 见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
