"""只读出口服务(RFC-0003 + 交叉审查 R1)。

R1 修复:①知识过滤在 SQL 层先于 LIMIT,服务层兜底;②配置严格校验(注入亦然);
③流水按"最新时刻唯一行"判定,旧重复行不误伤;④全响应 no-store、处理异常固定文案、
流水查询超限整月拒绝、币种白名单。
"""

from __future__ import annotations

import hmac
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, Overflow

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import SCHEMA_VERSION, BridgeConfig, validate_config
from .source import KnowledgeRow, RevenueRow, Source

# R2-1:一律 fullmatch + 显式 ASCII 类,防 $ 放行末尾换行、\d 放行 Unicode 数字
_PERIOD_RE = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
_CURRENCY_RE = re.compile(r"[A-Z0-9_]{3,16}")     # 仅明确币种标识,不接受名称/账号/中文
_KID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,149}")   # knowledge:<id> 全串 ≤160,符合 App 标识规则
_ALLOWED_LEVELS = {"L1", "L2", "L3", "L4"}
_FORBIDDEN_SOURCE = ("sanjian", "三鉴", "consult", "fortune", "decision-desk")
KNOW_LIMIT = 20
MAX_REV_ROWS = 1000       # 流水查询体积上限;超限整月拒绝,绝不截断求和
_AMT_MAX = Decimal("1E18")   # R2-3:金额绝对值上限
_AMT_RAW_MAX = 64            # 原始金额串长度上限,防 Decimal 解析超大输入


