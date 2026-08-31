"""数据源(RFC-0003):只读、只碰白名单两表、只取白名单列。

严禁 import 大脑的 app/main.py 或 session.py(其 import 即初始化正式库)。
SQLAlchemy 源在每次查询开启只读事务(PostgreSQL: SET TRANSACTION READ ONLY;
SQLite 仅供显式配置/测试: PRAGMA query_only=ON)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import bindparam, create_engine, text


@dataclass(frozen=True)
class KnowledgeRow:
    id: str
    content: str
    knowledge_layer: str
    confidentiality_level: str
    project_id: str
    verified_by_owner: bool
    source_system: str
    created_at: datetime | None


@dataclass(frozen=True)
class RevenueRow:
    id: str
    period_type: str
    period_key: str
    entity_type: str
    entity_id: str
    revenue_amount: object  # 原样携带,由服务层用 Decimal 严格解析
    currency: object
    synced_at: datetime | None


class Source(Protocol):
    def knowledge(self, project_id: str, limit: int) -> list[KnowledgeRow]: ...
    def revenue_monthly(self, period_key: str, group_ids: tuple[str, ...]) -> list[RevenueRow]: ...


# R1-1:等级/来源/空值过滤全部先于 LIMIT(服务层另有兜底);NULL 时间不入
_KNOW_SQL = text(
    "SELECT id, content, knowledge_layer, confidentiality_level, project_id,"
    " verified_by_owner, source_system, created_at"
    " FROM knowledge_items"
    " WHERE project_id = :pid AND verified_by_owner = :yes"
    " AND knowledge_layer IN ('company_reference','external_reference')"
    " AND confidentiality_level IN ('L1','L2','L3','L4')"
    " AND content IS NOT NULL AND trim(content) != ''"
    " AND source_system IS NOT NULL AND trim(source_system) != ''"
    " AND created_at IS NOT NULL"
    " AND lower(source_system) NOT LIKE '%sanjian%'"
    " AND source_system NOT LIKE '%三鉴%'"
    " AND lower(source_system) NOT LIKE '%consult%'"
    " AND lower(source_system) NOT LIKE '%fortune%'"
    " AND lower(source_system) NOT LIKE '%decision-desk%'"
    " ORDER BY created_at DESC, id DESC LIMIT :lim")

_REV_SQL = text(
    "SELECT id, period_type, period_key, entity_type, entity_id,"
    " revenue_amount, currency, synced_at"
    " FROM revenue_snapshots"
    " WHERE period_type = 'monthly' AND period_key = :pk AND entity_type = 'group'"
    " AND entity_id IN :gids LIMIT :rl").bindparams(bindparam("gids", expanding=True))


def _dt(v: object) -> datetime | None:
    """时间列归一化:PG 原生 datetime;SQLite 文本按 ISO 解析;坏值一律 None(上层按缺失处理)。"""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return datetime.fromisoformat(v.strip().replace(" ", "T").replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


_ALLOWED_SCHEMES = ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://",
                    "sqlite://", "sqlite:///")
_QUERY_TIMEOUT_MS = 5000


class SqlAlchemySource:
    """显式 DSN 注入的只读源;方言白名单(仅 PostgreSQL/SQLite),连接与语句均限时。

    坏 DSN 在此抛错,由 serve.build 捕获后以关闭态运行——DSN 永不打印。
    """

    def __init__(self, database_url: str):
        if not isinstance(database_url, str) or not database_url.startswith(_ALLOWED_SCHEMES):
            raise ValueError("unsupported database scheme")  # 不含 DSN 内容
        self._is_sqlite = database_url.startswith("sqlite")
        connect_args = {} if self._is_sqlite else {"connect_timeout": 5}
        self._engine = create_engine(database_url, future=True, pool_pre_ping=True,
                                     pool_timeout=5, connect_args=connect_args)

    def _conn(self):
        conn = self._engine.connect()
        try:  # R1-4:只读设置失败必须关连接,绝不带可写连接继续
            if self._is_sqlite:
                conn.exec_driver_sql("PRAGMA query_only=ON")
            else:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                # R2-2:语句级超时,防慢库占满请求线程(事务内 SET LOCAL,连接归还即失效)
                conn.exec_driver_sql(f"SET LOCAL statement_timeout = {_QUERY_TIMEOUT_MS}")
        except Exception:
            conn.close()
            raise
        return conn

    def knowledge(self, project_id: str, limit: int) -> list[KnowledgeRow]:
        with self._conn() as conn:
            rows = conn.execute(_KNOW_SQL, {"pid": project_id, "yes": True, "lim": limit}).all()
        return [KnowledgeRow(str(r[0]), r[1] or "", r[2] or "", r[3] or "", str(r[4]),
                             bool(r[5]), r[6] or "", _dt(r[7])) for r in rows]

    def revenue_monthly(self, period_key: str, group_ids: tuple[str, ...]) -> list[RevenueRow]:
        if not group_ids:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                _REV_SQL, {"pk": period_key, "gids": list(group_ids),
                           "rl": 1001}).all()  # 服务层 MAX_REV_ROWS+1,超限整月拒绝
        return [RevenueRow(str(r[0]), r[1] or "", r[2] or "", r[3] or "", str(r[4]),
                           r[5], r[6], _dt(r[7])) for r in rows]
