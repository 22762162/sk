# 「三鉴」工程设计 · 活文档

> **当前版本：V3.0 ｜ 2026-07-14 ｜ 唯一有效版本，历史版本全部作废**
> 本文件放置于主仓库 `docs/DESIGN.md`，随开发迭代维护。

## 如何迭代本文档

1. 第 1–11 节为**已冻结的设计基线**：修改须附理由（演练结果、实验数据或差分事件），走 PR 并在下方变更记录追加一行，版本号 +0.1；纯措辞修正不升版。
2. 第 12 节（启动清单）与第 13 节（迭代日志）为**工作区**：随时直接更新，不升版。
3. 重大架构决策写入 `docs/adr/`，本文档只保留结论与链接。

## 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| V3.0 | 2026-07-14 | 定稿为活文档；确立开发态双模型 / 运行态三模型两平面；四仓结构；judge 定位为轮换盲评者；拉丁方研究模式；双层 manifest；分级承诺与不确定性传播；四实验臂；巴纳姆预注册；私用合规底线 |

---

## 0 项目定位

**性质**：个人私有研究项目。不上架、不发售、不向任何第三方提供服务。研究对象为"确定性排盘 + 多模型互证"技术架构本身。

**核心研究问题**：三模型质证是否在可核验指标上优于单一强模型？若优，增益来自模型数量、质证过程还是仲裁步骤？全部评测围绕此问题设计（第 7 节实验臂）。

**两平面模型选型**：

- **开发态（写代码）= 双模型**：Fable 5（经 Claude Code，承担高难与高风险工作）+ Codex（GPT 系，承担性价比工作、参考实现与异构验证）。"Fable 5 能力覆盖 Opus 4.8"为项目内部待验证假设，以冻结评测集结果为准。
- **运行态（会诊引擎）= 三模型**：DeepSeek × GPT × Claude 三辩手互证。各模型为当前默认候选，最终以冻结评测集的质量、延迟、成本结果为准。

**架构**：五层——L1 确定性排盘（Rust）→ L2 流派规则库 → L3 多模型推理网关 → L4 会诊仲裁（LangGraph）→ L5 呈现（React + FastAPI，本地或带认证私有 VPS，不开放注册）。

**三条产品铁律**：大模型不做历法计算；每句解读可溯源到规则库条目；分歧透明呈现，不掩盖。

**UI 双模式**：观察模式展示完整会诊过程；实验模式在评分锁定前只展示格式统一后的最终文本，隐藏模型身份、辩论过程与引用线索（服务第 11 节实验）。

---

## 1 开发态：双模型、证据仲裁、人类签署

### 1.1 角色矩阵

| 角色 | 工具载体 | 当前模型 | 职责 | 硬约束 |
| --- | --- | --- | --- | --- |
| 主实现者 + 证据分析者 | Claude Code | Fable 5 | 排盘引擎 Rust 版、规格起草、会诊状态机、运行态提示词起草、差分事件证据整理、疑难调试 | 不评审自己的产出；分析涉及自身实现的差分事件时，Codex 必须并行出具独立报告 |
| 性价比实现者 + 交叉评审者 | Codex（主仓库工作会话） | GPT 系 | 常规模块实现（React 前端、后端 CRUD、脚本、测试补写）、PR 风险分诊、提示词偏袒审计、对抗测试 | 触碰过主仓库 L1 代码的会话不得承接参考实现 |
| 参考实现者 | Codex（独立环境、独立会话） | GPT 系 | 独立仓库盲写排盘参考实现（Python），只见 contract 仓库 | 环境不挂载主仓库、无主仓库凭据、不复用主仓库工作会话 |
| 最终签署人 | — | 本人 | 差分裁决、规格批准、规则库合入、评测器变更批准、发布决定 | 唯一责任主体 |

性价比分工：Fable 5 集中在错误代价高、推理密度大的任务；样板代码交 Codex；Claude Code 内琐碎任务可临时切换低档 Claude 模型，不改变角色结构。

双模型体系固有弱点的三重补偿：L1 差分裁决首先以外部历源与规范条款为准（模型分析只是导览）；Codex 对每个差分事件并行出具独立假设（互不可见）；纯推理型、无客观 Oracle 的分歧一律升级本人亲自查证。

### 1.2 Attestation（角色规则可执行化）

每次代理工作生成签名式 attestation 随 PR 归档：

```yaml
artifact_id: / timestamp:
provider: / model_id: / model_release:
agent_role: implementer | reviewer | reference_implementer
session_id: / run_manifest_id:
source_repository: / source_commit:
generated_files: [] / reviewed_files: []
```

高风险 PR 合入条件（CI 校验）：`author attestation + 异厂商 reviewer attestation + 本人签署` 三者齐备。

**高风险路径清单**：

