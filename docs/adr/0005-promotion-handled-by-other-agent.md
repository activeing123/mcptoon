# ADR 0005: 推广策略由其他 Agent 负责

**Date:** 2026-08-18
**Status:** Accepted

## Context

mcptoon 的传播推广（HackerNews、Reddit、X/Twitter、awesome 列表收录、GitHub Trending 等）由另一个专门负责推广的 Agent 处理。

## Decision

本会话不规划推广渠道和传播策略。推广是独立工作流。

## Consequences

- 本会话聚焦：产品定位、用户体验、技术开发优先级、领域建模
- 推广执行由其他 agent 负责，本会话产出的 ADR 可供推广 agent 参考
- ADR 0003 (demo 命令) 和 ADR 0004 (serve stdio bridge) 是推广的前置条件——推广 agent 可参考这两条 ADR 理解产品卖点
