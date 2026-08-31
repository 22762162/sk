# Codex 交叉审查 · 第一轮

范围：当前 integrations/huohuo_bridge 源码，只使用合成数据。未签署发布。

请 Claude 在自己的出口工作树修复以下问题（保留已完成工作）；我继续 App 与界面验证。

1. **P1，knowledge SQL 在等级/来源过滤前 LIMIT 21**：前21条若含L5或三鉴派生，会遮蔽后面合法知识并错误报告未截断。请在 SQL 中按协议过滤后 LIMIT，服务层再兜底；空文本、空来源、无效时间也不能输出不合规 item。增加“前21条全被排除，后面仍有合法条目”用例。
2. **P1，出口配置未严格校验**：group_ids 字符串被拆成单字符、project_id=None 被 str 化、重复组、非法 scope id、任意币种字符串均接受。请验证原始类型、非空项目ID、scope id≤160（ASCII字母数字_.:-）、label1–80字、groups list≤100且唯一非空str、scopes≤100；币种仅明确标识（如 CNY/USD/DIAMOND，ASCII大写字母数字下划线3–16），坏值按缺失。不输出名称/账号作为币种。create_app直接注入配置也应拒绝短token/不合规配置。
3. **P2，_revenue_items broken 集合把过期的同刻冲突永久带入**：只需要最新时刻冲突使组缺失。先按组收集再找最大时间；较老重复不影响唯一最新值。服务层同时检查period_type/period_key/entity_type，不能仅依赖SQL过滤。混合naive/aware时间统一UTC后比较。无效时间从严缺失。
4. **P1，异常边界只包数据库查询**：后续时间/金额转换异常仍会出500并进入服务日志。配置构建/数据处理均需固定无敏感信息的错误输出；_conn设置只读失败必须close连接。所有响应（含404/405/参数错误）也应no-store。限制数据库请求/返回体积与超时，至少限制授权组100、知识21、流水查询上限并在超限时拒绝（不可截断算部分总额）。

修复完成后，请对 /Users/sk/Projects/sk-decision-desk-p2 的以下改动做只读交叉审核：consult-engine/brain_context.py、personal_app.py，backend/brain_routes.py、app.py，web/brain.js/app.js/app.html/sw.js，backend/tests/test_brain_context.py 与 test_app_api.py。不要修改这些文件；发现问题写到本工作树 docs/coordination/claude-app-review.md。关注越权/缓存/失效确认/重复提交/源级隔离与真实隐私。App v4只持久化用户逐条编辑确认的L1/L2摘要与source_hash，L3/L4不存、不外发；十分钟预览，绑定或公司项目版本变化使快照失效。

原先真实数据探查已经记录，请后续不再做。attestation必须准确区分旧连接器阶段与新出口阶段；不要把“合并动作”当作开发代理可以代签的人类批准。
