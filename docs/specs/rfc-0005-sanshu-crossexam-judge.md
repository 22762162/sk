# RFC-0005 · 三段封存的质证与裁判契约 v0(候选草案,B6 专项)

状态:草案,与提示词 v2 同批送审;**不静默复用旧 chat/judge**(旧 judge 仅服务旧八字会诊,
其 issues/summary 协议无法承载三段/分方法/弃答语义,B6 已裁定不兼容)。
归属与评审路径:Fable 5 起草 → Codex 偏袒盲审计 → Change Eval → 本人批准 → 独立接线 PR;
接线前本契约与配套提示词(sanshu-crossexam-v2/sanshu-judge-v2,待起草)不进运行态。

## 1. 质证(cross-exam,新 slot:sanshu-crossexam)

- 输入:同一问题下,**另两家供应商**的脱敏封存三段(bazi/gua/combined 原文+seal),
  匿名标注为 甲/乙;不含供应商名、不含原始材料。
- 输出契约(要点):challenges[≤4],每条 {target: "甲|乙", section: "bazi|gua|combined",
  claim_ref: 被质证的原文摘录≤80字, reason: 质证理由, severity: "info|material"};
  无可质证时合法输出空数组。禁止引入新术数论据(只能用对方段内已有内容互驳)。
- 质证不改写任何段落;结果仅供裁判与复盘,原封存段不变。

## 2. 裁判(judge,新 slot:sanshu-judge)

- 输入:三家的脱敏封存三段+全部质证记录(匿名 甲乙丙;由 seed 轮换裁判供应商,
  裁判不得裁自家——编排层保证,本契约声明)。
- 输出契约(要点):per_provider[3]×per_section 的
  {consistency: "consistent|partial|contradicted", note≤200字}、
  cross_method_note(两法相悖面归纳,≤300字)、
  scorable: 每段是否可入复盘分母(弃答/失败标记透传,不改写)、
  summary ≤400字。**裁判不产生新预测、不合并三术为单一结论、不给准确率**。
- 与复盘关系:裁判输出只作复盘辅助标注;命中判定以事件 adjudication 对照现实记录为准,
  裁判无权改判事件结果。

## 3. facts-only 基线提示词的归属(应 Codex 要求明确)

`evals/change/baseline_prompts/facts-only-v1.md` 为**评测器资产**(P19 线,INV-12),
不是运行态提示词;其变更走评测线评审(独立评审+本人确认),与候选提示词永不同 PR。

## 4. 待办

- sanshu-crossexam-v2.md / sanshu-judge-v2.md 提示词正文:随本 RFC 评审意见定稿后起草
  (先契约后文案,避免 v1 式返工);编排层的轮换/匿名/预算扩展属接线 PR 范畴。
