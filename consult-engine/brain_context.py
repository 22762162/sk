"""Protected, read-only Brain context. No secrets/files/network read at import."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

SCHEMA = "huohuo-readonly-v1"
TTL_SECONDS = 600
MAX_RESPONSE = 100_000
FORBIDDEN_SOURCE = re.compile(r"sanjian|三鉴|consult|fortune|decision-desk", re.I)


class BrainError(ValueError):
    """Only safe, fixed messages may leave this boundary."""


def stamp():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def month(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise BrainError("资料月份必须使用 YYYY-MM")
    return value


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise BrainError("大脑来源时间不合规") from None


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value))


def access_allowed(provided):
    expected = os.environ.get("SANJIAN_BRAIN_ACCESS_TOKEN", "")
    return (valid_token(expected) and isinstance(provided, str) and len(provided) <= 256
            and hmac.compare_digest(provided.encode(), expected.encode()))


def valid_token(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[!-~]{32,256}", value))


class BrainClient:
    def __init__(self, base_url=None, token=None, transport=None):
        self.base_url = base_url if base_url is not None else os.environ.get("SANJIAN_BRAIN_URL", "http://127.0.0.1:8793")
        self.token = token if token is not None else os.environ.get("HUOHUO_EXPORT_TOKEN", "")
        self.transport = transport

    def configured(self):
        try:
            parsed = urlsplit(self.base_url)
            return (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}
                    and parsed.port is not None and 1 <= parsed.port <= 65535 and not parsed.username and not parsed.password
                    and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                    and not re.search(r"\s", self.base_url) and valid_token(self.token))
        except (TypeError, ValueError):
            return False

    def get(self, path, params=None):
        if not self.configured():
            raise BrainError("大脑只读出口尚未安全配置")
        try:
            started = time.monotonic()
            with httpx.Client(base_url=self.base_url, timeout=5, follow_redirects=False,
                              trust_env=False, transport=self.transport) as client:
                with client.stream("GET", path, params=params,
                                   headers={"Authorization": "Bearer " + self.token}) as response:
                    if response.status_code != 200:
                        raise BrainError("大脑出口不可用或授权已变化，请重新核对连接")
                    raw = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE or time.monotonic() - started > 10:
                            raise BrainError("大脑响应超出安全大小限制")
                    data = json.loads(raw)
            if not isinstance(data, dict) or data.get("ok") is not True or data.get("schema_version") != SCHEMA:
                raise BrainError("大脑响应版本不兼容")
            return data
        except BrainError:
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            raise BrainError("大脑只读连接失败；未使用旧数据替代") from None

    def scopes(self):
        rows = self.get("/v1/scopes").get("scopes")
        if not isinstance(rows, list) or len(rows) > 100:
            raise BrainError("大脑授权范围不合规")
        result = []
        for row in rows:
            if (not isinstance(row, dict) or not identifier(row.get("id"))
                    or not isinstance(row.get("label"), str) or not 1 <= len(row["label"]) <= 80):
                raise BrainError("大脑授权范围不合规")
            result.append({"id": row["id"], "label": row["label"]})
        if len({r["id"] for r in result}) != len(result):
            raise BrainError("大脑授权范围重复")
        return result

    def context(self, scope_id, period):
        data = self.get("/v1/context", {"scope_id": scope_id, "period": month(period)})
        return validate_context(data, scope_id, period)


def validate_context(data, scope_id, period):
    if data.get("scope_id") != scope_id or data.get("period") != period:
        raise BrainError("大脑返回了不同公司范围或月份，已拒绝")
    fetched = instant(data.get("fetched_at"))
    if not -30 <= (stamp() - fetched).total_seconds() <= TTL_SECONDS:
        raise BrainError("大脑响应已过期或时间异常，请重新预览")
    coverage = data.get("coverage")
    if (not isinstance(coverage, dict) or type(coverage.get("knowledge_truncated")) is not bool
            or type(coverage.get("revenue_complete")) is not bool
            or type(coverage.get("revenue_missing_groups")) is not int
            or not 0 <= coverage["revenue_missing_groups"] <= 10000
            or coverage["revenue_complete"] != (coverage["revenue_missing_groups"] == 0)):
        raise BrainError("大脑资料覆盖状态不合规")
    items = data.get("items")
    if not isinstance(items, list) or len(items) > 40:
        raise BrainError("大脑来源列表不合规")
    clean, ids = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise BrainError("大脑来源格式不合规")
        if (not identifier(item.get("id")) or item["id"] in ids or item.get("scope_id") != scope_id
                or item.get("level") not in {"L1", "L2", "L3", "L4"}
                or item.get("kind") not in {"knowledge", "revenue"}
                or not isinstance(item.get("text"), str) or not 1 <= len(item["text"]) <= 1200
                or not isinstance(item.get("source_system"), str)
                or not 1 <= len(item["source_system"]) <= 80
                or FORBIDDEN_SOURCE.search(item["source_system"])):
            raise BrainError("来源等级、范围或来源链不合规，已拒绝整个响应")
        if instant(item.get("known_at")) > fetched + timedelta(seconds=30):
            raise BrainError("来源时间晚于本次读取时间")
        if item["kind"] == "revenue":
            if (item["level"] != "L4" or item.get("verification") != "provider_reported_not_audited"
                    or coverage["revenue_complete"] is not True):
                raise BrainError("流水等级或覆盖范围不合规")
        elif item.get("verification") != "source_marked_verified":
            raise BrainError("知识来源缺少确认标记")
        ids.add(item["id"])
        # Do not preserve arbitrary fields/URLs/account identifiers from the upstream object.
        clean.append({k: item[k] for k in ("id", "scope_id", "kind", "level", "text", "known_at", "source_system", "verification")})
    return {"scope_id": scope_id, "period": period, "fetched_at": fetched.isoformat(),
            "coverage": {k: coverage[k] for k in ("knowledge_truncated", "revenue_complete", "revenue_missing_groups")},
            "items": clean}


def migrate(con):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS brain_bindings (
            company_id TEXT NOT NULL REFERENCES companies(id), project_id TEXT NOT NULL DEFAULT '',
            scope_id TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(company_id, project_id)
        );
        CREATE TABLE IF NOT EXISTS brain_snapshots (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            project_id TEXT NOT NULL, period TEXT NOT NULL, binding_version INTEGER NOT NULL,
            company_version INTEGER NOT NULL, project_version INTEGER NOT NULL,
            scope_id TEXT NOT NULL, expires_at TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            content_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS brain_uses (
            snapshot_id TEXT PRIMARY KEY REFERENCES brain_snapshots(id),
            inquiry_id TEXT NOT NULL UNIQUE REFERENCES inquiries(id)
        );
        CREATE TRIGGER IF NOT EXISTS immutable_brain_snapshot_update BEFORE UPDATE ON brain_snapshots
            BEGIN SELECT RAISE(ABORT, 'brain snapshots are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_brain_snapshot_delete BEFORE DELETE ON brain_snapshots
            BEGIN SELECT RAISE(ABORT, 'brain snapshots are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_brain_use_update BEFORE UPDATE ON brain_uses
            BEGIN SELECT RAISE(ABORT, 'brain uses are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_brain_use_delete BEFORE DELETE ON brain_uses
            BEGIN SELECT RAISE(ABORT, 'brain uses are immutable'); END;
    """)


