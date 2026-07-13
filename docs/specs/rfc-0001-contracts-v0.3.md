# RFC-0001:契约 v0.3 —— 不确定性传播与分级承诺

| | |
| --- | --- |
| 状态 | 已批准(2026-07-14 本人指示起草并随 PR 合并签署;INV-05 流程) |
| 影响 | sk-contracts v0.2.0 → v0.3.0;主实现新增 op;参考实现随后扩展 |

## 动机(DESIGN V3.0 §5.2)

输入时间精度(出生时间常只记到分)与判界距离共同决定命盘可靠性。若时刻可能落在
立春/节界/时辰界/日界的任一侧,L1 不得强行返回单一命盘。

## 变更

1. **新增 op `four_pillars_uncertainty`**(spec 4.5,条款 AMB-1…5):输入 = four_pillars +
   必填 `input_time_precision_seconds`;输出 = four_pillars + `result_status` /
   `boundary_distance_seconds` / `uncertainty_sources`。
2. **调用方候选盘协议**:ambiguous 时呈现层对 `t±p` 分别重解析上下文并调用 four_pillars,
   给出去重候选盘;引擎不承担上下文重解析(维持注入纯度)。
3. **第 5 章分级承诺**:天文范围/节气容差/ΔT/tzdb 分层承诺表,替代模糊的"±1 秒"单一口径。

## 兼容性

`four_pillars` 输入输出**位级不变**;新能力走独立 op,参考实现在其 v0.2 范围内的对拍
不受影响,能力域(runner `--ref-ops`)在参考实现跟进 v0.3 前不包含新 op。

## 备选方案与取舍

- 在 four_pillars 上加可选字段:被否——输出形状随输入变化,双实现对拍语义复杂化;
- 引擎内直接产出候选盘:被否——需要引擎自行重解析 civil_year/month_ctx,违背历法事实
  注入纪律(INV-01),故候选盘装配归呈现层。