```text
engine-paipan/**    contracts/**    prompts/**    consult-engine/**
rulebase/approved/**    evals/**（评测器与指标代码）    governance/**
密钥与数据处理路径
```

评测代码特别提示：修改评分器有时比修改被评分的提示词更危险；评测器变更须本人批准并附冻结基线模型回溯验证。

---

## 2 运行态：三模型会诊体系

### 2.1 辩手与盲评者

内部工程命名一律 `debater_a / debater_b / debater_c / judge`；"三师""主审"仅用于 UI 文案。

**观察模式默认绑定**（日常使用）：

| 槽位 | 当前默认模型 | 绑定流派 |
| --- | --- | --- |
| debater_a | Claude（Sonnet 级） | 子平格局派 |
| debater_b | GPT（5.x） | 旺衰扶抑派 |
| debater_c | DeepSeek（V 系） | 调候派 |
| judge | 三家轮换 | 无流派 |

盲派不由任何辩手兼任（工作量不对等污染比较），作为独立实验条件或第二轮单独分析步骤。

**judge 定位**：judge 不是独立的第四真值源——三家供应商均已有模型参与本场辩论。每场按平衡计划从三家轮换取一路全新、无状态、未见辩手身份的会话做盲评；候选论断顺序随机、格式统一、模型与流派身份脱敏。轮换制仅用于跨场平衡各家系统性偏差，不作为单场独立性保证。证据不足时 judge 必须允许输出 `unresolved`，不得强制选边。

### 2.2 仲裁流水线（确定性校验前置）

```text
辩手原始 claim
→ 确定性规则校验器（规则存在性、条件触发、引用真实性——机器验证，不由 judge 自证）
→ 证据矩阵
→ 身份脱敏 + 候选顺序随机化
→ judge 盲评
→ 裁决 ∈ { A | B | C | partial | unresolved }
```

judge 只能评价经确定性校验的证据，不得自行声称"规则库校验通过"。

**偏差监控指标**（入月度评测）：

```text
position_bias_score       # 交换候选顺序后裁决变化率
judge_family_bias_score   # 某家 judge 偏向同厂辩手的程度
辩手采纳率 / 质证胜率 / 置信度分布
  （若 Claude 辩手系统性占优且无法用流派解释 → 触发提示词复查）
```

### 2.3 研究评测模式：3×3 拉丁方（解除模型×流派混杂）

固定绑定下的差异无法归因于模型或流派。**所有形成研究结论的评测均采用平衡轮换设计，不以固定绑定结果推断某一模型或流派的优劣**：

| 批次 | Claude | GPT | DeepSeek |
| --- | --- | --- | --- |
| A | 子平 | 旺衰 | 调候 |
| B | 旺衰 | 调候 | 子平 |
| C | 调候 | 子平 | 旺衰 |

由此分别估计模型效应、流派效应、模型×流派交互。工程代价：研究模式评测成本约为固定绑定的 3 倍；辩手提示词骨架必须彻底模型无关——`prompts/base/` 骨架 + `prompts/schools/` 流派模块 + `prompts/provider-adapters/` 仅处理格式差异。

### 2.4 两平面交叉污染防线

为辩手写提示词的 Fable 5 与辩手 Claude 同门，Codex 与辩手 GPT 同门。四条防线：Codex 对全部辩手/judge 提示词做对称性盲审计（信息量、约束严格度、示例质量对等）；Change Eval 固定含提示词骨架互换模型测试；2.2 偏差指标常态监控；**开发/运行单向阀**——运行态模型永不写代码，开发会话中的临时 prompt 片段禁止直接上线，一切提示词经 Change Eval 闸门。

---

## 3 核心工程原则

### 3.1 四句基本表述

一、**分歧处理**：任何双实现不一致均生成差分事件。AI 整理证据与提出根因假设，最终由本人依据规范、原始历源与 ADR 签署裁决；参与实现的模型不得担任该事件的唯一分析者。

二、**正确性**：双实现与多历源构成多重佐证信号，一致仅表示当前观测范围内未发现差异。正确性结论必须同时满足：来源独立性审计、规范条款全覆盖、性质测试通过。

三、**可复现**：对托管模型调用追求可审计、可回放、统计稳定，不承诺位级可复现；温度与种子只是 manifest 中的普通字段。

四、**评审**：Codex 负责风险分诊与严重问题提示；高风险路径（1.2 清单）的 diff 本人必须完整审阅。

### 3.2 三层 Oracle（L1 正确性框架）

| 层级 | 内容 |
| --- | --- |
| 规范 Oracle | 分级承诺规格（5.1）：条款编号 + 条款-测试映射 |
| 外部 Oracle | 经谱系审计的历源（确认无共同算法/数据源）、天文年历、人工核验样本 |
| 性质 Oracle | property-based、metamorphic、边界、mutation 测试 |

### 3.3 双层 Manifest

**run-manifest**（每次模型调用）：

