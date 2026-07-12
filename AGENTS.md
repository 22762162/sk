# 三鉴项目说明（AGENTS.md · Codex 侧）

本文件是 Codex 的项目说明，与 `CLAUDE.md` 语义同步但**独立维护**——不要机械复制其措辞，避免一份配置的偏差同时污染两个 AI。改动走 PR 评审。

## 不可违反的规则

1. `engine-paipan-ref/` 与 `engine-paipan/` 一样是确定性计算库：不得引入 LLM 调用、网络请求或非确定性逻辑（含系统时钟依赖）。历法事实（节气、时区、夏令时）只能来自注入的数据文件或函数参数，**不得凭模型记忆写历法常量**。
2. 修改任何 L1 计算路径后必须跑 `make golden-smoke`，失败不得提交。
3. 不得新增或修改 `rulebase/entries/` 下的规则条目内容；只能改 schema、校验器与工具链。
4. 用户可见文案在大陆版渠道禁用「预测/改运/消灾/化解/必然/注定」（词表 `infra/compliance/redline-words.txt`）；论断一律概率化措辞。
5. 命盘 JSON Schema 变更须先出 RFC（`docs/specs/`），经架构评审与人类批准。

## Codex 专属纪律（盲实现约束）

- **实现 `engine-paipan-ref/` 时禁止查看 `engine-paipan/` 目录。** 接口契约以 `docs/paipan-spec.md` 为唯一依据；对拍 I/O 协议见该文档附录。
- 参考实现使用 Python，**仅标准库 + pytest**，保持零第三方运行时依赖，便于独立复核。
- 不参与 `prompts/` 的编写与修改（避免措辞习惯渗入多模型辩手提示词，造成隐性偏袒）。

## 两个固定任务模板

| 模板 | 文件 | 用途 |
| --- | --- | --- |
| `ref-implementer` | `codex/tasks/ref-implementer.md` | 依据 spec 盲写参考实现 |
| `pr-reviewer` | `codex/tasks/pr-reviewer.md` | 按检查清单首轮评审 Claude 的 PR |

## 常用命令

`make test`（全部测试）· `make golden-smoke`（黄金集冒烟）· `make duipai`（双实现对拍）· `make redline`（红线词扫描）
