# rulebase（L2 流派规则库）

## 权责边界（CLAUDE.md / AGENTS.md 规则 3）

- **规则条目（`entries/`）：三个 AI 一律只读。** 条目由命理顾问经评审流程录入；强度权重调整走贝叶斯建议 + 人工评审通道。
- AI 可以做的：schema 与校验器、录入辅助工具（顾问口述 → 结构化草稿，草稿必须 `draft_by_ai: true` 且经顾问逐条确认）、古籍 OCR 与分段入库管线、向量入库管线。
- 版权纪律：公版古籍（《子平真诠》等）可全文入库；当代著作与盲派整理材料须先取得授权——管线中以 `provenance.source_type = licensed` + `license_ref` 做来源白名单校验。

## 结构

```
rulebase/
├── entries/        # 规则条目（JSON，v0；仅顾问经评审流程写入）
├── schema/         # 条目 JSON Schema（draft v0，条件谓词语言表达力评估中）
└── tools/          # 校验器与录入工具链（AI 可维护）
```

## 校验

```bash
make rulebase-check   # 校验 entries/ 全部条目（CI 阻断项）
```

校验器强制：schema 结构 + `strength ∈ [0,1]` + `licensed` 必有 `license_ref` + `review.status=confirmed` 必有 `reviewed_by`（含 AI 草稿的顾问确认要求）。

## 待办

- [ ] 条件谓词语言 v1 的表达力评估（Opus 评审，走 RFC）
- [ ] 顾问录入工具（P1 后期交付）
