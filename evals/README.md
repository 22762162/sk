# evals(运行态评测体系,DESIGN V3.0 §7)

主仓只含:评测 schema、公开 smoke/change 集、运行器与指标定义。
Sealed Holdout / Rotating Shadow / 人工标注 / 评分密钥在私有仓 **sk-evals-private**
(开发代理不可见;CI 只回传聚合分数)。

## 四实验臂(核心研究问题:三模型质证是否优于单一强模型,增益来自哪一步)

| 臂 | 配置 | 回答什么 |
| --- | --- | --- |
| S1 | 最佳单模型一次作答 | 基线:不辩论值多少 |
| P3 | 三模型独立作答,确定性合并,无质证 | 增益是否只来自模型数量 |
| D3 | 三模型质证,无 judge | 质证过程本身的贡献 |
| D3J | 三模型质证 + judge 盲评 | 仲裁步骤的边际贡献 |

若 D3J 相对 S1 无显著增益而成本数倍,这本身就是有效研究结论。
形成研究结论的评测一律用 3×3 拉丁方(§2.3)解除模型×流派混杂。

## 规模与触发

| 层级 | 规模 | 触发 | 存放 |
| --- | --- | --- | --- |
| Smoke | 20–30 | 每次本地 prompt/编排修改 | 主仓(公开) |
| Change Eval | 100 分层 | 每次 prompts/协议 PR(合入闸门,含骨架互换对称性检查) | 主仓(公开) |
| Monthly Eval | 300 | 每月 | 混合 |
| Sealed Holdout | 50 | 重大版本 | 私有仓 |
| Rotating Shadow | 50–100 | 季度更换 | 私有仓 |
| 人工盲评 | 20 抽样 | 每月 | 私有仓 |

## 指标(优化目标)

```text
abstention_precision / abstention_recall      # 防"什么都不说"刷分
citation_exists / citation_locator_correct
citation_condition_applicable / citation_entails_claim
unsupported_claim_rate ↓(核心)
position_bias_score / judge_family_bias_score
schema_valid_rate / cross_run_stability
human_blind_preference / unresolved_rate / cost_per_report / latency
共识率、分歧率:仅作行为描述指标,永不作为优化目标
```

## 治理三条(INV-12)

1. 候选提示词、评测器提示词、指标计算代码不得在同一 PR 中修改;
2. 评测器变更须冻结基线模型回溯验证 + 本人批准;
3. 私有仓 CI 只回传聚合分数,不返回测试内容。

评测语料与运行器在 P2(会诊协议 + 四臂基础设施)落地;本目录先立结构与指标定义。
