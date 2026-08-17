# ADR-0003: TOON Format as Primary Output

## Status
Accepted (2026-08-16)

## Context
MCP 返回 JSON 格式：`{"content":[{"type":"text","text":"{\"name\":\"react\"}"}]}` — 80 tokens 的包装只为传 6 tokens 数据。200 次调用 = 15K tokens 纯语法浪费。

## Decision
mcptoon 将 TOON (Token-Oriented Object Notation) 作为默认输出格式：
1. `--toon`：标准 TOON（YAML 风格 + CSV 表格），比 JSON 省 30-60%
2. `--slim`：超紧凑 schema，比 JSON 省 93%
3. `--compact`：工具名列表，比 JSON 省 97-100%
4. `--json`：标准 JSON（向后兼容）
5. 技能直调模式：连 TOON 都不用，CLI 输出直接进 Agent 上下文

## Consequences
- ✅ 每次调用省 30-97% token
- ✅ 技能直调模式 0 token
- ✅ TOON 是开放规范，其他工具可以采纳
- ⚠️ TOON 不是标准格式，需要 Agent 理解（但 TOON 设计为 LLM 友好）
- ⚠️ 需要维护 toon_encode/toon_decode 的正确性