```yaml
run_id: / timestamp:
provider: / model_id: / model_release:
input_hash: / system_prompt_hash: / prompt_bundle_hash:
rulebase_commit: / retrieval_manifest:
sampling_parameters: / output_schema_version:
response_hash: / token_usage: / cost:
```

**consultation-manifest**（每场会诊）：

```yaml
consultation_id: / protocol_version: / case_id: / case_input_hash:
experiment_arm: S1 | P3 | D3 | D3J
model_school_assignments:
  - role: debater_a
    provider: / resolved_model_id: / reasoning_mode:
    school: / run_ids: []
judge:
  provider: / resolved_model_id: / run_id: / candidate_order_seed:
evidence_pack:
  version: / content_hash: / retrieved_chunk_hashes: []
randomization:
  assignment_seed: / candidate_order_seed: / decoy_selection_seed:
outputs:
  final_claim_set_hash: / verdict: / unresolved_claim_ids: []
evaluation:
  dataset_version: / evaluator_version: / human_rating_lock_timestamp:
```

**模型配置可执行化**：架构文档可写槽位泛称，实验配置必须落到 resolved_model_id；thinking / non-thinking 等推理模式视为不同实验条件。`governance/model-routing.yaml`：

```yaml
role_slot: gpt_debater
configured_alias: gpt-5.x            # 具体 ID 以接入时官方文档为准
resolved_model_id: <接入时锁定>
reasoning_effort: high
fallback_policy: fail_closed         # 研究模式禁止静默 fallback：
routing_policy_version: 1.0.0        # 模型不可用 → 该场标记不可比较
```

回归比对不做字符串相等，测：JSON Schema 合法性、核心 claim 稳定性、规则引用一致性、多次调用统计波动带。

### 3.4 Claim Schema

**computed_fact 只能由 L1 注入**，携带引擎签名，模型不得自行输出此类型：

```json
{ "claim_type": "computed_fact",
  "origin": "engine-paipan", "engine_version": "…",
  "calculation_hash": "…", "value": "…", "uncertainty": null }
```

**confidence 禁用自由字符串与未校准数值**：

```json
{ "confidence_label": "low | medium | high",
  "confidence_basis": "rule_match | source_support | synthesis",
  "calibration_version": "…" }
```

**证据逐条绑定**：

```json
{
  "claim_id": "c-001",
  "claim_type": "computed_fact | school_rule | model_synthesis | reflective_prompt",
  "school": "ziping",
  "claim": "…",
  "evidence": [
    { "rule_id": "R-102", "source_id": "S-008",
      "source_locator": "卷三·第十二节",
      "condition_match": true, "entailment": "direct" }
  ],
  "counterevidence": [],
  "support_status": "supported | partial | unsupported | disputed",
  "limitations": []
}
```

验收分层：L1 可讨论计算正确性；L2–L4 只讨论规则忠实度、一致性与来源，不因多模型一致而宣称预测得到验证。

---

## 4 仓库结构（四仓）

```text
sanjian-contracts/                  # 唯一事实源，不可变 tag 发版
├── paipan-spec.md                  # 分级承诺规格
├── schemas/                        # paipan / claim / run-manifest / consultation-manifest
├── public-fixtures/
└── CHANGELOG.md
    # canonicalization 只做：JSON 字段排序、数值格式、序列化、枚举归一化
    # 禁止放入节气、日期、时区、四柱等任何领域计算

sanjian/                            # 主仓库（Fable 5 与 Codex 主工作区）
├── docs/DESIGN.md                  # 本文档
├── CLAUDE.md / AGENTS.md           # 由 governance/ai-invariants.yaml 渲染生成，勿手改
├── governance/{ai-invariants.yaml, claude-overlay.md, codex-overlay.md,
│               model-routing.yaml, role-separation.yaml}
├── docs/{adr, specs, research-notes, prereg}
├── engine-paipan/                  # Rust 主实现（tag 引用 contracts）
├── golden-tests/{fixed, boundary, stratified, metamorphic, regression, oracle-sources}
├── evals/                          # 只含 schema、公开 smoke/change 集、运行器、指标定义
├── rulebase/{approved, staging, rejected, schemas, provenance}
├── prompts/{base, schools, provider-adapters, manifests}
├── consult-engine/ ├── backend/ ├── web/ ├── security/ └── infra/

sanjian-paipan-reference/           # 参考实现仓（Codex 独立环境）
└── Python 参考实现（tag 引用 contracts；无主仓库访问）

sanjian-evals-private/              # 私有评测仓（本人 + 受保护 CI 可见；开发代理不可见）
├── sealed-holdout/                 # 50 例，一个重大版本周期
├── rotating-shadow/                # 50–100 例，定期更换
├── human-labels/ ├── expected-evidence/ └── scoring-keys/
    # CI 只向主仓返回聚合分数，不返回测试内容
```

