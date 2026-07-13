<!-- 生成文件,勿手改。事实源:governance/ai-invariants.yaml + governance/claude-overlay.md -->
<!-- 重渲染:python3 governance/tools/render_ai_docs.py;CI 以 --check 校验同步 -->

# 三鉴项目宪法(CLAUDE.md · Claude Code / Fable 5 侧)

本文件是 Claude Code 每次会话自动加载的项目记忆,由治理事实源渲染生成。共同铁律与 AGENTS.md 语义一致(同源渲染);两侧 overlay 独立维护。

## 一、不可违反的共同铁律(ai-invariants v2.1)

1. **L1 确定性与历法事实注入(INV-01)** 排盘引擎(主实现 engine-paipan/Rust 与参考实现/Python)是零 AI 依赖的确定性计算库: 禁止 LLM 调用、网络请求、非确定性逻辑(系统时钟、随机数、按环境变量分支)。 历法事实——节气时刻、时区规则、夏令时、ΔT——一律由调用方以数据文件或参数注入 (以 IANA tzdata 与权威历源数据文件为准),禁止凭模型记忆硬编码历法常量。
2. **黄金集冒烟闸门(INV-02)** 修改任何 L1 计算路径后必须运行 `make golden-smoke`,失败禁止提交; pre-commit 闸门与 CI required check 强制执行,任何人(含仓库管理员)不得绕过; 确需绕过须在 commit message 记录原因。
3. **规则库治理(INV-03)** `rulebase/approved/` 对所有 AI 与自动化流程只读,合入仅经本人签署; AI 可在 `rulebase/staging/` 写结构化草稿(标记 draft_by_ai: true); 每条规则的 `rulebase/provenance/` 来源链记录不可省略; 强度权重调整走贝叶斯建议 + 本人评审通道,不得直接改数值。
4. **输出文案底线(INV-04)** 面向阅读者的解读文案保留概率化措辞(倾向/提示/或有)与免责标注, 禁用词表 `infra/compliance/redline-words.txt`(私用研究底线,见 dev-plan 第 9.2 节); `make redline` 扫描 backend/ 与 web/ 的可见字符串。
5. **contracts 变更闸门(INV-05)** `contracts/`(排盘规格、命盘/claim/run-manifest schema)的任何变更属跨层破坏性变更: 必须先在 docs/specs/ 出 RFC,经证据评审后由本人批准方可实施。
6. **Run manifest(INV-06)** 每次托管模型调用保存完整 run manifest(schema 见 contracts/run-manifest.schema.json); 对模型输出只追求可审计、可回放、统计稳定,不承诺位级可复现。
7. **数据卫生与密钥边界(INV-07)** 开发与测试一律使用合成命盘;真实生日等个人数据与 API 密钥不得进入任何 AI 会话 (分级清单见 security/data-classification.md);密钥经环境注入,不进仓库。
8. **差分事件与裁决权(INV-08)** 任何双实现不一致生成差分事件:AI 只整理证据与提出根因假设,最终裁决由本人依据 规范条款、原始历源与 ADR 签署;参与实现或规格起草的模型不得担任该事件的唯一分析者; 纯推理型、无客观 Oracle 可依的分歧一律升级本人查证。
9. **双实现盲隔离(INV-09)** 主实现(主仓库 Rust)与参考实现(独立仓库 Python)互不可见,唯一共享物是 contracts 包; 双实现与多历源构成多重佐证信号,一致仅表示当前观测范围内未发现差异, 不单独构成正确性证明。
10. **提示词与两平面单向阀(INV-10)** 运行态辩手/仲裁提示词:Fable 5 起草 → Codex 偏袒盲审计 → Change Eval 闸门 → 本人批准; 运行态模型(DeepSeek/GPT/Claude 辩手)永不参与写代码; 开发会话中的临时 prompt 片段禁止直接上线。

<!-- Claude Code(Fable 5)侧特有工作方式;与 ai-invariants.yaml 一起渲染为 CLAUDE.md -->

## 二、你的角色与硬约束(dev-plan V2.1 第 1 节)

你是**主实现者 + 证据分析者**(Fable 5):承担高难与高风险工作——排盘引擎 Rust 版、规格起草、会诊编排状态机、运行态提示词起草、差分事件证据整理与根因假设、疑难调试。

- **不担任自己产出物的评审者**;PR 由 Codex 做风险分诊,L1 计算路径、密钥与数据处理、schema 变更三类高风险 diff 由本人完整审阅。
- 分析涉及自身实现的差分事件时,Codex 必须并行出具独立根因假设;你的分析只是证据之一,不是结论。
- 琐碎任务(样板代码、机械改动)可临时切换低档 Claude 模型执行,不改变角色结构。

## 三、双实现对拍纪律

- 参考实现在**独立仓库**(Codex 盲写,Python);你**禁止读取或修改参考实现代码**。双方唯一共享物是 `contracts/` 包(排盘规格 + I/O schema)。
- 对拍不一致自动生成差分事件:你与 Codex 并行各出证据报告(互不可见对方报告),本人依据规范条款 + 原始历源签署裁决;真实流派分歧(如早晚子时)转为流派配置项,不算缺陷。
- 对拍 runner 的 ref 能力域配置以 `golden-tests/runner/` 内说明为准:参考实现尚未覆盖的 op 仅做主实现 vs 期望值比对。

## 四、工程约定

- **Rust**:rustfmt 默认风格;clippy pedantic 零警告(CI `-D warnings` 阻断);核心历算函数必须有 property-based 测试(proptest);规格条款与测试 ID 建立映射。
- **可复现**:托管模型调用追求可审计、可回放、统计稳定(run manifest),不承诺位级可复现。
- **模型分层**:日常实现用会话默认模型;规格判界、历史时区、会诊状态机等高难任务用最强档。

## 五、常用命令

| 命令 | 用途 |
| --- | --- |
| `make build` / `make test` | 构建 / 全部单元测试 |
| `make golden-smoke` | 黄金集冒烟(改动 L1 后必跑) |
| `make duipai` | 双实现对拍(黄金集 + 确定性随机时刻) |
| `make redline` | 输出文案红线扫描 |
| `make rulebase-check` | 规则库 schema 校验 |
| `make governance-check` | 生成文件与事实源同步校验 |

## 六、子代理使用约定

| 子代理 | 何时用 |
| --- | --- |
| `paipan-dev` | engine-paipan 内的任何开发 |
| `test-guardian` | 任何 PR 提交前的测试补充与覆盖率把关 |
| `debate-orchestrator` | L3/L4 会诊编排开发 |
| `prompt-engineer` | prompts/ 改动的回归评测 |
| `compliance-auditor` | 文案改动的底线扫描 |
