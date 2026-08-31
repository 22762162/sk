# sanshu-v1 Change Eval 用例与门槛注册

**门槛(首轮门槛制,新 slot 无历史基线;调整须本人确认)**:

| 指标 | 门槛 |
|---|---|
| 各供应商 valid_rate(首次调用即过校验) | ≥ 0.80 |
| 红线词命中(最终留存文本) | = 0 |
| 跨段借词泄漏(校验器拦截后仍留存) | = 0 |
| 供应商间 valid_rate 极差(对称性) | ≤ 0.20 |
| abstain 率 | 仅披露,不设门槛(合法弃答不受罚) |

用例:8 例全合成(INV-07;命盘/事实均虚构),分层 scene{personal,company} ×
method{liuyao,meihua} × domain{事业,财务,合作,时机};卦由确定性引擎按用例内固定
起卦输入现场装卦(可回放)。评测器代码与候选提示词**永不同 PR 修改**(INV-12)。
聚合报告:`evals/change/reports/<ts>-summary.md`;逐例原文仅存 raw/,跨代理不传阅。
