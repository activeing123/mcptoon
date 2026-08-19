# ADR 0007: 工具命名空间 — server_tool 前缀

**Date:** 2026-08-18
**Status:** Accepted

## Context

`mcptoon serve` 模式下，MCP 协议的 `call_tool` 只接收一个 `name` 字符串。底层可能有 10 个 server，每个 server 都有 `fetch`、`search`、`read` 等同名工具。需要命名空间策略避免冲突。

## Decision

**A. 前缀命名 `server_tool`。**

工具名格式：`{server_name}_{tool_name}`

示例：
- `fetch_fetch` — fetch server 的 fetch 工具
- `github_search` — github server 的 search 工具
- `filesystem_read` — filesystem server 的 read 工具

## Rationale

1. **代码一致** — 现有 manifest.py 已用 `{server}_{tool_name}` 作为 operationId
2. **无歧义** — agent 和用户一看工具名就知道是哪个 server 的
3. **token 成本微增** — 工具名多 10-20 字符，相比 schema 节省不值一提
4. **行为确定** — 不依赖加载顺序，同名工具不会因 server 配置顺序不同而产生不同名字
5. **零配置** — 用户不需要为每个 server 指定前缀，自动生成

**否决方案：**
- B. 不加前缀 — 同名冲突
- C. 智能去重 — 行为取决于加载顺序，bug 温床
- D. 用户自配前缀 — 增加配置负担，违背零配置理念

## Consequences

- serve 模式的 tools/list 返回的工具名全部为 `{server}_{tool}` 格式
- call_tool 收到 `{server}_{tool}` 后，按第一个 `_` 拆分为 server 和 tool，路由到对应底层 server
- 需要处理边界：server name 或 tool name 本身包含 `_` 的情况 — 用配置中已知的 server name 列表做最长匹配
- CLI 模式不受影响 — CLI 仍是 `mcptoon call <server> <tool>` 两个参数