def versions(con, company_id, project_id):
    company = con.execute("SELECT version FROM companies WHERE id=?", (company_id,)).fetchone()
    project = con.execute("SELECT version FROM company_projects WHERE id=? AND company_id=?", (project_id, company_id)).fetchone() if project_id else None
    if not company or (project_id and not project):
        raise BrainError("公司或项目不存在，或项目不属于该公司")
    return (company["version"], project["version"] if project else 0)


class BrainStore:
    def __init__(self, store, client=None):
        self.store, self.client = store, client or BrainClient()
        self.previews = {}
        self.lock = threading.Lock()

    def binding(self, company_id, project_id=""):
        with self.store._connect() as con:
            versions(con, company_id, project_id)
            row = con.execute("SELECT * FROM brain_bindings WHERE company_id=? AND project_id=?", (company_id, project_id)).fetchone()
            return dict(row) if row else None

    def bind(self, company_id, project_id, scope_id, expected_version):
        if scope_id not in {s["id"] for s in self.client.scopes()}:
            raise BrainError("请选择出口明确授权的范围")
        with self.store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            versions(con, company_id, project_id)
            row = con.execute("SELECT version FROM brain_bindings WHERE company_id=? AND project_id=?", (company_id, project_id)).fetchone()
            version = row["version"] if row else 0
            if version != expected_version:
                raise BrainError("绑定已变化，请刷新后重新确认")
            con.execute("INSERT INTO brain_bindings VALUES(?,?,?,?,?) ON CONFLICT(company_id,project_id) "
                        "DO UPDATE SET scope_id=excluded.scope_id,version=excluded.version,updated_at=excluded.updated_at",
                        (company_id, project_id, scope_id, version + 1, stamp().isoformat()))
            con.commit()
        return self.binding(company_id, project_id)

    def preview(self, company_id, project_id, period):
        binding = self.binding(company_id, project_id)
        if not binding:
            raise BrainError("请先在公司页绑定明确授权的大脑范围")
        with self.store._connect() as con:
            co_v, pr_v = versions(con, company_id, project_id)
        packet = self.client.context(binding["scope_id"], period)
        now = stamp()
        preview = {**packet, "id": "preview-" + uuid.uuid4().hex, "company_id": company_id,
                   "project_id": project_id, "binding_version": binding["version"],
                   "company_version": co_v, "project_version": pr_v,
                   "expires_at": (now + timedelta(seconds=TTL_SECONDS)).isoformat()}
        with self.lock:
            self.previews = {k: v for k, v in self.previews.items() if instant(v["expires_at"]) > now}
            if len(self.previews) >= 20:
                self.previews.pop(next(iter(self.previews)))
            self.previews[preview["id"]] = preview
        return preview

    def confirm(self, preview_id, summaries, confirmed):
        if not confirmed or not isinstance(summaries, dict) or not 1 <= len(summaries) <= 20:
            raise BrainError("请逐条检查去标识摘要，并明确确认用于云端三方分析")
        with self.lock:
            preview = self.previews.get(preview_id)
            if not preview or instant(preview["expires_at"]) <= stamp():
                raise BrainError("预览已过期，请重新读取")
            items = {i["id"]: i for i in preview["items"]}
            selected = []
            for key, summary in summaries.items():
                item = items.get(key)
                if not item or item["level"] not in {"L1", "L2"} or item["kind"] != "knowledge":
                    raise BrainError("本期仅允许已确认的 L1/L2 知识摘要用于模型，敏感流水仅供查看")
                if not isinstance(summary, str) or not 2 <= len(summary.strip()) <= 400:
                    raise BrainError("每条去标识摘要需要 2–400 字")
                if re.search(r"[\x00-\x1f\x7f]|https?://|\S+@\S+|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)|(?:账号|帐号|微信|QQ)\s*[:：]?\s*\S+", summary):
                    raise BrainError("摘要含联系方式、链接或账号，请先删除")
                selected.append({"source_hash": digest(item), "level": item["level"],
                                 "known_at": item["known_at"], "verification": item["verification"],
                                 "summary": summary.strip()})
            with self.store._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                binding = con.execute("SELECT * FROM brain_bindings WHERE company_id=? AND project_id=?",
                                      (preview["company_id"], preview["project_id"])).fetchone()
                current_versions = versions(con, preview["company_id"], preview["project_id"])
                if (not binding or binding["version"] != preview["binding_version"]
                        or binding["scope_id"] != preview["scope_id"]
                        or current_versions != (preview["company_version"], preview["project_version"])):
                    raise BrainError("公司、项目或绑定已更新，请重新预览")
                snapshot = {k: preview[k] for k in ("company_id", "project_id", "period", "scope_id", "binding_version",
                                                   "company_version", "project_version", "fetched_at", "expires_at", "coverage")}
                snapshot.update(id="brain-" + uuid.uuid4().hex, confirmed_at=stamp().isoformat(), items=selected)
                content_hash = digest(snapshot)
                con.execute("INSERT INTO brain_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                    snapshot["id"], snapshot["company_id"], snapshot["project_id"], snapshot["period"], snapshot["binding_version"],
                    snapshot["company_version"], snapshot["project_version"], snapshot["scope_id"], snapshot["expires_at"], canonical(snapshot), content_hash))
                con.commit()
            del self.previews[preview_id]
        return {"id": snapshot["id"], "expires_at": snapshot["expires_at"], "content_hash": content_hash, "item_count": len(selected)}


