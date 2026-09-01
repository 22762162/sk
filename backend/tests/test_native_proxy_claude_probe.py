"""独立两层探针(Claude 增量复审;PR#54 修复 97941de;纯合成 token,零真实数据/密钥/网络/重启)。
证明 BLOCK-1/OBS-404 解除,并验证凭据隔离/剥离/注入顺序/安全头。TestClient 跑 lifespan,
proxy.upstream 经 ASGITransport 直连合成 backend。"""
from __future__ import annotations
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.testclient import TestClient
from httpx import ASGITransport

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.device_auth import (COOKIE_NAME, SESSION_CONTEXT, TOKEN_HEADER, DeviceAuth)  # noqa: E402
from backend import native_proxy as npx  # noqa: E402

TOKEN = "synthetic-device-token-claude-probe-000000000000000000"


def backend_8788() -> FastAPI:
    """忠实复现 8788:全站门禁 + /__native_auth 302(cookie 由 middleware refresh) + 诊断路由。"""
    app = FastAPI()
    gate = DeviceAuth(TOKEN, enabled=True)  # 默认 SESSION_CONTEXT

    @app.middleware("http")
    async def protected(request, call_next):
        return await gate.middleware(request, call_next)

    @app.get("/__native_auth")
    def handshake() -> RedirectResponse:
        return RedirectResponse(url="/", status_code=302)

    @app.get("/api/app/ping")
    def ping(request: Request):
        # 回显第二跳实际收到的凭据,验证剥离/注入
        return {"ok": True,
                "device_header": request.headers.get(TOKEN_HEADER, ""),
                "saw_browser_cookie": "browser_marker" in request.cookies,
                "saw_proxy_cookie": npx.PROXY_COOKIE_NAME in request.cookies}

    @app.get("/setcookie")
    def setcookie():
        r = JSONResponse({"ok": True})
        r.set_cookie("backend_side", "x", httponly=True)
        return r
    return app


def two_layer():
    backend = backend_8788()
    proxy = npx.create_app(TOKEN, upstream_url="http://backend",
                           upstream_transport=ASGITransport(app=backend))
    return backend, proxy


# ── 1. 固定域名直连 8788 ──
def test_direct_backend_token_then_cookie():
    c = TestClient(backend_8788(), base_url="https://sanjian.sk.live")
    r = c.get("/api/app/ping", headers={TOKEN_HEADER: TOKEN})
    assert r.status_code == 200 and COOKIE_NAME in r.cookies       # 换得 native cookie
    sess = r.cookies[COOKIE_NAME]
    r2 = TestClient(backend_8788(), base_url="https://sanjian.sk.live",
                    cookies={COOKIE_NAME: sess}).get("/api/app/ping")
    # 说明:不同实例签名密钥同为 TOKEN、context 同默认 → 会话可续
    assert r2.status_code == 200


# ── 2. App→8790 /__native_auth→proxy cookie→第二跳最终 200 ──
def test_local_fallback_end_to_end_200():
    _, proxy = two_layer()
    with TestClient(proxy, base_url="http://skdemac-studio.local:8790") as c:
        assert c.get("/api/app/ping").status_code == 401           # 无会话先拒
        h = c.get("/__native_auth", headers={TOKEN_HEADER: TOKEN}, follow_redirects=False)
        assert h.status_code == 302 and npx.PROXY_COOKIE_NAME in h.cookies
        r = c.get("/api/app/ping")                                  # 带 proxy cookie
        assert r.status_code == 200, "第二跳注入服务端 token 后必须 200(BLOCK-1 解除)"
        body = r.json()
        assert body["device_header"] == TOKEN                      # 注入了服务端 token
        assert body["saw_browser_cookie"] is False                 # 浏览器 cookie 未进第二跳
        assert body["saw_proxy_cookie"] is False                   # proxy cookie 未进第二跳


# ── 3. 错误 token / 错误 proxy cookie 均 401 ──
def test_wrong_credentials_rejected():
    _, proxy = two_layer()
    with TestClient(proxy, base_url="http://p") as c:
        assert c.get("/__native_auth", headers={TOKEN_HEADER: "wrong"*12},
                     follow_redirects=False).status_code == 401
        assert c.get("/api/app/ping",
                     cookies={npx.PROXY_COOKIE_NAME: "0.deadbeef"}).status_code == 401


# ── 4. 浏览器 cookie 不进第二跳 + 8788 Set-Cookie 不回浏览器 ──
def test_browser_cookie_stripped_and_backend_setcookie_stripped():
    _, proxy = two_layer()
    with TestClient(proxy, base_url="http://p") as c:
        c.get("/__native_auth", headers={TOKEN_HEADER: TOKEN}, follow_redirects=False)
        r = c.get("/api/app/ping", cookies={"browser_marker": "leak"})
        assert r.json()["saw_browser_cookie"] is False
        r2 = c.get("/setcookie")
        assert "set-cookie" not in {k.lower() for k in r2.headers}  # backend Set-Cookie 被剥


# ── 5. 两层会话签名隔离(不同 session_context,双向不可重放) ──
def test_session_contexts_are_isolated():
    backend_gate = DeviceAuth(TOKEN, enabled=True)                          # 默认 context
    proxy_gate = DeviceAuth(TOKEN, enabled=True, session_context=npx.PROXY_SESSION_CONTEXT)
    import time
    now = int(time.time())
    assert backend_gate.valid_session(proxy_gate.issue_session(now)) is False  # proxy→backend 拒
    assert proxy_gate.valid_session(backend_gate.issue_session(now)) is False  # backend→proxy 拒
    assert SESSION_CONTEXT != npx.PROXY_SESSION_CONTEXT


# ── 6. /__native_auth 直连 backend:302 且完成 cookie 交换(OBS-404 解除) ──
def test_native_auth_direct_backend_is_302_with_cookie():
    c = TestClient(backend_8788(), base_url="https://sanjian.sk.live")
    r = c.get("/__native_auth", headers={TOKEN_HEADER: TOKEN}, follow_redirects=False)
    assert r.status_code == 302                                    # 非 404
    assert COOKIE_NAME in r.cookies                                # middleware refresh 设 native cookie
    # 跟随 302 到 / 带 cookie → 通过门禁
    r2 = TestClient(backend_8788(), base_url="https://sanjian.sk.live",
                    cookies={COOKIE_NAME: r.cookies[COOKIE_NAME]}).get("/api/app/ping")
    assert r2.status_code == 200


# ── 边界:注入顺序(浏览器发 device header 不能覆盖注入)+ 异常安全头 + token 不泄漏 ──
def test_browser_device_header_cannot_override_injection():
    _, proxy = two_layer()
    with TestClient(proxy, base_url="http://p") as c:
        c.get("/__native_auth", headers={TOKEN_HEADER: TOKEN}, follow_redirects=False)
        r = c.get("/api/app/ping", headers={TOKEN_HEADER: "attacker-supplied"})
        assert r.status_code == 200 and r.json()["device_header"] == TOKEN  # 注入覆盖浏览器值


def test_error_responses_have_security_headers_and_no_token_leak():
    _, proxy = two_layer()
    with TestClient(proxy, base_url="http://p") as c:
        r = c.get("/api/app/ping")  # 401
        assert r.status_code == 401
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("Cache-Control") == "no-store"
        assert TOKEN not in r.text


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
