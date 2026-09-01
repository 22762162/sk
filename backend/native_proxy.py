"""Authenticated reverse proxy for the native App's local Wi-Fi/USB fallback.

The browser-facing proxy keeps its own HttpOnly session.  After authenticating
that session it injects the provisioned device token only on the loopback hop
to the protected backend.  Browser cookies and backend Set-Cookie headers never
cross the boundary, preventing the two session layers from overwriting one
another.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from backend.device_auth import (
    COOKIE_SECONDS,
    MAX_TOKEN_LENGTH,
    TOKEN_HEADER,
    DeviceAuth,
    read_device_token_file,
)


UPSTREAM = "http://127.0.0.1:8788"
PROXY_COOKIE_NAME = "sanjian_proxy_session"
PROXY_SESSION_CONTEXT = b"sanjian-native-proxy-session-v1"
MAX_BODY_BYTES = 1_048_576
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def _security_headers(response: Response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def create_app(
    token: str | None = None,
    *,
    upstream_url: str = UPSTREAM,
    upstream_transport: Any = None,
) -> FastAPI:
    """Create the proxy; tests inject a synthetic token and ASGI transport."""
    if token is None:
        token_file = (os.environ.get("SANJIAN_DEVICE_TOKEN_FILE", "")
                      or os.environ.get("SANJIAN_TOKEN_FILE", ""))
        token = read_device_token_file(token_file)
    gate = DeviceAuth(token, enabled=True, session_context=PROXY_SESSION_CONTEXT)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = httpx.AsyncClient(
            base_url=upstream_url,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(180.0, connect=5.0),
            transport=upstream_transport,
        )
        yield
        await app.state.client.aclose()

    app = FastAPI(
        title="Sanjian native access proxy",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def private_proxy_responses(request: Request, call_next) -> Response:
        response = await call_next(request)
        _security_headers(response)
        return response

    def proxy_session_valid(request: Request) -> bool:
        return gate.valid_session(request.cookies.get(PROXY_COOKIE_NAME, ""))

    @app.get("/__native_auth", include_in_schema=False)
    async def native_auth(request: Request) -> Response:
        supplied = request.headers.get(TOKEN_HEADER, "")
        if (not isinstance(supplied, str) or len(supplied) > MAX_TOKEN_LENGTH
                or not hmac.compare_digest(supplied.encode(), token.encode())):
            raise HTTPException(status_code=401, detail="Unauthorized")
        response = RedirectResponse(url="/", status_code=302)
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        response.set_cookie(
            key=PROXY_COOKIE_NAME,
            value=gate.issue_session(),
            max_age=COOKIE_SECONDS,
            httponly=True,
            secure=forwarded_proto == "https" or request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        _security_headers(response)
        return response

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def proxy(path: str, request: Request) -> Response:
        if not proxy_session_valid(request):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    raise HTTPException(status_code=413, detail="Request too large")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request too large")

        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in HOP_BY_HOP
            and name.lower() not in {"host", "content-length", "cookie", TOKEN_HEADER}
        }
        # The only credential crossing the second hop is injected after the
        # browser's headers and cookies have been removed.
        headers[TOKEN_HEADER] = token
        query = request.url.query
        target = f"/{path}" + (f"?{query}" if query else "")
        upstream = await request.app.state.client.request(
            request.method,
            target,
            headers=headers,
            content=body,
        )
        response_headers = {
            name: value
            for name, value in upstream.headers.items()
            if name.lower() not in HOP_BY_HOP
            and name.lower() not in {"content-length", "content-encoding", "set-cookie"}
        }
        response = Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
        )
        _security_headers(response)
        return response

    return app
