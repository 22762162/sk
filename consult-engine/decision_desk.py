"""Local decision-desk records. No network, model calls, or production data at import."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScopeError(ValueError):
    pass


def migrate(con) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, industry TEXT NOT NULL DEFAULT '',
            context TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS company_projects (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            name TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS company_memberships (
            id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
            project_id TEXT NOT NULL DEFAULT '', profile_id TEXT NOT NULL REFERENCES profiles(id),
            role TEXT NOT NULL, consent_confirmed INTEGER NOT NULL DEFAULT 0,
            starts_on TEXT NOT NULL DEFAULT '', ends_on TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(company_id, project_id, profile_id)
        );
        CREATE TABLE IF NOT EXISTS profile_events (
            id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id),
            occurred_on TEXT NOT NULL, content TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'owner_confirmed', known_at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS immutable_profile_event_update BEFORE UPDATE ON profile_events
            BEGIN SELECT RAISE(ABORT, 'profile events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_profile_event_delete BEFORE DELETE ON profile_events
            BEGIN SELECT RAISE(ABORT, 'profile events are append-only'); END;
    """)
    columns = {row["name"] for row in con.execute("PRAGMA table_info(inquiries)")}
    for name, definition in (
        ("scene", "TEXT NOT NULL DEFAULT 'personal'"),
        ("company_id", "TEXT NOT NULL DEFAULT ''"),
        ("project_id", "TEXT NOT NULL DEFAULT ''"),
        ("scope_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in columns:
            con.execute(f"ALTER TABLE inquiries ADD COLUMN {name} {definition}")
    con.execute("CREATE INDEX IF NOT EXISTS inquiry_company ON inquiries(company_id, project_id)")


class DeskStore:
    def __init__(self, app_store):
        self.store = app_store

    def list_companies(self) -> list[dict]:
        with self.store._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM companies ORDER BY updated_at DESC, id")]

    def list_projects(self, company_id: str = "") -> list[dict]:
        with self.store._connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM company_projects" + (" WHERE company_id=?" if company_id else "")
                + " ORDER BY updated_at DESC, id", (company_id,) if company_id else (),
            )]

    def list_memberships(self, company_id: str = "") -> list[dict]:
        with self.store._connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT m.*,p.name AS profile_name,p.version AS profile_version FROM company_memberships m "
                "JOIN profiles p ON p.id=m.profile_id"
                + (" WHERE m.company_id=?" if company_id else "") + " ORDER BY m.created_at,m.id",
                (company_id,) if company_id else (),
            )]

    def save_company(self, values: dict, company_id: str = "", expected_version: int = 0) -> dict:
        stamp = now()
        with self.store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if company_id:
                row = con.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
                if not row or int(row["version"]) != expected_version:
                    raise ScopeError("公司不存在或已更新，请刷新后重试")
                con.execute("UPDATE companies SET name=?,industry=?,context=?,version=version+1,updated_at=? WHERE id=?",
                            (values["name"], values["industry"], values["context"], stamp, company_id))
            else:
                company_id = "company-" + uuid.uuid4().hex[:12]
                con.execute("INSERT INTO companies(id,name,industry,context,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (company_id, values["name"], values["industry"], values["context"], stamp, stamp))
            result = dict(con.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone())
            con.execute("COMMIT")
            return result

    def save_project(self, company_id: str, values: dict, project_id: str = "", expected_version: int = 0) -> dict:
        stamp = now()
        with self.store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM companies WHERE id=?", (company_id,)).fetchone():
                raise ScopeError("公司不存在")
            if project_id:
                row = con.execute("SELECT * FROM company_projects WHERE id=? AND company_id=?", (project_id, company_id)).fetchone()
                if not row or int(row["version"]) != expected_version:
                    raise ScopeError("项目不存在、归属不符或已更新")
                con.execute("UPDATE company_projects SET name=?,context=?,version=version+1,updated_at=? WHERE id=?",
                            (values["name"], values["context"], stamp, project_id))
            else:
                project_id = "project-" + uuid.uuid4().hex[:12]
                con.execute("INSERT INTO company_projects(id,company_id,name,context,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (project_id, company_id, values["name"], values["context"], stamp, stamp))
            result = dict(con.execute("SELECT * FROM company_projects WHERE id=?", (project_id,)).fetchone())
            con.execute("COMMIT")
            return result

    def save_membership(self, company_id: str, values: dict, expected_version: int = 0) -> dict:
        for value in (values["starts_on"], values["ends_on"]):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ScopeError("日期必须使用 YYYY-MM-DD 格式")
        if values["starts_on"] and values["ends_on"] and values["ends_on"] < values["starts_on"]:
            raise ScopeError("结束日期不能早于开始日期")
        with self.store._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM companies WHERE id=?", (company_id,)).fetchone():
                raise ScopeError("公司不存在")
            if not con.execute("SELECT 1 FROM profiles WHERE id=?", (values["profile_id"],)).fetchone():
                raise ScopeError("个人档案不存在")
            project_id = values.get("project_id", "")
            if project_id and not con.execute("SELECT 1 FROM company_projects WHERE id=? AND company_id=?", (project_id, company_id)).fetchone():
                raise ScopeError("项目不属于当前公司")
            row = con.execute("SELECT * FROM company_memberships WHERE company_id=? AND project_id=? AND profile_id=?",
                              (company_id, project_id, values["profile_id"])).fetchone()
            if row and int(row["version"]) != expected_version:
                raise ScopeError("人员关联已存在或已更新，请刷新后编辑")
            stamp, mid = now(), row["id"] if row else "member-" + uuid.uuid4().hex[:12]
            args = (values["role"], int(values["consent_confirmed"]), values["starts_on"], values["ends_on"], stamp)
            if row:
                con.execute("UPDATE company_memberships SET role=?,consent_confirmed=?,starts_on=?,ends_on=?,updated_at=?,version=version+1 WHERE id=?", (*args, mid))
            else:
                con.execute("INSERT INTO company_memberships(id,company_id,project_id,profile_id,role,consent_confirmed,starts_on,ends_on,updated_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (mid, company_id, project_id, values["profile_id"], *args, stamp))
            result = dict(con.execute("SELECT * FROM company_memberships WHERE id=?", (mid,)).fetchone())
            con.execute("COMMIT")
            return result

    def list_events(self, profile_id: str) -> list[dict]:
        with self.store._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM profile_events WHERE profile_id=? ORDER BY known_at DESC,id DESC LIMIT 100", (profile_id,))]

    def append_event(self, profile_id: str, occurred_on: str, content: str) -> dict:
        if date.fromisoformat(occurred_on).isoformat() != occurred_on:
            raise ScopeError("日期必须使用 YYYY-MM-DD 格式")
        eid, stamp = "event-" + uuid.uuid4().hex[:12], now()
        with self.store._connect() as con:
            if not con.execute("SELECT 1 FROM profiles WHERE id=?", (profile_id,)).fetchone():
                raise ScopeError("个人档案不存在")
            con.execute("INSERT INTO profile_events(id,profile_id,occurred_on,content,known_at) VALUES(?,?,?,?,?)",
                        (eid, profile_id, occurred_on, content, stamp))
            return dict(con.execute("SELECT * FROM profile_events WHERE id=?", (eid,)).fetchone())

    def resolve_scope(self, profile_id: str, scene: str, company_id: str = "", project_id: str = "",
                      membership_ids: list[str] | None = None, as_of: str = "",
                      expected_profile_version: int | None = None,
                      expected_company_version: int | None = None,
                      expected_project_version: int | None = None,
                      expected_memberships: dict | None = None) -> tuple[dict, list[dict]]:
        """Take all scope records in one SQLite read transaction; never infer participants."""
        selected = membership_ids or []
        if scene not in {"personal", "company"}:
            raise ScopeError("问事场景无效")
        if len(selected) != len(set(selected)) or len(selected) > 6:
            raise ScopeError("关联人员不可重复且最多六位")
        if expected_memberships is not None and set(expected_memberships) != set(selected):
            raise ScopeError("已确认的人员范围与本次选择不一致")
        if scene == "personal" and (company_id or project_id or selected):
            raise ScopeError("个人问事不能夹带公司、项目或他人命盘")
        with self.store._connect() as con:
            con.execute("BEGIN")
            row = con.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not row:
                raise ScopeError("分析主体不存在")
            subject = dict(row)
            if expected_profile_version is not None and subject["version"] != expected_profile_version:
                raise ScopeError("主体档案已更新，请重新确认资料范围")
            profiles = [subject]
            events = [dict(r) for r in con.execute("SELECT * FROM profile_events WHERE profile_id=? ORDER BY known_at DESC,id DESC LIMIT 12", (profile_id,))]
            scope = {"version": "decision-scope-v1", "scene": scene,
                     "subject": {"id": subject["id"], "name": subject["name"], "version": subject["version"]},
                     "company": None, "project": None, "participants": [], "events": events,
                     "confirmed_at": now(), "brain_connection": "not_connected"}
            if scene == "company":
                company = con.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
                if not company:
                    raise ScopeError("请选择存在的公司")
                if expected_company_version is not None and company["version"] != expected_company_version:
                    raise ScopeError("公司资料已更新，请重新确认")
                scope["company"] = dict(company)
                if project_id:
                    project = con.execute("SELECT * FROM company_projects WHERE id=? AND company_id=?", (project_id, company_id)).fetchone()
                    if not project:
                        raise ScopeError("项目不属于当前公司")
                    scope["project"] = dict(project)
                    if expected_project_version is not None and project["version"] != expected_project_version:
                        raise ScopeError("项目资料已更新，请重新确认")
                if not selected:
                    raise ScopeError("请明确勾选本次相关人员（含主参考人）")
                profile_ids = set()
                for mid in selected:
                    member = con.execute("SELECT * FROM company_memberships WHERE id=? AND company_id=?", (mid, company_id)).fetchone()
                    if not member or member["project_id"] not in {"", project_id}:
                        raise ScopeError("关联人员不属于当前公司或项目")
                    if not member["consent_confirmed"]:
                        raise ScopeError("关联人员尚未确认资料使用授权")
                    if (member["starts_on"] and member["starts_on"] > as_of) or (member["ends_on"] and member["ends_on"] < as_of):
                        raise ScopeError("关联人员不在本次问事的有效任职日期内")
                    if member["profile_id"] in profile_ids:
                        raise ScopeError("同一人不能重复计入公司分析")
                    profile_ids.add(member["profile_id"])
                    person = dict(con.execute("SELECT * FROM profiles WHERE id=?", (member["profile_id"],)).fetchone())
                    if expected_memberships is not None:
                        expected = expected_memberships[mid]
                        if expected.get("version") != member["version"] or expected.get("profile_version") != person["version"]:
                            raise ScopeError("相关人员或授权资料已更新，请重新确认")
                    scope["participants"].append({
                        "membership_id": mid, "membership_version": member["version"],
                        "profile_id": person["id"], "profile_version": person["version"],
                        "name": person["name"], "role": member["role"],
                        "consent_confirmed": True, "starts_on": member["starts_on"], "ends_on": member["ends_on"],
                    })
                    if person["id"] != profile_id:
                        profiles.append(person)
                if profile_id not in profile_ids:
                    raise ScopeError("主参考人必须是本次勾选的已授权关联人员")
                # Personal life events are not automatically business context.
                scope["events"] = []
                aliases = {person["id"]: "主体" if index == 0 else f"关联人{index}"
                           for index, person in enumerate(profiles)}
                for participant in scope["participants"]:
                    participant["alias"] = aliases[participant["profile_id"]]
            con.execute("COMMIT")
            return scope, profiles


def scope_json(scope: dict) -> str:
    return json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
