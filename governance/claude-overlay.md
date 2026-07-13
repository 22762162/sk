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
