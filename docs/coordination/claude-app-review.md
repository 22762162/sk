# Claude 只读交叉审核 · App 侧大脑接入（agent/decision-desk-p2 工作树现状）

审核人:Claude(Fable 5)。方式:只读;未改动任何被审文件;未接触真实数据。
独立复跑:`test_brain_context.py + test_app_api.py → 21 passed(+8 subtests)`。

## 结论:**通过,无阻断项**。5 条低危建议 + 2 条部署备注。

## 逐项核验(按你指定的关注面)

| 关注面 | 结论 | 证据 |
|---|---|---|
| 越权 | ✓ | scopes 白名单绑定+`bind` 乐观版本;`consume` 在问事 INSERT 同事务内校验 公司/项目/月份/绑定版本/scope 五要素;`versions()` 校验项目属于公司;越权 scope 403 由出口层+`validate_context` 双重把守 |
| 缓存 | ✓ | `/api/app/*` 与 `/api/consult/result` 中间件级 no-store;brain 路由 PrivateJSON 再加 Pragma;sw.js 只缓存静态壳(v9),brain 数据仅页面内存,预览到期定时清除 |
| 失效确认 | ✓ | 预览 TTL 600s(服务端 expires_at+客户端定时器);confirm 时复查 绑定版本/scope/公司/项目版本;`consume` 再查一遍且过期即拒;approval 以 场景/公司/项目/当月 为 key,错位即弃 |
| 重复提交 | ✓ | `brain_uses` 单次使用表+UNIQUE(inquiry);不可变触发器禁 UPDATE/DELETE;快照 content_hash 以 compare_digest 复核 |
| 源级隔离 | ✓ | 仅 L1/L2 知识可确认外发;流水 L4 仅预览;确认摘要须人工撰写(2–400字)且正则拦联系方式/链接/手机号/身份证/账号;`_desk_clean` 对 summary 二次清洗;外发物仅 summary/level/verification/known_at/source_hash/content_hash,无内部 ID/token/原文 |
| 真实隐私 | ✓ | BrainClient `trust_env=False`(不走系统代理)、仅 loopback URL、禁重定向、响应限 100KB/10s;错误信息全部固定文案;token 仅页面内存,输入框即时清空,不入 localStorage;FK pragma ON |

## 值得点名的好设计

`validate_context` 对出口响应做**全字段再验证**(不信任我方出口),与我方出口的"不信任大脑库"
构成三层互不信任链;CI 用 `--require-hashes` 锁依赖且**同时跑我方 bridge 测试**,把两侧交付缝合进同一闸门。

## 低危建议(不阻断)

1. `PreviewInput.period` 的 pydantic pattern 用 `$` 锚——`"2026-08\n"` 可过第一层
   (下游 `month()` fullmatch 会拦住)。建议改 `\Z` 求一致。
2. `BrainStore.previews` 是进程内存:多 worker 部署会失效。建议 README 注明"单 worker 约束"。
3. 确认后的快照沿用预览的 expires_at:预览 9 分钟后才确认则提交窗口只剩 1 分钟。行为符合从严
   设计且前端已展示有效期;建议在确认成功文案中强调"尽快提交"。已见部分提示,仅备注。
4. App 页面未设 CSP 响应头;brain token 在 JS 闭包中,若未来引入第三方脚本有暴露面。
   建议给 `/`、`/static/*` 加 `Content-Security-Policy: default-src 'self'`(现状无第三方脚本,低危)。
5. `unlock()` 以首个成功请求作为口令验证,失败路径靠 `lock()` 兜底——可接受;若想更显式,
   可加专用 `GET /api/app/brain/ping`。

## 部署备注(非代码问题)

- App 后端 BrainClient 读 `HUOHUO_EXPORT_TOKEN` 与出口服务同名环境变量:两进程需分别注入同值,
  部署文档请写明;轮换时两侧同步。
- `SANJIAN_BRAIN_ACCESS_TOKEN`(页面解锁口令)与出口 token 是两把不同的钥匙,请在交付说明中
  向本人讲清各自用途与保管方式。
- 真库(PostgreSQL)链路仍未运行过:合成通过≠已上线,发布清单里的真库验证项(只读账号、
  statement_timeout、psycopg 驱动安装)仍待执行——与我方出口 README 的驱动说明呼应。
