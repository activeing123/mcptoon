# ADR 0004: mcptoon serve stdio bridge — 最高优先级开发任务

**Date:** 2026-08-18
**Status:** Accepted

## Context

mcptoon 当前是纯 CLI 工具——用户在 agent 外面的终端运行命令。这导致一个核心矛盾：Claude Code / Cursor 用户习惯在 agent 内部直接用工具，mcptoon 要求他们在 agent 外面用 CLI。行为改变太大。

竞品对比：
- headroom (66K星): proxy 模式，改一行配置，透明接入
- mcptoon (172星): CLI 模式，需在 agent 外操作

## Decision

**`mcptoon serve` stdio bridge 是从 172 星到 1000 星的第一优先级开发任务。**

## 设计

### 用户视角
在 Claude Code 的 `mcpServers` 配置中加一条：
```json
"mcptoon": {
  "command": "mcptoon",
  "args": ["serve"]
}
```
Claude Code 只看到 **1 个 MCP server**（mcptoon），而不是 100 个。mcptoon 在中间做：
1. `list_tools` → 返回所有底层 server 的 compact manifest（不是完整 schema）
2. `call_tool` → 路由到对应底层 server，返回压缩后的结果
3. 安全检查在中间层完成

### 实现要点
- 新增 MCP server 端实现（监听 stdin/stdout 的 JSON-RPC 循环）
- 复用现有 MCPClientPool（连接池懒加载）和 router.py（路由逻辑）
- `list_tools` 返回 compact/SLIM 格式的 manifest，而非完整 JSON schema
- `call_tool` 转发到底层 server，输出 TOON/SLIM 压缩后返回
- 安全检查（prompt injection guard, credential leak detection）在中间层执行

### 架构基础
已有：MCPClient（完整 client 端协议）、MCPClientPool（连接池）、router.py（路由）
需新增：MCP server 端 stdin/stdout JSON-RPC 循环模块

## Rationale

1. **行为改变为零** — 用户在 Claude Code 内照常用工具，只是底下多了一层 mcptoon 代理
2. **headroom 验证** — headroom 66K 星就是 proxy 模式，改一行配置接入
3. **从"辅助工具"到"基础设施"** — mcptoon 从 agent 外的 CLI 变成 agent 和 MCP server 之间的透明代理
4. **传播链解锁** — Claude Code 用户只需加一条配置就能试用，截图/分享门槛大幅降低

## Consequences

- 开发优先级：`mcptoon serve` > `mcptoon demo` > 其他功能
- README 快速开始部分需要新增 "stdio bridge 模式" 安装方式
- 需要处理 Claude Code / Cursor / Codex 不同 agent 的配置差异
- compact manifest 的 MCP schema 需要符合 MCP 协议规范（Claude Code 能理解）
- 这是 hard to reverse 的架构决策——一旦发布 serve 模式，用户依赖它作为日常基础设施
