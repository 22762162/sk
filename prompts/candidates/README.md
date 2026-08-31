# prompts/candidates · 候选提示词停放区

此目录内一切提示词**未上线**,运行态代码禁止引用。上线链(INV-10):
Fable 5 起草 → Codex 偏袒盲审计 → Change Eval → 本人批准 → 独立接线 PR。

| 候选 | 状态 |
|---|---|
| sanshu-inquiry-v1.md | **审计不通过(2026-08-31,阻断 B1-B5)**——归档留证,禁止接线。起草方(Fable 5)接受全部结论 |

## v1 审计结论摘要(详见 docs/reviews/sanshu-inquiry-v1-codex-audit.md)

- 无供应商偏袒(通过);但"三段封存"不能靠提示词纪律实现——**必须编排级物理隔离**:
  八字调用只见八字、卦调用只见卦快照、综合调用只见两份已封存结果;每次独立 run manifest
- 缺可执行输出 schema/校验器(fail-closed);材料缺席路径自相矛盾;应期约束会诱导编造日期;
  红线"继承"注释不会进入模型上下文(加载器只读 system 正文)
- **v2 前置工程**(新有界任务,先于任何重新起草):①三段封存编排器+字段级校验器(涉 contracts 需 RFC);
  ②Change Eval 基建(evals/change 现为空,INV-12 缺口);③结构化 abstain 与三表事件契约设计
