# ADR-0001: CLI Mode over MCP Protocol

## Status
Accepted (2026-08-16)

## Context
MCP 协议通过 schema injection 让 AI 调用外部工具，但每个工具的 JSON Schema 都会消耗 LLM 上下文 token。

行业研究证实：
- CLI Agent vs MCP Agent 对比（75 次测试）：CLI 全面碾压
  - token 成本低 10-32 倍
  - 可靠性 ~100% vs MCP 的 72%
- Perplexity 撤掉 MCP 支持（token 开销太大）
- Anthropic 内部研究：shell 脚本比 MCP 省 98.7% token
- 3-4 个 MCP Server 就消耗 ~150K tokens（还没开始干活）

## Decision
mcptoon 采用 CLI 模式而非 MCP 客户端模式：
1. Agent 通过 shell 命令调用 MCP 工具（`mcptoon call <server> <tool>`）
2. 工具 schema 留在磁盘上，不注入 LLM 上下文
3. 只有用户主动请求的紧凑输出（TOON/SLIM）才进入上下文
4. 技能直调模式：技能文件直接写 CLI 命令 → 0 token

## Consequences
- ✅ 0 schema token 注入（vs Claude Desktop 的 90K+ tokens）
- ✅ 任何能跑 shell 的 Agent 都能用（不需要 MCP SDK 集成）
- ✅ 多 Agent 共享同一份配置
- ⚠️ Agent 需要知道工具名才能调用（但可通过 manifest 发现）
- ⚠️ 不是标准 MCP 客户端（但通过 `--format mcp` 可导出 MCP 格式）