def consume(con, snapshot_id, inquiry_id, scope, period):
    """Called inside the inquiry INSERT transaction; approval is single-use."""
    row = con.execute("SELECT * FROM brain_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    co, pr = scope.get("company") or {}, scope.get("project") or {}
    if (scope.get("scene") != "company" or not row or row["company_id"] != co.get("id")
            or row["project_id"] != pr.get("id", "") or row["period"] != period
            or row["company_version"] != co.get("version") or row["project_version"] != pr.get("version", 0)
            or instant(row["expires_at"]) <= stamp()):
        raise BrainError("大脑授权已过期或与本次公司、项目、月份不一致，请重新确认")
    binding = con.execute("SELECT * FROM brain_bindings WHERE company_id=? AND project_id=?", (co["id"], pr.get("id", ""))).fetchone()
    if (not binding or binding["version"] != row["binding_version"] or binding["scope_id"] != row["scope_id"]
            or versions(con, co["id"], pr.get("id", "")) != (row["company_version"], row["project_version"])):
        raise BrainError("公司、项目或授权绑定发生变化，请重新确认")
    if con.execute("SELECT 1 FROM brain_uses WHERE snapshot_id=?", (snapshot_id,)).fetchone():
        raise BrainError("该大脑确认已用于另一条问事，请重新预览")
    snapshot = json.loads(row["snapshot_json"])
    if not hmac.compare_digest(digest(snapshot), row["content_hash"]):
        raise BrainError("大脑来源快照校验失败")
    con.execute("INSERT INTO brain_uses VALUES(?,?)", (snapshot_id, inquiry_id))
    return {**snapshot, "content_hash": row["content_hash"]}
