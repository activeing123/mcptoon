# ADR 0002: 目标用户为个人 AI Agent 用户

**Date:** 2026-08-18
**Status:** Accepted

## Context

mcptoon 的目标用户可以是：
- A. 个人 AI coding agent 用户（Claude Code / Cursor / Codex）
- B. MCP server 开发者
- C. 企业 AI 团队
- D. AI agent 框架开发者

## Decision

目标用户为 **A. 个人 AI coding agent 用户**。

## Rationale

1. **痛点最直接** — 他们已经感受到 MCP 配置痛苦（JSON 编辑、syntax error、重启）和 context window 被 schema 吃掉的痛点
2. **规模最大** — GitHub 2026 年爆火项目（ECC 241K, skills 221K, claw-code 195K）全服务于这个群体
3. **获取成本最低** — `pip install mcptoon` 零摩擦，社区传播有效
4. **toC 增长模型** — 不需要销售团队，靠 README / 博客 / HN / Reddit 传播

## Consequences

- 增长策略：toC 社区传播为主，不走 toB 销售路线
- 营销渠道：HackerNews、Reddit r/programming、X/Twitter、Dev.to、V2EX
- 文档优先级：英文 README 面向全球开发者，中文 README 面向国内开发者
- 不做：企业 SSO、团队管理、RBAC 等 toB 功能
- 风险：个人用户付费意愿低，需要考虑开源 + 可选增值服务的商业模式