def _rfc3339(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:  # 旧库 naive 按 UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _knowledge_items(rows: list[KnowledgeRow], scope_id: str, project_id: str) -> tuple[list[dict], bool]:
    """服务层兜底(SQL 已过滤):任何不合规行静默剔除,不输出残缺 item。"""
    items = []
    kept = 0
    for r in rows:
        if r.project_id != project_id or not r.verified_by_owner:
            continue
        if r.knowledge_layer not in ("company_reference", "external_reference"):
            continue
        if r.confidentiality_level not in _ALLOWED_LEVELS:
            continue
        text = (r.content or "").strip()
        src = (r.source_system or "").strip()
        known = _rfc3339(r.created_at)
        if not text or not known or not (1 <= len(src) <= 80):
            continue  # 空文本/无效时间/来源超长不出库
        if any(bad in src.lower() for bad in _FORBIDDEN_SOURCE):
            continue
        if not _KID_RE.fullmatch(str(r.id)):
            continue  # id 不合 App 标识规则:整行排除,不输出会导致整批拒绝的异常项
        kept += 1
        if kept > KNOW_LIMIT:
            return items, True
        items.append({
            "id": f"knowledge:{r.id}", "scope_id": scope_id, "kind": "knowledge",
            "level": r.confidentiality_level, "text": text[:1200],
            "known_at": known, "source_system": src,
            "verification": "source_marked_verified",
        })
    return items, False


def _parse_amount(raw: object) -> Decimal | None:
    """R2-3:范围校验(非金融改写)——绝对值≤1E18、小数位≤6、原始串≤64,超出按缺失不舍入。"""
    s = str(raw)
    if len(s) > _AMT_RAW_MAX:
        return None
    try:
        amt = Decimal(s)
        if not amt.is_finite():
            return None
        if amt.adjusted() > 18:
            return None  # 数量级 ≥1E19:先看指数,极端值连 abs() 都会 Overflow
        if abs(amt) > _AMT_MAX:
            return None
        exp = amt.as_tuple().exponent
        if isinstance(exp, int) and exp < -6:
            return None  # 小数位超 6,不悄悄舍入
        return amt
    except (InvalidOperation, Overflow, TypeError, ValueError):
        return None


def _pick_latest(rows: list[RevenueRow]) -> RevenueRow | None:
    """同组规则:任一无效时间→缺失;最新时刻多行→冲突缺失;旧重复行不影响唯一最新行。"""
    stamped = []
    for r in rows:
        if r.synced_at is None:
            return None  # 无效时间从严缺失
        stamped.append((_utc(r.synced_at), r))
    latest = max(t for t, _ in stamped)
    at_latest = [r for t, r in stamped if t == latest]
    if len(at_latest) != 1:
        return None  # 仅最新时刻的冲突才判缺失
    return at_latest[0]


def _revenue_items(rows: list[RevenueRow], scope_id: str, period: str,
                   group_ids: tuple[str, ...]) -> tuple[list[dict], bool, int]:
    if not group_ids:
        return [], True, 0
    if len(rows) > MAX_REV_ROWS:
        return [], False, len(group_ids)  # 超限整月拒绝
    by_gid: dict[str, list[RevenueRow]] = {}
    for r in rows:
        # 服务层复核,不单靠 SQL:类型/月份/组归属
        if (r.period_type != "monthly" or r.period_key != period
                or r.entity_type != "group" or r.entity_id not in group_ids):
            continue
        by_gid.setdefault(r.entity_id, []).append(r)
    chosen: dict[str, RevenueRow] = {}
    bad = 0
    for gid in group_ids:
        grp = by_gid.get(gid)
        pick = _pick_latest(grp) if grp else None
        if pick is None:
            bad += 1
            continue
        amt = _parse_amount(pick.revenue_amount)
        if amt is None:
            bad += 1
            continue
        cur = pick.currency if isinstance(pick.currency, str) else ""
        if not _CURRENCY_RE.fullmatch(cur):
            bad += 1  # 币种非白名单格式,按缺失,不猜、不输出名称型币种
            continue
        chosen[gid] = pick
    if bad:
        return [], False, bad
    by_cur: dict[str, dict] = {}
    for r in chosen.values():
        slot = by_cur.setdefault(r.currency, {"sum": Decimal(0), "earliest": _utc(r.synced_at)})
        slot["sum"] += _parse_amount(r.revenue_amount)  # 已过校验;≤100组×1E18,默认精度充足
        slot["earliest"] = min(slot["earliest"], _utc(r.synced_at))
    items = []
    for cur in sorted(by_cur):
        slot = by_cur[cur]
        amount = format(slot["sum"], "f")
        items.append({
            "id": f"revenue:{period}:{cur}", "scope_id": scope_id, "kind": "revenue",
            "level": "L4",
            "text": f"{period}已同步公司流水：{amount} {cur}（非个人收入、非审计报表）",
            "known_at": _rfc3339(slot["earliest"]),
            "source_system": "brain.revenue_snapshots",
            "verification": "provider_reported_not_audited",
            "metrics": {"amount": amount, "currency": cur, "period": period},
        })
    return items, True, 0


def create_app(config: BridgeConfig | None, source: Source | None) -> FastAPI:
    """可测试工厂;注入配置同样过严格校验,不合规视同未配置(关闭)。"""
    cfg = validate_config(config) if config is not None else None
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    @app.middleware("http")
    async def no_store(request: Request, call_next):  # 含 404/405/异常,全响应禁缓存
        try:
            resp = await call_next(request)
        except Exception:  # noqa: BLE001 固定文案,不回显异常内容
            resp = JSONResponse({"ok": False, "error": "内部错误"}, status_code=503)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _gate(request: Request) -> JSONResponse | None:
        if cfg is None or source is None:
            return JSONResponse({"ok": False, "error": "出口未配置,服务关闭"}, status_code=503)
        auth = request.headers.get("authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else ""
        # R2-1:bytes 比较,非 ASCII 输入不抛异常只判失败
        if not supplied or not hmac.compare_digest(supplied.encode("utf-8"),
                                                   cfg.token.encode("ascii")):
            return JSONResponse({"ok": False, "error": "鉴权失败"}, status_code=401)
        return None

    @app.get("/v1/health")
    def health(request: Request):
        return _gate(request) or JSONResponse({"ok": True, "schema_version": SCHEMA_VERSION})

    @app.get("/v1/scopes")
    def scopes(request: Request):
        deny = _gate(request)
        if deny is not None:
            return deny
        return JSONResponse({"ok": True, "schema_version": SCHEMA_VERSION,
                             "scopes": [{"id": sid, "label": s.label}
                                        for sid, s in sorted(cfg.scopes.items())]})

    @app.get("/v1/context")
    def context(request: Request, scope_id: str = "", period: str = ""):
        deny = _gate(request)
        if deny is not None:
            return deny
        if not _PERIOD_RE.fullmatch(period):
            return JSONResponse({"ok": False, "error": "period 须为 YYYY-MM"}, status_code=400)
        scope = cfg.scopes.get(scope_id)
        if scope is None:
            return JSONResponse({"ok": False, "error": "scope 未授权"}, status_code=403)
        try:  # 查询与全部数据处理同在边界内:任何异常固定 503,不泄 DSN/SQL/原文
            know_rows = source.knowledge(scope.project_id, KNOW_LIMIT + 1)
            rev_rows = source.revenue_monthly(period, scope.group_ids)
            k_items, truncated = _knowledge_items(know_rows, scope_id, scope.project_id)
            r_items, complete, miss_n = _revenue_items(rev_rows, scope_id, period, scope.group_ids)
            payload = {
                "ok": True, "schema_version": SCHEMA_VERSION,
                "scope_id": scope_id, "period": period,
                "fetched_at": _rfc3339(datetime.now(timezone.utc)),
                "items": k_items + r_items,
                "coverage": {"knowledge_truncated": truncated,
                             "revenue_complete": complete,
                             "revenue_missing_groups": miss_n},
            }
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "数据源不可用"}, status_code=503)
        return JSONResponse(payload)

    return app
