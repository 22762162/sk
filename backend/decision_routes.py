"""Decision-desk local CRUD; no external integrations or model calls."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import decision_desk


class CompanyInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    industry: str = Field(default="", max_length=60)
    context: str = Field(default="", max_length=800)
    expected_version: int = 0


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    context: str = Field(default="", max_length=800)
    expected_version: int = 0


class MemberInput(BaseModel):
    profile_id: str
    project_id: str = ""
    role: str = Field(min_length=1, max_length=60)
    consent_confirmed: bool = False
    starts_on: str = ""
    ends_on: str = ""
    expected_version: int = 0


class EventInput(BaseModel):
    occurred_on: str
    content: str = Field(min_length=2, max_length=300)
    confirmed: bool = False


def router(app_store) -> APIRouter:
    routes = APIRouter(prefix="/api/app")
    store = decision_desk.DeskStore(app_store)

    def failed(exc):
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)

    @routes.get("/desk")
    def desk():
        return {"ok": True, "companies": store.list_companies(), "projects": store.list_projects(),
                "memberships": store.list_memberships(),
                "brain": {"status": "not_connected", "mode": "read_only_planned",
                          "note": "大脑数据尚未接入；当前只使用你明确确认的背景。"}}

    @routes.post("/companies")
    def create_company(req: CompanyInput):
        values = {k: str(getattr(req, k)).strip() for k in ("name", "industry", "context")}
        if not values["name"]:
            return JSONResponse({"ok": False, "error": "公司名称不能为空"}, status_code=422)
        return JSONResponse({"ok": True, "company": store.save_company(values)}, status_code=201)

    @routes.put("/companies/{company_id}")
    def update_company(company_id: str, req: CompanyInput):
        values = {k: str(getattr(req, k)).strip() for k in ("name", "industry", "context")}
        if not values["name"]:
            return JSONResponse({"ok": False, "error": "公司名称不能为空"}, status_code=422)
        try:
            return {"ok": True, "company": store.save_company(values, company_id, req.expected_version)}
        except decision_desk.ScopeError as exc:
            return failed(exc)

    @routes.post("/companies/{company_id}/projects")
    def create_project(company_id: str, req: ProjectInput):
        if not req.name.strip():
            return JSONResponse({"ok": False, "error": "项目名称不能为空"}, status_code=422)
        try:
            return JSONResponse({"ok": True, "project": store.save_project(company_id, {
                "name": req.name.strip(), "context": req.context.strip(),
            })}, status_code=201)
        except decision_desk.ScopeError as exc:
            return failed(exc)

    @routes.put("/companies/{company_id}/projects/{project_id}")
    def update_project(company_id: str, project_id: str, req: ProjectInput):
        if not req.name.strip():
            return JSONResponse({"ok": False, "error": "项目名称不能为空"}, status_code=422)
        try:
            return {"ok": True, "project": store.save_project(company_id, {
                "name": req.name.strip(), "context": req.context.strip(),
            }, project_id, req.expected_version)}
        except decision_desk.ScopeError as exc:
            return failed(exc)

    @routes.post("/companies/{company_id}/memberships")
    def save_membership(company_id: str, req: MemberInput):
        try:
            for value in (req.starts_on, req.ends_on):
                if value:
                    date.fromisoformat(value)
            if req.starts_on and req.ends_on and req.ends_on < req.starts_on:
                raise ValueError("结束日期不能早于开始日期")
            if not req.role.strip():
                raise ValueError("关联角色不能为空")
            return {"ok": True, "membership": store.save_membership(company_id, {
                "profile_id": req.profile_id, "project_id": req.project_id, "role": req.role.strip(),
                "consent_confirmed": req.consent_confirmed, "starts_on": req.starts_on,
                "ends_on": req.ends_on,
            }, req.expected_version)}
        except (ValueError, decision_desk.ScopeError) as exc:
            return failed(exc)

    @routes.get("/profiles/{profile_id}/events")
    def list_events(profile_id: str):
        if not app_store.get_profile(profile_id):
            return JSONResponse({"ok": False, "error": "个人档案不存在"}, status_code=404)
        return {"ok": True, "events": store.list_events(profile_id)}

    @routes.post("/profiles/{profile_id}/events")
    def append_event(profile_id: str, req: EventInput):
        if not req.confirmed or len(req.content.strip()) < 2:
            return JSONResponse({"ok": False, "error": "请确认这是已经发生且可核对的事实"}, status_code=422)
        try:
            if date.fromisoformat(req.occurred_on) > datetime.now(ZoneInfo("Asia/Shanghai")).date():
                raise ValueError("尚未发生的事情不能记录为事实")
            return JSONResponse({"ok": True, "event": store.append_event(
                profile_id, req.occurred_on, req.content.strip(),
            )}, status_code=201)
        except (ValueError, decision_desk.ScopeError) as exc:
            return failed(exc)

    return routes
