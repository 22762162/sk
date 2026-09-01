"""Access-controlled Brain preview APIs. Never return server credentials."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import brain_context
from backend.device_auth import request_is_device_authenticated


class PrivateJSON(JSONResponse):
    def __init__(self, content, **kwargs):
        headers = {**(kwargs.pop("headers", None) or {}), "Cache-Control": "no-store", "Pragma": "no-cache"}
        super().__init__(content, headers=headers, **kwargs)


def request_authorized(request: Request, supplied: str = "") -> bool:
    return request_is_device_authenticated(request) or brain_context.access_allowed(supplied)


def require_access(request: Request, x_sanjian_brain_access: str = Header(default="")):
    if not request_authorized(request, x_sanjian_brain_access):
        raise HTTPException(401, "当前设备尚未绑定", headers={"Cache-Control": "no-store"})


class BindingInput(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(default="", max_length=100)
    scope_id: str = Field(min_length=1, max_length=160)
    expected_version: int = Field(default=0, ge=0)


class PreviewInput(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(default="", max_length=100)
    period: str = Field(min_length=7, max_length=7, pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")


class ConfirmInput(BaseModel):
    preview_id: str = Field(min_length=1, max_length=100)
    summaries: dict[str, str] = Field(max_length=20)
    external_confirmed: bool = False


def router(service):
    routes = APIRouter(prefix="/api/app/brain", dependencies=[Depends(require_access)], default_response_class=PrivateJSON)

    def safe(call):
        try:
            return {"ok": True, **call()}
        except brain_context.BrainError as exc:
            return PrivateJSON({"ok": False, "error": str(exc)}, status_code=409)
        except Exception:
            return PrivateJSON({"ok": False, "error": "大脑资料操作失败，未使用旧数据替代"}, status_code=503)

    @routes.get("/scopes")
    def scopes():
        return safe(lambda: {"scopes": service.client.scopes()})

    @routes.get("/binding")
    def binding(company_id: str, project_id: str = ""):
        return safe(lambda: {"binding": service.binding(company_id, project_id)})

    @routes.post("/binding")
    def bind(req: BindingInput):
        return safe(lambda: {"binding": service.bind(req.company_id, req.project_id, req.scope_id, req.expected_version)})

    @routes.post("/preview")
    def preview(req: PreviewInput):
        return safe(lambda: {"preview": service.preview(req.company_id, req.project_id, req.period)})

    @routes.post("/confirm")
    def confirm(req: ConfirmInput):
        return safe(lambda: {"snapshot": service.confirm(req.preview_id, req.summaries, req.external_confirmed)})

    return routes
