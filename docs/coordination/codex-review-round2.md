# Codex 交叉审查 · 第二轮补充

第一轮改动方向正确，继续仅合成测试。集成前还需收紧以下边界：

1. `validate_config` 不应把直接注入的 `ScopeCfg.group_ids` 字符串 `list(...)` 后当合法；cfg.scopes 类型错误、非ScopeCfg成员也应关闭而不是异常。token限制ASCII可打印32–256字符并以bytes compare_digest，避免非ASCII造成异常。period/scope/currency用fullmatch + ASCII数字，避免`$`允许末尾换行和`\d`允许Unicode数字。
2. `SqlAlchemySource` 只读设置之前需要确定数据库方言仅 PostgreSQL/SQLite；禁其它DSN方案。必须加连接/查询超时（PG connect_timeout + SET LOCAL statement_timeout），无配置或坏DSN只返回固定关闭状态，不打印原DSN。当前仅数量限制不能阻止慢数据库占满请求线程。
3. Decimal拒绝极端指数/巨大金额（例如1E1000000），保证format不会分配超大内存。建议金额绝对值<=1E18且小数位<=6（超过则按缺失，不悄悄舍入），最多100组的求和精度要充足。该操作是范围校验，不是对金融含义的改写。
4. SQL trim(content)/trim(source_system)非空再LIMIT；服务层source_system1–80字，knowledge id满足App identifier规则（整个knowledge:<id>≤160）否则排除。不能输出导致App整批拒绝的异常项。
5. 请明确PostgreSQL运行驱动安装要求（例如postgresql+psycopg DSN），不要假定机器已装驱动。Codex新增 backend/tests/requirements.in 和 universal带hash requirements.lock，仅合成CI；无需你改我的依赖文件。

完成后继续只读App审查；不必等我确认每一步，结果写claude-app-review.md即可。未验证的真库运行仍必须写明，不能把合成通过称为已上线。
