# 三鉴 / 火火大脑只读出口协议 v1（P2）
状态：设备无感连接增量实现与交叉审核中；不是发布批准。只用合成数据开发，不读取真实数据库或密钥。

## 两侧职责
- Claude Code 拥有 integrations/huohuo_bridge/（出口服务、测试、说明）；不得改主 App、prompts、contracts、正式数据和现有运行服务。
- Codex 拥有 consult-engine/brain_context.py、backend/brain_routes.py 及 App 接线/UI/测试；不得代写运行态 prompts。
- 出口是独立 loopback 服务，不改火火大脑 dirty worktree。当前大脑健康检查报告 PostgreSQL，因此严禁悄悄回退本地 SQLite。
- 只读数据库连接由运行进程通过专用环境变量注入。优先使用专门的 SELECT-only 数据库账号；代码也开启只读事务。任何配置缺失都关闭，不复用不明旧 token。
- 不做安装/启动真实出口、真实查询、PR 合并或线上发布。

## HTTP（Bearer 鉴权，全部禁止缓存，无重定向）
GET /v1/health: {"ok":true,"schema_version":"huohuo-readonly-v1"}；亦需鉴权，不返回 DSN。
GET /v1/scopes: {"ok":true,"schema_version":"huohuo-readonly-v1","scopes":[{"id":"synthetic-scope","label":"合成范围"}]}
GET /v1/context?scope_id=...&period=YYYY-MM:
{
  "ok":true, "schema_version":"huohuo-readonly-v1",
  "scope_id":"synthetic-scope", "period":"2026-08", "fetched_at":"2026-08-31T10:00:00Z",
  "items":[],
  "coverage":{"knowledge_truncated":false,"revenue_complete":true,"revenue_missing_groups":0}
}
严格月格式；未知 scope=403；未配/错 token=401/503；数据库异常=503，错误不含 DSN/SQL/原文。
只有上述 GET；无写回、同步、检索 POST、模型调用。所有 items 含相同 scope_id。

## Item 白名单
知识：
{"id":"knowledge:<id>","scope_id":"synthetic-scope","kind":"knowledge","level":"L2",
"text":"合成事实原文（最多1200字）","known_at":"2026-08-30T10:00:00Z",
"source_system":"manual","verification":"source_marked_verified"}
- 只查已授权 project_id，knowledge_layer 只能 company_reference/external_reference，verified_by_owner 必须 true。
- 只接受明确 L1/L2/L3/L4；未知或 L5 一律不返回。最多20条，另取1条判断截断。
- source_system 不得含 sanjian/三鉴/consult/fortune/decision-desk（大小写无关），防止预测循环伪装事实。
- 该验证标志不是审计证明；App 必须再次确认，不能自动认定内容真实。
- 时间规范化 RFC3339；旧数据库 naive 时间按 UTC 处理（现有模型 datetime.utcnow）。
流水：
{"id":"revenue:2026-08:CNY","scope_id":"synthetic-scope","kind":"revenue","level":"L4",
"text":"2026-08已同步公司流水：123.45 CNY（非个人收入、非审计报表）",
"known_at":"2026-08-30T10:00:00Z","source_system":"brain.revenue_snapshots",
"verification":"provider_reported_not_audited",
"metrics":{"amount":"123.45","currency":"CNY","period":"2026-08"}}
- 只查 period_type=monthly、period_key=请求月份、entity_type=group、entity_id 在授权 group_ids 中的行。
- 不包含主播、人名、raw_payload、账号；不由流水推个人收入。
- 同一 entity_id 有多行时按 synced_at 最新确定一行；最新时刻同组冲突/无有效时间/无效金额或货币时不要猜，视为该组缺失。
- 覆盖不全时 revenue_complete=false，报缺失组数量，不输出部分总和。空 group_ids 时完整且无流水项目。
- 分币种用 Decimal 求和，拒绝非有限数；不合计月表与日表。known_at 用该币种纳入记录最早同步时间。
- L4 只作本地预览；App 本期不允许直接外发原文或流水金额。允许用户另写去敏背景走现有显式输入。

## 出口环境与可测试工厂
HUOHUO_EXPORT_TOKEN：至少32字符；只在进程内校验，不打印。
HUOHUO_EXPORT_DATABASE_URL：只读 DSN；无默认或真实数据回退。
HUOHUO_EXPORT_SCOPES_JSON：{"synthetic-scope":{"label":"合成范围","project_id":"p-test","group_ids":["g-test"]}}
建议实现 create_app(config, source) 可注入合成 source，以及 SQLAlchemy 只读 source（SQLite 仅供显式配置或测试）。
专门脚本入口绑定 127.0.0.1:8793；严禁 0.0.0.0。
数据库结构只用：
knowledge_items(id,content,knowledge_layer,confidentiality_level,project_id,verified_by_owner,source_system,created_at)
revenue_snapshots(id,period_type,period_key,entity_type,entity_id,revenue_amount,currency,synced_at)
不得导入大脑实际 app/main.py 或 session.py（其 import 会连接/初始化正式数据库）。

