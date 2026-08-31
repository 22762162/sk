# Change Eval 聚合 · arm=sanshu · mode=dry · 20260831T202953Z-sanshu
冻结 as_of:2026-09-01(整场共用)

| provider | n | valid_first | retried | failed | abstain(b/g/c) | leak_blocked | leak_retained | redline |
|---|---|---|---|---|---|---|---|---|
| anthropic | 100 | 100 (100%) | 0 | 0 | 0/0/0 | 0 | 0 | 0 |

## 分层维度(provider×method×scene)
| provider | method | scene | n | ok | abstain(段计) | failed |
|---|---|---|---|---|---|---|
| anthropic | liuyao | company | 25 | 25 | 0 | 0 |
| anthropic | liuyao | personal | 25 | 25 | 0 | 0 |
| anthropic | meihua | company | 25 | 25 | 0 | 0 |
| anthropic | meihua | personal | 25 | 25 | 0 | 0 |

对称性极差:0.00 · 预算余量:90 · 用量(tok) in=0 out=0
门槛判定(草案阈值,未经独立评审与本人确认不生效):{"valid_rate>=min": true, "redline<=max": true, "leak<=max": true, "provider_spread<=max": true, "coverage_full_and_budget_ok": false}
结论:DRY-PIPELINE-ONLY(非门槛判定,不得用于放行)

运行配置指纹(起跑前冻结):{"as_of": "2026-09-01", "arm": "sanshu", "mode": "dry", "cases_sha256": "bef82143f7c05a59b4f145c6bd6b8d69a93af151f8fe5cf5bd5b0b4c1db540ea", "lock_sha256": "fadfa16ab227ba6634dcd4ef0a98a7029cfcbacd83971d6a511760367b5516f8", "prompts": {"bazi": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68", "gua": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68", "combined": "600e92d4525fd8f8506cd4bcd0db931a2c5007aa19ca3ae5be28112d804ecf68"}, "prompts_source": "dry_placeholder", "baseline_prompt_sha256": null, "schema": "51188112bc3d5f2a1c37071a9f60fe8ad10bab66c7620ecce994cfe71d6a6ef1", "runner_code": "42a49f35b9a2e771bc0b69cce3fc401e201c34b39f4fe07ea09eabdad55194dd", "orchestrator_version": "sanshu-orchestrator-v2", "validator": {"schema": "sanshu-sealed-v1", "banlists": "sanshu-banlists-v1"}, "providers": [["anthropic", "claude-sonnet-5"], ["gemini", "gemini-3.6-flash"], ["deepseek", "deepseek-chat"]], "redline_words": {"status": "loaded", "count": 9}}
说明:弃答按段分列且只披露不设门槛;弃答/失败均入分母;逐例原文在 raw/<run_id>/ 不传阅。