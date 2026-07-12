# 三鉴项目宪法（CLAUDE.md）

本文件是 Claude Code 每次会话自动加载的项目记忆，是《三鉴多 AI 协同开发设计方案》工程铁律的可执行版本。与 `AGENTS.md`（Codex 侧）语义同步、独立维护；两份文件的改动都必须走 PR 评审。

## 一、不可违反的规则（红线）

1. **engine-paipan 是零 AI 依赖的确定性计算库。** 禁止在其中引入任何 LLM 调用、网络请求或非确定性逻辑（含系统时钟依赖、随机数、按环境变量分支）。所有历法事实——节气时刻、时区规则、夏令时——一律由调用方以数据文件或参数注入，**禁止凭模型记忆硬编码历法常量**（历法事实以 IANA tzdata 与权威历源数据文件为准）。
2. **修改 engine-paipan 任何计算路径后，必须运行 `make golden-smoke`**（黄金集冒烟），失败禁止提交。pre-commit 闸门与 CI 会强制执行。
3. **禁止新增或修改 `rulebase/entries/` 下的规则条目内容。** 规则由命理顾问经评审流程录入；你只能修改其 schema、校验器与工具链。录入辅助工具产生的草稿必须标记 `draft_by_ai: true` 且经顾问逐条确认后方可去除该标记。强度权重调整走贝叶斯建议 + 人工评审通道，不得直接改数值。
4. **面向用户的任何文案**：大陆版渠道禁用「预测/改运/消灾/化解/必然/注定」等词（权威词表：`infra/compliance/redline-words.txt`，随监管通报月度更新）；全部论断使用概率化措辞（倾向/提示/或有）。`make redline` 扫描 `app/` 与 `backend/` 的用户可见字符串。
5. **命盘 JSON Schema 变更属于跨层破坏性变更**：必须先在 `docs/specs/` 出 RFC，经 Opus 架构评审 + 人类批准后才可实施。

## 二、双实现对拍纪律

- `engine-paipan/`（Rust 主实现，你负责）与 `engine-paipan-ref/`（Python 参考实现，由 Codex 盲写）互为对拍对象。
- 在 Claude Code 会话中**禁止读取或修改 `engine-paipan-ref/` 的实现代码**。双方唯一共享物是接口契约 `docs/paipan-spec.md` 与对拍 I/O 协议（见规格文档附录）。
- 对拍不一致的案例自动归档为 discrepancy issue，交 Opus 仲裁；仲裁结论必须同时满足「Opus 推理 + 权威历源证据」双条件，纯推理无法验证的分歧升级人类。
- 无法裁定的真实流派分歧（如早晚子时）转为流派配置项，不算缺陷。

## 三、工程约定

- **Rust**：rustfmt 默认风格；clippy pedantic 级零警告（CI 以 `-D warnings` 阻断）；核心历算函数必须有 property-based 测试（proptest）。
- **Python 参考实现**：仅标准库 + pytest，保持可独立运行（这是 Codex 侧的约定，写在这里仅供你理解对拍工具链）。
- **提示词（prompts/）视同代码**：改动走 PR，必须附 prompt-engineer 子代理的 20 例回归报告（共识覆盖率、同盘一致率、分歧率对基线）；指标劣化 CI 拒绝。只允许 Opus 会话产出提示词改动草案；Codex 不参与提示词编写。
- **可复现性**：每次会诊调用四元组落盘——温度 0 + 固定种子 + 规则库版本 + 提示词版本。
- **数据卫生**：开发与测试一律使用合成命盘；禁止将真实用户命盘数据粘贴进任何 AI 会话。
- **模型分层**：日常实现用默认模型；节气按秒判界、历史时区规则、会诊状态机设计等高难任务切换 Opus（`/model`）。

## 四、常用命令

| 命令 | 用途 |
| --- | --- |
| `make build` / `make test` | 构建 / 全部单元测试 |
| `make golden-smoke` | 黄金集冒烟（改动 L1 后必跑） |
| `make duipai` | 双实现对拍（黄金集 + 确定性随机时刻） |
| `make redline` | 大陆版红线词扫描 |
| `make rulebase-check` | 规则库 schema 校验 |

## 五、子代理使用约定

| 子代理 | 何时用 |
| --- | --- |
| `paipan-dev` | engine-paipan 内的任何开发 |
| `test-guardian` | 任何 PR 提交前的测试补充与覆盖率把关 |
| `debate-orchestrator` | L3/L4 会诊编排开发 |
| `prompt-engineer` | prompts/ 改动的回归评测 |
| `compliance-auditor` | 发布前与文案改动的合规扫描 |
