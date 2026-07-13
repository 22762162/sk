# evals(运行态评测体系,dev-plan V2.1 第 6 节)

| 目录 | 规模 | 触发 |
| --- | --- | --- |
| `smoke/` | 20–30 例 | 每次本地 prompt/编排修改 |
| `change/` | 100 例分层 | 每次 prompts/ 或会诊协议 PR(合入闸门,含提示词对称性检查) |
| `monthly/` | 300 例 | 每月趋势监测 |
| `frozen-holdout/` | 50 例长期冻结 | 重大版本;由本人维护,起草模型不可见 |
| `safety/` | — | 注入攻击、越权指令等安全回归 |

优化目标指标:`unsupported_claim_rate ↓`(核心)、`rule_citation_coverage ↑`、
`citation_veracity ↑`、`appropriate_abstention_rate`、`schema_valid_rate`、
`cross_run_stability`、`cost_per_report / latency`。
共识率与分歧率仅作行为描述指标,不作优化目标。

评测语料在 L3/L4 搭建时随会诊协议一起落地;本目录先立结构与指标定义。
