# huohuo_bridge · 火火大脑只读出口（RFC-0003）

独立 loopback 服务：三鉴 App 侧（Codex 负责）经 Bearer 鉴权从这里取**范围受限、白名单化**的
公司资料快照；本服务对大脑数据库只读，无任何写路径、无模型调用、无缓存、无重定向。

## 端点

| 端点 | 说明 |
|---|---|
| `GET /v1/health` | 鉴权后返回 `{ok, schema_version}`；不含 DSN |
| `GET /v1/scopes` | 已授权范围列表（id+label） |
| `GET /v1/context?scope_id&period=YYYY-MM` | 知识条目（≤20+截断标记）+ 月度流水合计（按币种、Decimal、覆盖不全不出数） |

错误：未配置/数据库异常 503；鉴权失败 401；未知 scope 403；period 非法 400。
错误体不含 DSN/SQL/数据原文。

## 硬边界（与 RFC-0003 一致）

- 知识：仅授权 `project_id`、`verified_by_owner=true`、layer ∈ company/external_reference、
  等级仅 L1-L4（未知/L5 不出库）、来源含 sanjian/三鉴/consult/fortune/decision-desk 的一律不出库（防预测自循环）。
- 流水：仅 monthly+group+授权 `group_ids`；每组取最新 `synced_at` 一行；同刻冲突/坏值/缺行=该组缺失；
  **任何缺失即整月不出合计**（`revenue_complete=false` + 缺失组数），绝不输出部分总和；不含主播/人名/raw_payload。
- L4 流水仅供 App 本地预览，本期不得直接外发模型（App 侧闸门，Codex 负责）。

## 运行（由 Codex/本人操作，Claude 侧不启动真实服务）

```
HUOHUO_EXPORT_TOKEN=<≥32字符专用token> \
HUOHUO_EXPORT_SCOPES_JSON='{"scope-id":{"label":"…","project_id":"…","group_ids":["…"]}}' \
HUOHUO_EXPORT_DATABASE_URL=postgresql+psycopg://<SELECT-only账号>@127.0.0.1:5432/brain \
python -m integrations.huohuo_bridge.serve   # 仅 127.0.0.1:8793
```

优先用数据库层 SELECT-only 账号；代码层同时开启只读事务（PG: SET TRANSACTION READ ONLY +
SET LOCAL statement_timeout=5s / SQLite 测试: PRAGMA query_only）。任一环境缺失或 DSN 非
PostgreSQL/SQLite 方言 → 服务关闭态（503），不复用旧 token、不回退 SQLite。

**PostgreSQL 驱动须显式安装**（不假定机器已装）：推荐 `postgresql+psycopg://`（psycopg 3，
`uv run --with psycopg` 或部署环境 `pip install psycopg[binary]`）；缺驱动时服务以关闭态运行。

## 测试

```
uv run --with pytest --with fastapi --with httpx --with sqlalchemy \
  python -m pytest integrations/huohuo_bridge/tests -q
```

全部使用合成 SQLite/注入源；不接触真实数据库、密钥或大脑代码。