## App 侧冻结与外发
- 只允许公司场景；绑定 scope_id 与具体公司/项目，不能自动按相似公司名匹配。
- 服务 URL 只允许固定 loopback IP、禁止代理/重定向/用户输入 URL；token 永不返回客户端。
- 新增访问口令保护大脑预览/快照接口，避免把经营数据加到旧未鉴权接口。
- 本地预览保留来源/敏感级别/时间/缺失状态；下载不等于向模型外发授权。
- 本期只有 L1/L2 可逐条确认用于模型。L3/L4 不可勾选外发；未知/L5 拒绝整个不合规响应。
- 预览后明确确认，冻结摘要和散列；提交问事时必须绑定同公司/项目/月和该确认快照。版本/范围变更使确认失效。
- 模型只接收确认的去标识内容与来源级别，不发送 token、内部 ID、DSN；最终预测保留来源快照。
- 离线/过期/缺失不自动降级使用旧经营数据，不用无资料当作零营收。

### App 实现补充（v4）
- `SANJIAN_BRAIN_URL` 仅允许 http + 127.0.0.1/::1 + 显式端口；默认 8793。
- App 访问凭据为独立的 `SANJIAN_BRAIN_ACCESS_TOKEN`（至少32字符），由运行进程注入。
  兼容的受控运维请求仍可显式携带该口令；正式 App 浏览器不再接收、保存或显示它。
- 生产入口强制 `SANJIAN_REQUIRE_DEVICE_AUTH=1`，从 `SANJIAN_DEVICE_TOKEN_FILE` 读取已配对设备令牌。
  原生容器只在导航请求发送 `X-Sanjian-Device-Token`；后端换取30天 HttpOnly、Secure、
  SameSite=Strict会话。页面后续请求只携浏览器管理的Cookie，不可由JavaScript读取令牌或会话值。
- 固定域名可直连受保护的8788；`/__native_auth` 兼容路径在验证设备头后返回根页面。Wi-Fi/USB
  备用入口使用主仓 `backend.native_proxy:create_app --factory`：8790代理以独立Cookie验证浏览器，
  剥离浏览器Cookie和设备头后，只在loopback第二跳注入服务端持有的设备令牌，并剥离8788的
  `Set-Cookie` 响应。两进程必须读取同一个owner-only令牌文件；旧代理不可与全站设备门混用。
- `/api/app/brain/*` 与携带大脑快照的问事接受已认证设备会话；未启用设备门时仍要求
  `X-Sanjian-Brain-Access`，以保持合成测试和本机受控运维兼容。生产设备配置缺失/过短则启动失败。
- 原始预览仅服务端有界内存暂存，最多20份，10分钟有效；客户端切后台/离线/锁定清除预览与口令。
- 使用者逐条勾选L1/L2，并手动编辑2–400字必要去标识摘要，确认无姓名/联系方式/精确地址/账号/机密。
  原文不写入App数据库；保留来源散列、时间、等级、确认摘要及整体散列。自动校验不能识别所有身份信息，人工核对不可省略。
- v4新增绑定表、不可变摘要表和使用凭证表；一份确认仅可用于一条问事（失败也需重新确认）。
  绑定版本、公司/项目版本、同月匹配与一次性消费在问事写入事务内校验，失败回滚整条问事。
- 不自动更新既有AI置信度或评测结果，不声称事实接入证明术数预测准确；本期L4流水仅受保护展示。
- 真正启用仍需用户确认范围、专用只读账号/运行态凭据、PostgreSQL预发验证和人工发布签署。
- 本期 App 后端必须使用单 worker：预览保存在进程内存；多 worker/多实例会造成确认失效，不支持共享预览。
  过期预览不可再读取或确认，下一次预览会清理过期内存项；客户端有到期清除计时器。
- App 与出口进程分别注入相同的 `HUOHUO_EXPORT_TOKEN`，轮换需同步；内部大脑访问口令、设备令牌
  与模型 API Key 是三类不同凭据，不能混用。生产设备会话同时承担全站入口保护并要求HTTPS。
- 远端授权映射撤销后，应同时轮换 App 访问口令、重启 App 并重新绑定受影响公司/项目，
  使旧预览与旧版本确认失效；本期不提供跨进程实时撤权广播。
