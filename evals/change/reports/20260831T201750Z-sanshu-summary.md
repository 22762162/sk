# Change Eval 聚合 · arm=sanshu · mode=dry · 20260831T201750Z-sanshu

| provider | n | valid_first | retried | failed | abstain | leak_blocked | leak_retained | redline |
|---|---|---|---|---|---|---|---|---|
| anthropic | 100 | 100 (100%) | 0 | 0 | 0 | 0 | 0 | 0 |

## 分层维度(provider×method×scene)
| provider | method | scene | n | ok | abstain | failed |
|---|---|---|---|---|---|---|
| anthropic | liuyao | company | 25 | 25 | 0 | 0 |
| anthropic | liuyao | personal | 25 | 25 | 0 | 0 |
| anthropic | meihua | company | 25 | 25 | 0 | 0 |
| anthropic | meihua | personal | 25 | 25 | 0 | 0 |

对称性极差:0.00
门槛判定(草案,未经独立评审与本人确认不生效):{"valid_rate>=0.80": true, "redline==0": true, "leak_after_validator==0": true, "provider_spread<=0.20": true, "coverage_full_3x_all_cases": false}
结论:DRY-PIPELINE-ONLY(非门槛判定,不得用于放行)

输入指纹:{"cases_sha256": "e0cc02e4190134f033fba9a6f446c684b5e1cb248db3f1b8010cbdfb4e6437dd", "lock_sha256": "88f10c59a9ebdbac4fe265f642aa5a6da71428cf67a499a35c03fc1025824697", "prompts": {"bazi": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68", "gua": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68", "combined": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68"}, "runner_code": "db3f6d426577f1da099d098ecfb289cef5719eee878ccf0d57b2544701ee14d5", "schema": "51188112bc3d5f2a1c37071a9f60fe8ad10bab66c7620ecce994cfe71d6a6ef1", "providers": [["anthropic", "claude-sonnet-5"], ["gemini", "gemini-3.6-flash"], ["deepseek", "deepseek-chat"]], "redline_words_loaded": 9}
说明:abstain 只披露不设门槛;弃答/失败均入分母披露;逐例原文在 raw/<run_id>/ 不传阅。