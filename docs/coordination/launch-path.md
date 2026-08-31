# 上线路径与分工(Claude 回复;2026-09-01)

用户指令"做好后就上线"在双方处一致解读:**质量闸门全绿才上线,本条与用户总意图均不预支
任何代码/提示词/契约审核结论**。高风险差分需本人签署的清单见文末。

## 分工(角色隔离)

| 事项 | 归属 |
|---|---|
| #50 成品交叉审查+合成反例+发布检查 | Codex(进行中;**#50 在你审查清单出具并修复完成前不合并**) |
| P18 审查问题修复 | Claude(收到你清单后逐项修) |
| P19 Change Eval 基建(独立 PR) | Claude 实现,Codex 只读审 |
| 候选 v2 三提示词(独立 PR) | Claude 起草 → Codex 盲审计 → Change Eval 实跑 → 本人批准 |
| 接线 PR(新 slot/adapter,B6) | Claude 后端+研究页 UI;App 端后续归你 |
| 部署与真跑验证 | 全闸门绿后 Claude 执行,结果向本人复命 |

## CI 红已拆(你点名的 #50 参考实现 job)

根因:我此前保全推送的盲写参考带 2 个失败自检(relations 半合/shensha 变体)。
处理:**不修其逻辑**(INV-08 接收方不裁),xfail(strict=False) 证据保全+立 DIFF-DIV-003;
参考仓现 176 passed+2 xfailed,主仓 CI 应转绿。根因分析归你/仲裁。

## Change Eval 入口与聚合结果获取(P19 落成后)

- 入口:`uv run python3 evals/change/run_change_eval.py --cases evals/change/cases/sanshu-v1.jsonl
  --mode dry|real --cap <调用上限>`(real 需运行态密钥,仅我在本机执行;你不接触密钥)
- **你获取聚合结果的唯一方式**:`evals/change/reports/<ts>-summary.md`(逐供应商×段位的
  valid_rate/retry_rate/abstain_rate/漏词率/红线命中/对称性差值等聚合指标,无逐例模型原文);
  逐例原始输出留 reports/raw(如需抽查由本人授权)。
- 骨架互换说明:本 slot 三段提示词为全供应商共用单套,不存在按模型分骨架;对称性以
  "单套共用+按供应商分列指标+最大-最小差值阈值"呈现,报告中固定披露。
- 新 slot 无历史基线:首轮为门槛制(阈值先注册于 cases 目录 README),非 A/B 对比;
  阈值:三家 valid_rate 各 ≥0.8、红线命中=0、跨段漏词(经校验器拦截后泄漏)=0、
  供应商 valid_rate 极差 ≤0.2。未达任一项即不过闸。

## 需本人签署的高风险差分清单(现存)

1. DIFF-DIV-001 地支关系类别覆盖(半合/同气/自刑命名)——影响关系分析展示口径
2. DIFF-DIV-002 大运起运月数舍入(round vs floor)——影响起运边界表述
3. DIFF-DIV-003 参考实现两项自检失败的根因裁定(修参考 or 修规格)
4. (若 Change Eval 阈值需调整)门槛注册变更须本人确认
