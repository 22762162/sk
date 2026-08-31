# Claude 侧协作状态（huohuo_bridge）

## 接单回执（2026-08-31）

- **接单**：确认承接 RFC-0003 只读出口服务，范围仅 `integrations/huohuo_bridge/`（服务、测试、README）。
- **原工作区**：`~/Projects/sk-claude-wt`，分支 `feat/p16-brain-connector`（我此前的 HTTP 版连接器 + spec + 测试）。
  该实现已被 RFC-0003 取代：**保留在本地、未推送、未合并、未部署**（线上 main 无我方 P2 改动），可供你 diff 参考后废弃。
- **既往真实数据接触披露（皆在你的暂停请求送达之前）**：读过大脑 openapi 与开放 API 文档；经 HTTP 拉过样例营收
  （daily/monthly 各一次+连接器自测两次）；为排查 401 比对过 .env 与容器内 KNOWLEDGE_API_KEY 的**哈希**并用容器值
  发过一次 `GET /knowledge?limit=1`（200）。**密钥任何时刻未打印明文、未持久化、未入仓**。此后遵守：不再读
  token/.env/真实 DB，仅合成数据开发。
- **PR #45**（六爻/梅花）：维持草稿与盲隔离，未动。
- **并行任务披露**：我此前经 `codex exec` 派了一个独立 Codex 实例在 `~/Projects/sk-paipan-reference` 做
  盲写对拍参考实现（后台运行中，禁读主仓 consult-engine）。如与你的规划冲突请告知。
- **治理提醒**：最终 PR 需含我方文件的 implementer attestation——本文件末节备有草稿文本，汇总 PR 时可直接取用。

## 实现进度

- [x] 读毕 CLAUDE.md / 任务书 / RFC-0003
- [x] service + source + config + serve 入口
- [x] 合成测试全绿(18/18)

## 完工报告（2026-08-31）

### 文件清单（全部新增，仅 integrations/huohuo_bridge/ 及本文档）

```
integrations/__init__.py                       # 命名空间占位
integrations/huohuo_bridge/__init__.py
integrations/huohuo_bridge/config.py           # from_env:token≥32/scopes JSON/DSN,任一缺失→None(关闭)
integrations/huohuo_bridge/source.py           # Source 协议+SqlAlchemySource(只读事务;PG SET TRANSACTION READ ONLY/SQLite PRAGMA query_only;白名单两表白名单列;时间列归一化 naive→上层按 UTC)
integrations/huohuo_bridge/service.py          # create_app(config,source):/v1/health /v1/scopes /v1/context;Bearer+compare_digest;no-store;错误不回显 DSN/SQL
integrations/huohuo_bridge/serve.py            # python -m …serve;仅 127.0.0.1:8793
integrations/huohuo_bridge/README.md
integrations/huohuo_bridge/tests/__init__.py
integrations/huohuo_bridge/tests/test_bridge.py
```

### 测试命令与结果

```
uv run --with pytest --with fastapi --with httpx --with sqlalchemy --with uvicorn \
  python3 -m pytest integrations/huohuo_bridge/tests -q
→ 18 passed
```

覆盖:未配置全端点 503;错/缺 token 401;短 token 配置拒载;未知 scope 403;period 五种非法 400;
知识七类过滤(L5/未知级/跨项目/未确认/自循环来源/私有层)仅正常行出库;21 行截断标记;
流水多币种 Decimal 精确合计+最早同步时间;最新行胜出;缺组/同刻冲突/NaN/空币种/无时间五路"整月不出数";
越权组/日表/他月/非 group 隔离;空 group_ids 完整且空;DB 异常 503 且响应不含 DSN/SQL;
源级只读(INSERT 被拒、读不受影响);所有 items 同 scope_id。

### source 只读性自查

- SQL 仅两条 SELECT 常量语句(白名单列),无任何 INSERT/UPDATE/DELETE/DDL 路径;
- 连接层双保险:PG `SET TRANSACTION READ ONLY` / SQLite `PRAGMA query_only=ON`(有测试证明写被拒);
- **未初始化/未连接任何真实数据库**——全程注入合成 SQLite 与假 source;serve.py 从未运行。

### 未解决风险（提交前请评审）

1. **PG 只读事务语句未经真库验证**(本侧禁触真库):`SET TRANSACTION READ ONLY` 在 SQLAlchemy
   autobegin 下的时序建议由你在预发验证;更优解是 DSN 直接用 SELECT-only 账号(RFC 首选)。
2. 知识排序依赖 `created_at DESC, id DESC`;若真库 created_at 有 NULL,NULL 排序行为 PG/SQLite 不同,
   建议真库验证或在 SQL 加 `NULLS LAST`。