双实现构建产物记录 `contract_version + contract_commit + contract_content_hash` 三元组。

`ai-invariants.yaml` 核心条目（渲染进 CLAUDE.md 与 AGENTS.md）：engine-paipan 零 LLM / 零网络 / 零系统时钟依赖；历法事实一律取自钉版数据文件（tzdata、天文数据），禁止 AI 从记忆写历法常量；rulebase/approved 对所有 AI 只读；contracts 变更先出 RFC 经本人批准；每次模型调用落 run manifest；真实个人数据不进 AI 开发会话（开发一律用合成盘）。

---

## 5 L1 规格与测试体系

### 5.1 分级承诺

天文可算 ≠ 民用时间可换算 ≠ 时刻转换无误差，三者分开承诺：

```yaml
astronomical_computation_range: { start: 1600, end: 2200 }
civil_time_support:
  verified:                 # 按国家/地区/时期列出人工核验区间（中国近现代优先）
  tzdb_supported: { policy: pinned_tzdata }
  historical_best_effort:   # tzdb 对 1970 年前不保证可靠
    before: 1970
    require_uncertainty_flag: true
  future_provisional: { require_rule_version: true }
tolerance_policy:
  astronomical_numeric_error:
  delta_t_uncertainty_by_epoch:    # ΔT 不确定性按年代分档，无统一 ±1 秒
  civil_time_source_confidence:
  boundary_classification_policy:
```

### 5.2 不确定性传播

若输入时间精度、历史时区置信度或天文不确定性足以跨越节气、时辰或日界，L1 不得强行返回单一命盘，而返回候选集与来源：

```json
{
  "input_time_precision_seconds": 300,
  "timezone_confidence": "historical_best_effort",
  "boundary_distance_seconds": 120,
  "result_status": "ambiguous",
  "candidate_charts": ["chart_a", "chart_b"],
  "uncertainty_sources": ["input_precision", "delta_t"]
}
```

下游会诊对 ambiguous 输入的处理协议（并行双盘会诊或提示补充信息）为独立规格条款。

### 5.3 测试语料七类

固定黄金集（起步 500–1000 例，人工可复核）；规格条款测试（条款-测试映射全覆盖，CI 统计）；边界集（节气交接 ±5 分钟、真太阳时跨日、1988 夏令时、早晚子时、时区重叠与空洞、历史五时区）；分层随机集（时间 × 时区 × 经纬度 × DST × 输入精度 × 流派 × 边界距离，按配额生成）；metamorphic（如经度东移 15° 与真太阳时的关系式）；mutation（月度，验证测试网灵敏度）；缺陷回归集（每个差分事件裁决后永久入库）。

对拍协议预定义：完全相等字段（四柱、大运序列）、epsilon 字段及数值、边界舍入归属；canonicalization 由 contract 包提供（仅格式层）。

闸门层级：本地 hook = 快速反馈；CI required check = 合入闸门；branch protection = 强制（绕过须在 commit message 记录原因）。失败用例自动最小化并归档。

---

## 6 规则库与语料治理

目录权限：`approved/` 对全部 AI 与自动化只读，合入仅经本人签署；`staging/` 为 AI 草稿区；`provenance/` 逐条记录：

```yaml
source_id: / source_edition: / source_locator:
license:                 # 公版原文 / 需授权的校注、译文、整理本
extractor_model: / extractor_prompt_hash:
reviewer: / review_decision: / approval_signature:
```

版权：古籍原文公版，但现代标点本、校注、译文、数据库整理成果可能仍有权利，按具体版本登记 rights registry；若未来公开任何衍生内容须回头清理。

RAG 硬边界（指令模式扫描仅为辅助）：

```text
检索文本只进入 data-only 字段，与指令通道物理分离
检索内容不能修改 system policy、不能直接触发工具
RAG 会话无密钥、无写权限
工具调用一律 allowlist
```

---

## 7 评测体系

### 7.1 四实验臂（回答核心研究问题）

| 臂 | 配置 | 回答什么 |
| --- | --- | --- |
| S1 | 最佳单模型一次作答 | 基线：不辩论值多少 |
| P3 | 三模型独立作答，确定性合并，无质证 | 增益是否只来自模型数量 |
| D3 | 三模型质证，无 judge | 质证过程本身的贡献 |
| D3J | 三模型质证 + judge 盲评 | 仲裁步骤的边际贡献 |

若 D3J 相对 S1 无显著质量增益而成本数倍，这本身就是本项目的有效研究结论。

### 7.2 指标体系

```text
abstention_precision / abstention_recall        # 防"什么都不说"刷分
citation_exists / citation_locator_correct
citation_condition_applicable / citation_entails_claim
unsupported_claim_rate ↓（核心）
position_bias_score / judge_family_bias_score
schema_valid_rate / cross_run_stability
human_blind_preference / unresolved_rate / cost_per_report / latency
共识率、分歧率：仅作行为描述指标，永不作为优化目标
```

