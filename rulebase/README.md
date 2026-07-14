# rulebase(L2 流派规则库)

## 权责边界(INV-03,DESIGN V3.0 §6)

- **`approved/` 对所有 AI 与自动化流程只读**:合入仅经本人(或顾问)签署 + PR(分支保护把关);强度权重调整走贝叶斯建议 + 人工评审通道。
- **`staging/` 为 AI 草稿区**:录入辅助产出的条目必须 `draft_by_ai: true`、`review.status: draft`。
- **`provenance/` 来源链不可省略**:每条 approved 规则一份记录(校验器强制)。
- 版权:公版古籍可全文引用;当代著作/校注/译文须 `source_type=licensed` + `license_ref` 白名单。

## 结构与工具

```
rulebase/
├── approved/      # 已签署条目(AI 只读;每条配 provenance 记录)
├── staging/       # AI/转写草稿(draft_by_ai 强制)
├── rejected/      # 评审否决留档
├── provenance/    # 逐条来源链(source_edition/locator/license/签署)
├── schemas/       # 条目 JSON Schema(draft v0;字段变更走 RFC)
└── tools/
    ├── validate.py    # make rulebase-check(CI 阻断):结构 + 权责 + 来源链
    ├── new_draft.py   # 生成 staging 草稿(AI/顾问口述转写用)
    └── promote.py     # 晋升签署(仅本人/顾问运行)→ approved + provenance
```

## 流程

顾问口述/古籍抽取 → `new_draft.py` 生成草稿 → 人工逐条确认 → `promote.py --reviewed-by …`
签署晋升 → 补全 provenance 的版本与篇章定位 → PR 合入(required checks + 本人合并)。

## 待办

- [ ] 条件谓词语言 v1 表达力评估(走 RFC;当前 condition 为自由文本布尔表达)
- [ ] 古籍 OCR 与分段入库管线(公版语料;RAG 硬边界见 DESIGN §6)
