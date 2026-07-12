# prompts（辩手 / 仲裁提示词 · 产品核心资产）

## 纪律（CLAUDE.md 工程约定 + 设计方案第 7 节）

1. **提示词视同代码**：改动走 PR；每个文件头部维护 `version:` 字段与变更说明。
2. **只允许 Opus 会话产出改动草案**（`/model` 切换后进行）；日常模型与 Codex 均不参与提示词编写——防止措辞习惯渗入多模型辩手提示词造成隐性偏袒。
3. 每次改动必须附 `prompt-engineer` 子代理的 **20 例回归报告**（共识覆盖率、同盘一致率、分歧率，对基线与对首版 V1）；指标劣化 CI 拒绝。
4. 防隐性漂移：每月对比首版基线一次，累计偏移写入 `CHANGELOG.md`。

## 结构

```
prompts/
├── debaters/    # 三辩手人设与质证协议（P2 由 Opus 会话产出）
├── arbiter/     # 仲裁标准与合成规则（P2）
└── CHANGELOG.md # 版本与基线偏移记录（首个提示词合入时创建）
```

## 文件头部约定

```yaml
# version: 1
# model_target: <辩手所属模型池标识>
# baseline: eval/baselines/v1.json
# changelog: 首版
```