目标形态：有据处成共识、真实流派差异处保留分歧、缺据处弃权。

### 7.3 评测规模与治理

| 层级 | 规模 | 触发 | 存放 |
| --- | --- | --- | --- |
| Smoke | 20–30 | 每次本地修改 | 主仓（公开） |
| Change Eval | 100 分层 | 每次 prompts/协议 PR | 主仓（公开） |
| Monthly Eval | 300 | 每月 | 混合 |
| Sealed Holdout | 50 | 重大版本 | 私有仓 |
| Rotating Shadow | 50–100 定期更换 | 季度 | 私有仓 |
| 人工盲评 | 20 抽样 | 每月 | 私有仓 |

治理三条：候选提示词、评测器提示词、指标计算代码不得在同一 PR 中修改；评测器变更须冻结基线模型回溯验证 + 本人批准；私有仓 CI 只回传聚合分数。

提示词工作流：Fable 5 起草 → Codex 对称性盲审计 → Change Eval（含骨架互换测试）→ 本人批准。Sealed Holdout 对起草模型物理不可见（第 4 节仓库隔离保证）。

---

## 8 标准工作流（单功能生命周期）

1. **规格**：Fable 5 起草 spec（条款编号、Oracle 指定、分级 tolerance），Codex 评审，本人批准 → contracts 仓发 tag。
2. **并行实现**：Fable 5 主仓写 Rust；Codex 独立环境依同一 contract tag 盲写 Python。
3. **对拍**：CI 灌固定集 + 分层随机集 → 差分事件（附双方推导链）。
4. **证据分析**：Fable 5 与 Codex 并行各出证据报告（互不可见，Codex 报告为强制项）。
5. **裁决**：本人依据规范 + 原始历源 + 两份报告签署；真实流派分歧转配置项。
6. **合入**：attestation 三件套齐备 + 高风险 diff 本人全量审阅；裁决入 ADR，失败用例入回归集。

低风险任务简化流：Fable 5 或 Codex 实现 → 异厂商抽查 → 本人合入。全流程仅用于 L1 计算路径与 L4 仲裁逻辑等错误代价高的模块。

---

## 9 安全与合规

### 9.1 五项威胁

1. **RAG 提示注入**：按第 6 节硬边界处理。
2. **密钥与数据边界**：密钥经密钥管理注入，不进仓库不进 AI 会话。
3. **成本失控**：供应商侧月度硬预算 + 网关侧单日熔断 + manifest cost 周度汇总；拉丁方与四臂实验开跑前先估算批次成本。
4. **开发代理与软件供应链**：仓库内 README、依赖包、脚本、下载内容对开发代理均按不可信输入处理；高风险命令须批准；开发代理不可读取运行态密钥；依赖锁定并生成 SBOM。
5. **运行日志与供应商数据外发**：请求体、trace、错误日志、模型响应可能含命盘信息；日志默认脱敏、限期保留；供应商数据政策登记并定期复核。

### 9.2 数据流分层

数据库在本地不等于数据不离机——发给三家云端 API 的内容已经离开本机：

```text
仅本地 L1 可见：  原始出生日期、时刻、地点、姓名
发送给运行态模型：最小化后的命盘结构（四柱、大运、流派特征）与必要规则引用
禁止发送：      姓名、联系方式、精确地址、任何账号标识
模型日志：      默认脱敏
```

`security/vendor-register.yaml` 逐家登记：data_sent_fields / retention_policy_snapshot / training_opt_out / region / account_project_id / terms_checked_at，季度复核。

### 9.3 法律定位

本项目当前仅由本人使用，不向中华人民共和国境内公众提供服务，且设计目标不包含持续性的情感照护、陪伴或支持互动；据此，现阶段一般不落入《人工智能拟人化互动服务管理暂行办法》（2026-07-15 施行）第二条所述适用范围。科学研究性质本身不构成当然豁免。任何对外分发、公众访问、持续陪伴式交互或第三方参与范围扩大，均须重新进行适用性判断，并同步触发《生成式人工智能服务管理暂行办法》与 AI 生成内容标识义务的评估。本文档不为公开运营提供合规依据。

**私用呈现层的吉凶落地（2026-07-14，本人裁定）**：本人研究用途下，白话呈现层可给出**概率化的吉凶倾向**并配「预测→回访→命中率」验证闭环——用生活结果检验解读，而非以措辞回避。仍守边界：不说「必然/注定」等把话说死的词；财运给吉凶倾向与时机、但**不出具体买卖/投资交易建议**（本人自行决策，以真实盈亏记入命中率验证）；健康给倾向提示并**一律提醒就医**、不做疾病确诊、不断言必得重病、不碰生死；「改命术」类（改运/消灾/转运…）继续禁。此调整不改变上文「仅本人使用、不向公众提供服务」的定位；任何对外开放仍须先做适用性判断。

