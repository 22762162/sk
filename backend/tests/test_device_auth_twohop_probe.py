"""两层拓扑兼容性探针(Claude 增量复核;PR#54;纯合成,零真实数据/密钥/网络/重启)。
复现 iOS 本地 fallback:App→8790 auth_proxy(自有会话)→剥离 cookie/device-token→转发 8788。
证明 8788 启用 SANJIAN_REQUIRE_DEVICE_AUTH=1 后旧代理第二跳返回 401;并核对域名直连仍正常。
auth_proxy 剥离集合依据源码 /Users/sk/Projects/sk-ios/RemoteAccess/auth_proxy.py:121-125(只读复现,不 import)。"""
from __future__ import annotations
import sys, time
from pathlib import Path
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import device_auth as da  # noqa: E402

BACKEND_TOKEN = "b" * 64   # 8788 设备 token(合成)
PROXY_SECRET = "p" * 64    # 8790 auth_proxy 自有会话密钥(合成,与 8788 不同)

# auth_proxy.py:24 HOP_BY_HOP + :125 额外剥离集合(源码复现)
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailers", "transfer-encoding", "upgrade"}
_STRIP = _HOP | {"host", "content-length", "cookie", da.TOKEN_HEADER}


def backend_8788() -> FastAPI:
    """8788 语义:device_auth 全站中间件(enabled)+ 两个路由。"""
    app = FastAPI()
    auth = da.DeviceAuth(BACKEND_TOKEN, enabled=True)

    @app.middleware("http")
    async def gate(request, call_next):
        return await auth.middleware(request, call_next)

    @app.get("/api/app/ping")
    async def ping():
        return {"ok": True}

    @app.get("/")
    async def root():
        return JSONResponse({"shell": True})
    return app


def proxy_forward_headers(incoming: dict) -> dict:
    """复现 auth_proxy 转发:剥掉 cookie 与 device token,其余透传。"""
    return {k: v for k, v in incoming.items() if k.lower() not in _STRIP}


@pytest.mark.asyncio
async def test_direct_domain_with_device_token_passes():
    """固定域名直连 8788 带 device token → 非 401,且下发会话 Cookie。"""
    async with AsyncClient(transport=ASGITransport(app=backend_8788()), base_url="https://sanjian.sk.live") as c:
        r = await c.get("/", headers={da.TOKEN_HEADER: BACKEND_TOKEN})
    assert r.status_code == 200
    assert "sanjian_native_session" in r.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_direct_domain_with_session_cookie_passes():
    sess = da.DeviceAuth(BACKEND_TOKEN, enabled=True)._session_for(int(time.time()))
    async with AsyncClient(transport=ASGITransport(app=backend_8788()), base_url="https://sanjian.sk.live",
                           cookies={"sanjian_native_session": sess}) as c:
        r = await c.get("/api/app/ping")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_local_fallback_through_proxy_is_broken():
    """核心 blocker:App 经 8790 带完整凭据 → auth_proxy 剥离 → 转发 8788 → 401。"""
    app = backend_8788()
    # App 原始请求(经 8790 时会带 device token 或 8790 cookie),auth_proxy 剥离后:
    forwarded = proxy_forward_headers({
        da.TOKEN_HEADER: BACKEND_TOKEN,            # 被剥
        "cookie": "sanjian_native_session=" + PROXY_SECRET,  # 被剥
        "accept": "text/html",
    })
    assert da.TOKEN_HEADER not in forwarded and "cookie" not in {k.lower() for k in forwarded}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8788") as c:
        r = await c.get("/api/app/ping", headers=forwarded)
    assert r.status_code == 401, "第二跳凭据被剥离后,8788 全站门禁返回 401"


@pytest.mark.asyncio
async def test_native_auth_route_404_on_direct_backend():
    """第4点:/__native_auth 在 8788 不存在;带有效 device token 过门禁后得 404(非 200 cookie 交换)。"""
    async with AsyncClient(transport=ASGITransport(app=backend_8788()), base_url="https://sanjian.sk.live") as c:
        r = await c.get("/__native_auth", headers={da.TOKEN_HEADER: BACKEND_TOKEN})
    assert r.status_code == 404  # App 期望 200+Set-Cookie,实得 404 → 候选降级失败

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
