# ADR 0001: mcptoon 定位为 MCP 工具管理器

**Date:** 2026-08-18
**Status:** Accepted

## Context

mcptoon 的核心能力包括：(1) schema 不进 context，(2) 工具懒加载，(3) 输出 TOON/SLIM 压缩。

有三种可能的定位方向：

1. **MCP token 优化工具** — 聚焦 token 节省，与 headroom(66K星) 和 tscg(24星) 直接竞争"token 优化"赛道
2. **MCP 工具管理器** — 聚焦"管理 MCP 工具的全流程"，token 优化是核心卖点之一但不唯一
3. **Agent-MCP 中间层** — 聚焦"agent 和 MCP 之间的抽象层"，更学术更抽象

## Decision

定位为 **MCP 工具管理器**。

## Rationale

1. **赛道更宽** — "token 优化" 只是管理器的一个功能维度，定位太窄会限制后续功能扩展
2. **避开正面硬刚** — headroom 66K 星的"token 压缩"赛道已有头部玩家，mcptoon 以"管理器"身份切入，token 优化是差异化卖点而非全部
3. **用户心智更清晰** — 用户搜 "MCP tool manager" / "MCP 管理器" 时能直接找到 mcptoon；搜 "token optimization" 时会被 headroom 碾压
4. **对标已有成功模式** — homebrew, nvm, cargo 都是"工具管理器"定位，用户天然理解这个概念

## Consequences

- README 和营销材料以"管理器"为主叙事，token 优化作为"杀手级功能"
- 后续功能扩展方向：版本管理、配置同步、多 agent 共享、server 健康监控
- 不与 headroom 形成直接竞争关系，而是互补关系（headroom 压输出，mcptoon 管 schema + 管工具）