---

## 10 巴纳姆自盲实验（预注册版）

**预注册**（开跑前冻结于 `docs/prereg/`）：主要假设、主要指标、最少/最大批次数、停止规则（不得"看到显著即停"；序贯分析用预先声明的边界）、排除规则、干扰盘生成方法、分析方法。揭盲前评分锁定。

**评分设计**：强制匹配（一份真盘报告 + 2–4 份匹配干扰报告，判断哪份属于自己）与成对比较（真盘 vs 匹配干扰盘，随机左右，选"左更像我 / 右更像我 / 无法区分"）。

**干扰盘匹配维度**：报告长度、正负面措辞比例、claim 数量、置信度分布、引用数量、主题类别、输出模型与协议版本。历史名人盘不入主实验（隐性线索），一律用完全合成的匹配盘。

**实验期间 UI 强制实验模式**（第 0 节）。

**结论边界**：无论结果方向如何均可形成研究记录；但样本量不足、盲法失效或统计功效不足时，结果只能判定为不确定，不得据此支持或否定个性化区分度。可选扩展：5–10 位知情同意亲友参与，数据仅本人研究使用、可随时删除。

---

## 11 阶段路线

**P1（当前）**：四仓与治理脚手架 → "年柱判定"端到端彩排（双实现对拍 + 红队演练）→ 扩展节气、真太阳时、四柱、大运 → L1 达到黄金集全通过。

**P2**：规则库 schema 与录入工具链 → 单模型速览管线 → 三模型会诊协议（观察模式）→ 四实验臂基础设施。

**P3**：研究模式（拉丁方）评测 → 巴纳姆预注册实验 → 研究记录整理。

---

## 12 启动清单（工作区，直接更新）

- [x] 建四仓：sk / sk-contracts / sk-paipan-reference / sk-evals-private（2026-07-14；实际命名用 sk- 前缀）
- [x] governance/ai-invariants.yaml（v3.0,十二条）+ 渲染脚本 → 生成 CLAUDE.md / AGENTS.md（CI 同步校验）
- [x] role-separation.yaml（attestation 三件套 + 高风险路径清单）+ attestation 模板 + CODEOWNERS
- [x] 数据分级清单 + 数据流分层 + vendor-register.yaml 骨架；API 月度预算上限为本人控制台动作项（data-classification.md 第四节,**未完成**）
- [x] 规格已超出最小范围：spec v0.2（年柱已评审 + 四柱条款,条款-测试映射见附录 C）→ sk-contracts 发 tag v0.2.0；分级承诺与 ambiguous 候选盘条款已入 sk-contracts v0.3.0(spec 4.5/第 5 章,RFC-0001)并经主实现+呈现层落地
- [x] Fable 5 主仓 Rust 年柱+四柱模块（attestation 自 PR #6 起归档）；Codex 独立环境盲实现已完成（gpt-5.6-sol,双方 attestation 归档;异源双实现信号自此成立）
- [x] CI：build → 单元/属性 → 契约钉版校验 → 边界 → 差分（能力域）→ 归档；required checks + branch protection 已生效(2026-07-14,管理员不可绕过);失败用例自动最小化待补
- [x] 红队演练：边界舍入 / 期望值投毒 / 锚点篡改三项注入全部拦截（research-notes/red-team-drill-2026-07-14.md）;错误时区、评审漏报两项按范围顺延并留触发条件
- [x] 外部 Oracle 首批：JPL DE440s 自算节气 + HKO 分钟级核对 + KASI/中研院日柱锚双源（谱系相互独立）;紫金山《中国天文年历》采购待办

## 13 迭代日志（工作区，直接更新）