3. `synced_at` 相同但金额也完全相同的重复行,当前按"同刻冲突→该组缺失"处理(从严);若真库存在
   合法重复快照,需要你定夺是否放宽为"同刻同额视为同一行"。我未擅自放宽。
4. 每组仅"最新一行为准"假设 revenue_snapshots 为快照语义(同组同月多行=修订);若实为增量语义,
   合计规则需改,请以真库口径确认。
5. RFC 中 `known_at="该币种纳入记录最早同步时间"`已实现;但多组同币种时"最早"取的是入合计各行的
   最小 synced_at,如需改为"最新"请说明。

## R1+R2 修复记录（2026-08-31 第二批）

- R1-1 SQL 层等级/来源/空值过滤先于 LIMIT(trim 版),服务层兜底保留;新增"前 21 条全被排除仍取旧合法条目且不误报截断"用例
- R1-2/R2-1 配置严格化:token ASCII 可打印 32–256 + bytes compare_digest;scope id/period/currency 一律 fullmatch+显式 ASCII 类;
  group_ids 必须原生 list/tuple[str](字符串不再被迭代洗白);注入 BridgeConfig 同样全量校验,类型错误按关闭不抛异常
- R1-3 流水改"先聚组、后取最新":旧时刻重复行不再误伤唯一最新快照;服务层复核 period_type/period_key/entity_type;naive/aware 统一 UTC 比较
- R1-4/R2-2 全响应(含 404/405/未捕获异常)no-store;处理边界整体 try/except 固定文案;_conn 只读设置失败即 close;
  DSN 方言白名单(仅 postgresql/psycopg/sqlite),坏 DSN 由 serve.build 捕获转关闭态不打印;PG connect_timeout=5+SET LOCAL statement_timeout=5s;流水查询 1001 上限,超限整月拒绝
- R2-3 金额范围校验:原始串≤64、|amt|≤1E18、小数位≤6、极端指数在 abs() 前用 adjusted() 拦截(修了 decimal.Overflow 逃逸),超出按缺失不舍入
- R2-4 知识 id 须合 App 标识规则(全串≤160)、来源 1–80 字,不合规整行排除
- R2-5 README 写明 postgresql+psycopg 驱动须显式安装,缺驱动以关闭态运行

**测试:31/31 通过**(同一命令)。真库(PostgreSQL)运行仍未验证——合成通过不等于已上线,发布前的真库清单见 App 审核文末。

## 冻结声明与集成 BLOCKER（2026-08-31 收尾）

- **integrations/ 已冻结**:最后一改为 README DSN 示例统一为 `postgresql+psycopg://`(按你的收尾请求);
  此后不再改动,补丁整合由你执行。31/31 测试在冻结点通过。
- **BLOCKER-1(需本人拍板,合成阶段无法解决)**:真库 kinet 同步的 currency 实际存的是「音浪」(非 ASCII),
  会被出口币种白名单(`[A-Z0-9_]{3,16}`)判为坏值 → 上线后**所有流水都会按缺失处理,整月不出合计**。
  两个解法二选一,均不属我或你可自行放宽的边界:①大脑侧把 currency 规范为 ASCII 代码(如 KS_COIN),
  由其同步任务改写;②本人批准在出口加一张显式币种映射表(音浪→KS_COIN)并保留原值于 unit 注记。
- **BLOCKER-2(部署项,非代码)**:真库 SELECT-only 账号、psycopg 驱动、statement_timeout 真库行为,
  三项均未在真实 PostgreSQL 上验证;发布清单须含一次真库演练。
- 两份 attestation 已按规范放置:`governance/attestations/decision-desk-p2-claude-{implementer,reviewer}.yaml`
  (artifact_id 描述性命名;均已注明**人工签署仍待定**,不含"本人签署由合并承载"类措辞)。

## App 侧交叉审核

已完成,见 `docs/coordination/claude-app-review.md`:**通过,无阻断**;独立复跑其测试 21 passed(+8 subtests);5 条低危建议+2 条部署备注。

### 给汇总 PR 的 implementer attestation 草稿（可直接取用）

artifact_id: PR-<N>-implementer-claude-bridge / provider: anthropic / model_id: claude-fable-5 /
agent_role: implementer(仅 integrations/huohuo_bridge/) / notes: 分两阶段——旧 HTTP 连接器阶段
(feat/p16,曾按当时授权做过真实数据探查,已废弃未合并)与本出口阶段(纯合成数据,未触真实 DB/密钥);
31 项合成测试通过;真库运行未验证;R1/R2 审查意见已全部落实。发布须经本人审阅与批准——
开发代理不代签,合并动作仅在本人执行或明示授权时方视为人签。
