# consult-engine（L3 推理网关 + L4 会诊引擎）

P2 阶段主战场，当前为占位。开发使用 `debate-orchestrator` 子代理。

## 规划范围

- **L3 推理网关**：多供应商抽象、国内外模型池热切换、缓存策略；Codex 负责故障注入测试（断供/超时/降级）。
- **L4 会诊引擎**：LangGraph 三轮会诊状态机（盲评 → 匿名质证 → 仲裁合成）、claim JSON Schema 结构化输出、可复现性四元组落盘（温度 0 + 种子 + 规则库版本 + 提示词版本）；Codex 负责对抗测试（"自信的说谎者"用例攻击仲裁逻辑）。
- `eval/`：提示词回归评测的 20 例固定合成盘集与基线（供 prompt-engineer 子代理使用）。

## 纪律

- 单元测试禁止真实调用 LLM API（用录制 fixture）。
- 会诊状态机与 claim schema 变更走 RFC（docs/specs/）。
