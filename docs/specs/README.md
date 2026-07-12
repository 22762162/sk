# RFC 流程（docs/specs/）

跨层破坏性变更——命盘 JSON Schema、对拍 I/O 协议、claim JSON Schema、规则条目 schema——必须先出 RFC 再实施（CLAUDE.md 规则 5）。

## 流程

1. 复制 `TEMPLATE.md` 为 `NNNN-短标题.md`（NNNN 递增编号），填写动机、变更内容、兼容性影响、迁移方案。
2. 切换 Opus（`/model`）做架构评审，评审意见附在 RFC 末尾。
3. 人类工程师批准后合入，RFC 状态改为 `accepted`，方可开始实施。
4. 实施 PR 必须引用 RFC 编号。

## 状态

`draft` → `review` → `accepted` / `rejected` / `superseded`