| 日期 | 事项 | 结论/链接 |
| --- | --- | --- |
| 2026-07-13 | 环境搭建 + 历源首批入库（PR #2） | 节气 4824 条,HKO 核对最大偏差 30 秒 |
| 2026-07-14 | V2.1 治理迁移（PR #3）+ 红队演练（PR #4） | 三项注入全拦截,协作机制成立 |
| 2026-07-14 | V1.0 四柱 + 本地测试页（PR #5,本人验收通过合并） | spec v0.2;93 例黄金集;日柱锚 KASI/中研院双源闭合 |
| 2026-07-14 | V3.0 落地：四仓 + attestation + 契约钉版（PR #6） | sk-contracts@v0.2.0;lock 校验入 CI |
| 2026-07-14 | main 分支保护生效（六项必过检查,不可绕过） | 启动清单 CI 项闭环 |
| 2026-07-14 | 契约 v0.3.0：不确定性 op + 分级承诺（RFC-0001,PR #7） | 模糊时刻返回候选双盘;黄金集 102 例 |
| 2026-07-14 | 三家 API 通道打通（PR #8/#10） | claude-sonnet-5 / gpt-5.1 / deepseek-chat 冒烟通过 |
| 2026-07-14 | L4 三模型会诊引擎（PR #11,D3J 观察模式） | 三辩手绑流派质证 + 轮换裁判盲评;真实会诊:1共识/5分歧/2未决,命中"有据共识·分歧保留·缺据弃权" |
| 2026-07-14 | 四实验臂评测框架（PR #12,eval-smoke） | S1/P3/D3/D3J 自动指标对照;smoke 观察:仅 D3J 有弃权机制(均弃权率 0.2),成本 S1→D3J 约 1→7 倍;红线 0/过度自信 0 |
| 2026-07-14 | 拉丁方研究模式（PR #13,research-smoke） | 3×3 轮换分离模型/流派效应 + 提示词对称性校验入 CI;单盘演示:观点数量为"模型特性"(Claude 4/GPT 3/DeepSeek≈2.7)而非流派特性,固定绑定不可分、轮换后可归因 |
| 2026-07-14 | Codex 盲写参考实现完成（gpt-5.6-sol,独立会话,自带 102 测试） | 对拍能力域扩至 four_pillars;10092 例双实现一致;SPEC-QUESTIONS 零歧义 |
| 2026-07-14 | 巴纳姆自盲实验预注册（PR #14,barnum-smoke） | 预注册冻结(docs/prereg + prereg.lock + INV-13 校验闸,篡改即阻断)+ 干扰盘匹配 packet + UI 实验模式页 + 揭盲精确二项评分;自动代理指标(巴纳姆率/具体性/可证伪)并入四臂 metrics;离线演示:巴纳姆报告 barnum 1.0/specific 0.0 vs 具体报告 0.25/0.75,词面代理可区分(仅描述、不替代人类盲判) |
| 2026-07-14 | 白话综述层 + 吉凶落地（PR #16） | 会诊末加 L5 白话综述(presenter=claude-sonnet-5):按性格/事业/财运/感情/近期时机分域说人话,可直说吉凶倾向但用概率化措辞;红线放开「预测」、保留「必然/注定」与改命术类;三条底线(不说必然·不掺投资买卖·不断生死重病)由提示词 + 后端 scrub 双重把关;presenter 失败优雅降级到专业视图。真实会诊验证:辛亥日盘白话输出无术语、无禁忌词。配套「预测→回访→命中率」验证闭环见后续 PR |
| 2026-07-14 | 预测→回访→命中率 验证闭环（PR #18） | consult-engine/predictions.py 存储(gitignored,本机私有)+ /api/predict/save·list·review;白话每域可「记录为预测」留时间窗,到期自动进「待回访」标命中/未中/部分,命中率含部分按 0.5、按领域分解;落实「数据越多越准」(§10 精神:让命理能被检验)。后端闭环冒烟通过(存→到期→回访→命中率 1.0);疾病域补齐(PR #17,六域 + 就医提醒) |
| 2026-07-14 | 大胆具体 + 流年逐年（PR #21） | 反笼统(巴纳姆):辩手 v2 放开 3–5 条、要求锚定干支/十神、禁「谁都适用」空话(守对称性);白话 presenter v2 大胆具体 + 六域(加六亲)+ yearly 逐年流年推演;luck.py 算流年(锚 1984 甲子),会诊传入未来 8 年。真实会诊验证:输出具体到「30 岁前后转折、35 岁落脚」+ 逐年干支推演(2026 丙午…2033 癸丑),禁忌词 0、健康带就医、财运给倾向不给交易指令。深度增加,耗时约 3.5 分钟(仍 <6 分钟上限)。巴纳姆自盲实验可再测此改动是否真降低了笼统度 |
| 2026-07-15 | 完整版:大运 + 神煞 + 性别（PR #22） | luck.py 加 dayun(阳男阴女定顺逆、月柱起、起运=节气距÷3 近似)+ shensha(桃花/驿马/华盖/天乙贵人/文昌/羊刃,标准规则);排盘 meta 暴露出生时刻/节气边界(起运用);表单加性别;会诊传大运+神煞,presenter 输出 dayun 解读、流年挂靠大运;web 显示大运时间轴(标「现在」)+ 神煞标签。真实验证(男命):天乙贵人午、乙酉大运末→2027 换丙戌、流年正确挂靠大运。四柱+神煞+大运+流年骨架完整。耗时约 4.7 分钟,前端上限提至 450s。注:大运/神煞现由 Python 后端算(待迁 Rust + 对拍以达 L1 严谨) |
| 2026-07-15 | 个人背景贯穿 + 追问对话（PR #23） | 反「大路货」:表单加行业(15 选项)/职业/目前状况,profile 贯穿辩手与白话(推演落到实际处境;实测:程序员纠结跳槽 → 直接回答「创业公司要挑有产品雏形有资本背书的」、2026 为跳槽关键年)。追问对话:/api/chat/start(异步,单模型 1 次调用,约 9–60s)+ prompts/base/presenter/chat.md——用户反驳/补充当**新数据**重新推,该修正就明确修正(revised 字段),并给可验证预测(suggestion,可一键记录进命中率);web 聊天界面,历史客户端持有(最近 8 轮)。修 bug:辩手带背景后内容变长,sonnet-5 思考+正文超 3500/5000 截断 → max_tokens 8000 + 提示词硬限单条长度(claim≤120 字)。实测追问:「想转管理」→ 按 2027 丙戌大运正官重推并修正旧结论 |
| 2026-07-18 | 组织合盘「势」(PR #33 并入) | 公司走向=主事人+关键人+开业盘的合力。确定性层(luck.py,可对拍):十神互参(shishen)/地支六合六冲六害刑半合(branch_rel)/五行分布与互补(chart_elements,pair_analysis)/流年分别打在各盘;公司成立时刻自起一盘(开业盘);时辰不明按三柱诚实降权。AI 只翻译矩阵(group.md,禁自算干支)。web 折叠卡:动态添加关键人(≤6)+公司日期,输出 overview/各人今年/关系互参/可验证时间窗(可记录为预测) |
| 2026-07-17 | 精准化四件套(账户迁移重建后;PR #33) | ①排盘根基:真太阳时(经度差+均时差,39城下拉;乌鲁木齐实测时柱壬辰→辛卯)+大运精到月+神煞补全(禄神/红鸾/天喜/将星/孤辰/寡宿/空亡);②流月:五虎遁+节气表定十二流月(干支/日期确定性,模型只解读),验证周期年→月;③对照盲测:验过去混入随机盘反推,揭盲出真盘vs随机盘命中率差值(区分度检测器),随机盘不入档案;④快速会诊(S1,~85s)替代AI速览+双击启动脚本(启动三鉴.command)。大运/神煞/真太阳时仍待双实现对拍(诚实记录) |
| 2026-07-15 | 盘前验证(铁口直断过去)+ 个人档案（PR #25,产品差异化核心） | 「先证明,再预测」:/api/backcast(单模型 1 次,~12s)从命局+大运+过去十年流年反推 8–10 条过去大事(只挑冲合明显年份、吉凶都断、每条可打分),本人逐条打分 → 当场出「过去命中率」;打分入 consult-engine/dossier/(按 birth 哈希聚合,gitignored)→ dossier.summary 注入后续会诊/追问 profile 做校准(已确认「准」的作锚点、「不准」的避同类错)。backcast 不喂档案(防作弊循环)。真实验证:10 条覆盖 5 域、具体可打分,模拟打分 6/8 → 命中率 75%、摘要正确生成。web「① 验过去·铁口直断」为推荐第一步 |
| 2026-07-15 | 我的大事记:已知事实校准 + 命×环境合成（PR #28） | 回应用户「历史已知,把当年情况和改变加进去;行业/合伙人/贵人/平台/政策/风口都影响走向」——推演=命局倾向×现实处境。dossier 加 facts(add/del/list,每年真实事件+当年现状,gitignored);已知实录以最高优先注入会诊与追问(「推演须与之一致并据此校准」);plain_summary/chat 提示词加两条:事实锚点不得矛盾、命×环境合成(先命局倾向再现实条件,点명依据来源)。**backcast 仍不喂大事记(盲测防作弊)**。web「我的大事记」面板(按当前排盘生日增删);行业加「直播/电商」。零成本闭环验证 |
| 2026-07-15 | 时辰校准(定时辰)（PR #26） | 不确定出生时辰 → 13 个候选时辰各排一盘(本地引擎免费,含晚子时单列)+ 本人自述大事 → 单模型比对排出前三(fit/干支级理由/进一步区分问题);「用这个时辰」一键填回表单。真实验证:13 候选、10s,推理落到干支(酉冲寅→被动换工作),note 诚实提示信息量不足并建议补充。表单「不确定时辰?」入口 |
| 2026-07-15 | 会诊记录存档 + 历史查看（PR #24） | 刷新不丢:每场会诊自动存 consult-engine/records/(gitignored 本机私有,含命盘/背景/完整载荷);追问对话也追加到记录。/api/records/list·get;web「历史记录」按钮 → 列表 → 查看(复用 renderConsult 渲染,回填四柱头部、回放追问对话、可继续追问);renderConsult 从点击处理器中抽出为通用函数。零成本端到端验证(save/list/get/append_chat) |
| 2026-07-14 | P2 启动：L3 网关 + run-manifest + 单模型速览（PR #8） | fail_closed/日熔断 50/manifest 落盘;密钥仅本机进程;Smoke/Change Eval 体系待建（INV-12 缺口,评测基建随 P2 补） |

---

*私人研究项目工程设计；不构成对命理预测效度的任何主张，亦不为公开运营提供合规依据。*
