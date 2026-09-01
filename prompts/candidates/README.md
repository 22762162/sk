# prompts/candidates · 候选提示词停放区

此目录内一切提示词**未上线**,运行态代码禁止引用。上线链(INV-10):
Fable 5 起草 → Codex 偏袒盲审计 → Change Eval → 本人批准 → 独立接线 PR。

| 候选 | 状态 | 归属/评审路径 |
|---|---|---|
| sanshu-inquiry-v1.md | 审计不通过(B1-B6),归档留证,禁止接线 | 已结 |
| sanshu-bazi-v2.md | **待 Codex 盲审计** | 运行态候选;INV-10 全链 |
| sanshu-gua-v2.md | **待 Codex 盲审计** | 同上 |
| sanshu-combined-v2.md | **待 Codex 盲审计** | 同上 |
| (RFC-0005)sanshu-crossexam/judge-v2 | 契约草案先行,文案待契约评审后起草 | 同上;不复用旧 judge |
| evals/…/facts-only-v1.md | 评测器资产(P19 线) | 评测线独立评审+本人确认;永不与候选同 PR |

v2 设计对审计 v1 结论的对应:输出=可执行 schema 逐字段;弃答一等公民且 gua 弃答带元数据;
红线全文在 system 正文;隔离由编排层物理保证,提示词只做行为引导;三段结构/约束严格度对称
(供偏袒审计核验);事件含 comparator-threshold 依赖规则原文。
