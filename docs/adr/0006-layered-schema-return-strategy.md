# ADR 0006: 分层 Schema 返回策略

**Date:** 2026-08-18
**Status:** Accepted

## Context

`mcptoon serve` stdio bridge 需要向 agent 返回工具 schema。MCP 协议的 `tools/list` 要求返回每个工具的 JSON Schema（参数名、类型、描述）。Claude Code 用这个 schema 决定如何调用工具。

方案选择：
- A. 返回完整 schema — token 不省，核心价值消失
- B. 返回 SLIM manifest 作为 schema — token 极省但 Claude Code 可能无法理解
- C. 单工具按需返回 — agent 不知道参数，可能报错
- D. 分层返回 — 精简 schema 在 tools/list，完整校验在 call_tool

## Decision

**D. 分层返回。**

## 设计

### tools/list 返回精简 schema
- 保留标准 JSON Schema 结构（type, properties, 顶层参数名+类型）
- 去掉冗长 description、examples、嵌套 $ref、default 值等
- 目标：省 80-90% tokens，同时 Claude Code 能正确调用

```json
{
  "name": "fetch_fetch",
  "description": "Fetch a URL and return content. Args: url(str), max_length(int)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url": {"type": "string"},
      "max_length": {"type": "integer"}
    }
  }
}
```

### call_tool 被调用时，中间层做
1. 参数校验 — 用完整 schema 验证 agent 传的参数
2. 安全检查 — prompt injection guard, credential leak detection, dangerous-op blocker
3. 路由转发 — 通过 MCPClientPool 转发到底层 server
4. 输出压缩 — TOON/SLIM 编码后返回

### 精简规则
- description：原始 schema 可能 500+ 字的描述 → 压缩到 1 句话（< 100 字）
- properties：保留参数名和类型，去掉 description 嵌套
- required：保留
- 去掉：examples, $ref, $schema, additionalProperties, pattern, format 等非必要字段

## Rationale

1. **兼容性优先** — Claude Code / Cursor 需要标准 JSON Schema 才能正确调用工具。SLIM 格式 token 更省但 agent 不认。
2. **80-90% 节省已足够** — 从 90,804 tokens 降到 ~9K-18K tokens，对大多数 context window 已经够用。
3. **完整校验保留在中间层** — agent 传错参数时 mcptoon 能拦住，不会浪费底层 server 调用。
4. **实现复杂度可控** — 精简 schema 是字符串裁剪，不是格式转换。

## Consequences

- 需要实现 schema 精简函数：`simplify_schema(full_schema) → slim_schema`
- 需要实现参数校验函数：`validate_args(slim_args, full_schema) → ok/error`
- tools/list 的 token 节省 80-90%，不如 CLI 模式的 99.9%——但换取了 agent 兼容性
- 后续可考虑：agent 声明支持 SLIM 时，动态切换到更激进压缩
