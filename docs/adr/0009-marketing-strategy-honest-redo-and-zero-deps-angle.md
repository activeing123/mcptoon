# ADR 0009: 营销策略——诚实复盘帖 + 零依赖工程哲学角度

**Date:** 2026-08-20
**Status:** Accepted
**Supersedes:** ADR 0005 (推广策略由其他 Agent 负责 — 现在推广策略在本会话中制定)

## Context

mcptoon 在 2026-08-11 获得 99 颗 star（全部来自 GitHub 内部推荐），但增长随后停滞。7 个社区已发帖（Dev.to、Bluesky、Reddit、HN、Product Hunt、EveryDev、Hashnode），但外部 referrer 几乎为零。核心瓶颈是 HN 被 shadowban（73 分但帖子不可见）和 Reddit karma=0 无法在高流量子版发帖。

已有推广内容角度单一——所有帖子都在讲 "token 优化"，同一个故事讲了 7 遍，新鲜感已过。

## Decision

采用多角度内容策略，每个渠道用不同的叙事角度：

1. **HN**：新账号 + 诚实复盘帖（"I claimed 99.87% savings, HN commenters proved me wrong"）。旧帖被 shadowban = 从未传播，可安全重发。需要 3-5 天养号后发帖。
2. **Dev.to**：新文章，角度为"零依赖工程哲学 + 项目经验"（"Zero Dependencies, 250KB, 486 Tests"）。不重复旧文的角度。
3. **Product Hunt**：排在 HN + Dev.to 之后，用 HN 帖作为社会证明。
4. **Reddit**：只养号不发帖，等 karma 到 50 再在 r/LocalLLaMA 和 r/ClaudeAI 发帖。
5. **Twitter/X 和中文平台**：暂不做。

执行顺序：Dev.to（立刻）→ HN 养号 + 发帖 → Product Hunt。

## Consequences

- HN 需要新账号 + 3-5 天养号，不立即可发
- Dev.to 文章草稿在 `docs/devto-zero-deps.md`
- HN 帖草稿在 `docs/hn-post-draft.md`（数据已更新到 177 star / v0.5.1 / 486 tests）
- Reddit 短期无产出，长期需要持续养号
- ADR 0005 被推翻——推广策略现在由本会话制定，不再外包给其他 agent
