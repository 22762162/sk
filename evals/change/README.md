# Change Eval 基建(P19 v2) · 状态:未通过 / NOT-A-GATE

- 用例集:`cases/sanshu-v100.jsonl`(gen v2:中性结构合成盘,无预解释;期限词与 deadline 锁齐;
  lock 哈希闸,篡改拒跑)。**本集仅支撑结构/合规试验,不支撑测算有效性结论**;smoke8 已删除。
- real 预检三闸:冻结 lock + 本人批准文件 `thresholds-approved.yaml`(机器永不写入)+
  (基线臂)p19b 提示词已合入;任一不满足即 NOT-A-GATE 退出,不构造任何供应商调用。
- facts-only 基线提示词按 INV-12 分拆至独立 PR(p19b)并独立审计;本分支不携带。
- 每次运行排他唯一 run 目录,报告/回执写一次不覆盖;失败例保留完整脱敏回执并入分母;
  输入/提示词/schema/代码/模型配置哈希入 run-manifest。
- 冻结基线回溯(旧基线模型)定义 & 门槛数值:待独立评审与本人确认,当前全部为草案。
