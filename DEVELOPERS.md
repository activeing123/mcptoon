# DEVELOPERS.md — mcptoon 技术文档

> 面向开发者和进阶用户。普通小白请看 [README.md](./README.md)。
> English: this document is technical; the beginner-facing README is at [README.md](./README.md).

mcptoon: 一个零依赖、零配置、CLI 优先的跨 Agent MCP 管理网关。
`README.md` 面向小白，本文件是完整的技术说明。

- 版本：v0.6.0 · 531 tests · 0 依赖 · ~6,800 行 Python · Apache 2.0
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
mcptoon add fetch --stdio npx -y @modelcontextprotocol/server-fetch
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

复现：`mcptoon manifest --compact --tokens`. 这是一个旋钮不是开关：需要零歧义时切回 `--json`。

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
- 5 分钟 schema 缓存
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
| `mcptoon quickstart` | 检测并导入已有配置，列出全部工具 |
| `mcptoon demo` | 现场前后对比 token 数字 |

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

with MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"]) as c:
    tools = c.list_tools()
    result = c.call_tool("fetch", {"url": "https://example.com"})
```

```bash
git clone https://github.com/activeing123/mcptoon.git && cd mcptoon
pip install -e . --no-build-isolation && pip install pytest
python -m pytest tests/ -v          # 531 tests, green expected

docker run --rm -v ~/.mcptoon:/root/.mcptoon mcptoon manifest --compact
```

零第三方导入是 review 阶段硬性规则。新功能必须带测试。
~6,800 行 Python、14 模块。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 路线图

详见 [ROADMAP.md](ROADMAP.md)：

- **v0.7.0 (P0)**：Profile 系统、凭证安全存储(Keyring)、安装源追踪+update、同步扩展 13+ IDE
- **v0.8.0 (P1)**：Tunnel 共享、语义搜索、交互式 TUI、自然语言命令
- **v1.0.0 (P2)**：容器隔离、审计日志/OTel、策略引擎/RBAC、Gateway、K8s Operator

## License

Apache 2.0 —— 见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
