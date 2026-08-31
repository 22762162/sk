# PR #42 风险分诊：运行态 GPT 迁移至 Gemini

本报告是实现者侧风险分诊，不构成独立异厂商评审。变更触及 `consult-engine/` 推理网关、
运行态模型路由、供应商登记与密钥处理，属于高风险路径；合入前仍须异厂商 reviewer
attestation 与本人完整审阅签署。

## BLOCKER

无已知代码阻断项。开发、单元测试和真实 API 冒烟只使用合成问题与合成命盘；`.env` 已被
gitignore，密钥值没有写入源码、测试、报告、manifest 或命令输出。

## WARN

1. 用户曾在聊天中粘贴过一枚密钥，该枚密钥应视为已暴露并在 Google 控制台撤销。本实现只确认
   当前 `.env` 中 `GEMINI_API_KEY` 存在且能调用，无法证明用户是否已完成旧密钥轮换。
2. 官方最新 `gemini-3.7-flash` 在 2026-08-30 实测连续返回 503 高负载；稳定版
   `gemini-3.6-flash` 同环境实测成功，因此当前锁定 3.6。未来升级必须重新走模型路由 PR 与评测。
3. 换模型会破坏 GPT 历史实验与 Gemini 新实验的直接可比性。迁移时间点前后的命中率、观点数、
   分歧率和延迟必须分版本观察，不能把变化直接归因于命理方法提升。
4. Google Gemini 的数据保留、训练退出、区域与账号项目字段仍需本人在
   `security/vendor-register.yaml` 完成季度登记；同时应在 Google 控制台设置预算硬上限。
5. Gemini 原生 `generateContent` 响应与 Anthropic/DeepSeek 不同；网关已做正文、usage 和
   modelVersion 映射，并在无正文/安全阻断时 fail closed，但后续新响应字段仍可能需要适配。
6. 未修改 `prompts/`。同一套模型无关辩手与 judge 提示词继续使用；提示词起草/审计隔离不变。
7. `eval-smoke` 在约 10 分钟后由实现者中止：第一张合成盘的 S1/P3/D3/D3J 全部完成，第二张完成
   S1/P3 后在 D3 长尾等待。已完成结果中第一张 P3/D3 的原始研究输出各有 1 个红线词，D3J 为 0；
   正式 App 仍有后端清洗，但该观察必须在后续 Change Eval 与提示词审计中保留，不能记为全量通过。

## NOTE

- 运行态三方：Claude / Gemini 3.6 Flash / DeepSeek。
- Gemini 采用原生端点
  `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`，密钥只通过
  `x-goog-api-key` 请求头注入。
- 模型路由版本从 `1.0.0` 升至 `1.1.0`，工程设计从 V3.0 升至 V3.1。
- `keys-check` 只报告三家密钥是否存在，不读取或输出密钥值。

## 验证

- 后端单元测试 16 项通过，其中 2 项覆盖 Gemini 原生请求映射与无正文 fail-closed。
- Gemini 3.6 Flash 单次合成 JSON 冒烟通过。
- 合成命盘完整 D3J 实测通过：`anthropic,deepseek,gemini` 三家到场，0 缺席，judge 与
  plain summary 均生成。
- `make test`：Rust 24 项、参考实现 158 项、后端 16 项全部通过；`golden-smoke` 102 项一致。
- `lint`、`rulebase-check`、`prompt-symmetry`、`governance-check`、`redline`、
  Python/JavaScript 语法检查与 `git diff --check` 通过。
- `eval-smoke` 为部分完成且主动中止，不列为通过项；已完成数据与风险见 WARN 7。

结论：实现者侧建议进入评审；必须完成全仓门禁、异厂商评审与本人签署后才可合入。
