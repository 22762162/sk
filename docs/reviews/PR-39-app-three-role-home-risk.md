# PR #39 风险分诊：App 三方协议、首页能力与绑定交互

本报告是实现者侧风险分诊，不构成独立异厂商评审。变更涉及 `backend/`、`web/` 与
attestation，按 `governance/role-separation.yaml` 属高风险路径，合入前须本人完整审阅并补齐
异厂商 reviewer attestation。

## BLOCKER

无已知代码阻断项。合成 API 测试和手机尺寸浏览器流程已通过；完整仓库闸门见本 PR 验证记录。

## WARN

1. App 问事从 `S1` 改为 `D3J` 后，单次延迟、模型调用次数和费用会明显增加。前端等待上限从
   5 分钟延长到 8 分钟，但网络中断仍可能要求用户稍后从记录页刷新。
2. 三方完整只证明三个指定供应商/角色/流派都返回了观点，不证明观点正确。分歧保留，准确率仍
   只能来自锁定后的未来事件复盘；小样本继续抑制展示。
3. PR #39 之前的旧 App 快照没有三方拆分证据。页面明确标成旧版记录，允许继续复盘，但不能
   冒充新版“三方完整会诊”。
4. 首页“择时”和“关系/合盘”是三方问事预设，会引导用户补充具体事项、日期或关系背景；原高级
   研究页仍保留更细的确定性逐日表/双盘矩阵。两者当前不是同一份专用结果，后续若合并数据结构
   须单独设计 schema 与迁移。
5. 绑定按钮改为 10 秒内二次点击确认，解决 iOS `WKWebView` 未处理 `confirm/alert` 时无反应的
   问题；用户若停留超过 10 秒须重新点击。后端的同生日分钟校验和乐观锁仍是最终约束。
6. “本机数据备份”卡展示现有主机每日备份策略，不代表手机另存了一份数据库；主机离线或备份
   任务异常时，卡片本身不会完成健康检查。

## NOTE

- 后端严格要求角色集合 `debater_a/b/c`、供应商集合 `anthropic/openai/deepseek`、流派集合
  `ziping/wangshuai/tiaohou`，且每方至少一条可保存观点；缺一即停止生成预测。
- 不可变快照新增 `three_role_protocol`、`three_role_analysis` 与 `arbitration`，算法版本升至
  `app-forecast-compose-v1.3.0`。
- 首页增加今日、本月、择时、关系/合盘、命中率与备份六个入口；方向判断全部进入 D3J。
- App 撤销自动单模型今日解读；旧高级研究页的 `S1` 快捷按钮与前端分支已删除。
- Service Worker 壳缓存升级到 v6；私密 API 仍不进入 Cache Storage。
- 未触碰 `engine-paipan/`、`consult-engine/luck.py`、contracts、prompts、approved rulebase 或 eval
  指标。

## 验证

- `make test`：Rust 24 项、参考实现 158 项、后端 12 项全部通过。
- `make lint`、`make redline`、`make governance-check`、`make golden-smoke` 与
  `make keys-check` 全部通过；黄金集 102 例一致，三家模型密钥均已配置。
- `node --check web/app.js` 与 `git diff --check` 通过。
- 390×844 合成浏览器流程通过：首页六卡两列且无横向溢出；“三方择时”进入本月问事并预填事项、
  时间范围和现实条件提示。
- 绑定 API 的同生日校验、版本更新与跨人拒绝由合成单元测试覆盖；页面函数不再调用
  `confirm()` / `alert()`。

结论：实现者侧建议进入评审；完整自动化闸门已通过，合入仍须异厂商评审与本人签署。
