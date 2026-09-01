"""Synthetic two-hop tests for the versioned native access proxy."""
from __future__ import annotations

import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport

from backend.device_auth import DeviceAuth, TOKEN_HEADER
from backend.native_proxy import PROXY_COOKIE_NAME, create_app


TEST_TOKEN = "synthetic-two-hop-device-token-not-runtime-secret-000000000"


def protected_backend() -> FastAPI:
    app = FastAPI()
    gate = DeviceAuth(TEST_TOKEN, enabled=True)

    @app.middleware("http")
    async def protected(request, call_next):
        return await gate.middleware(request, call_next)

    @app.get("/")
    def root(request: Request):
        return {
            "ok": True,
            "proxy_cookie_forwarded": PROXY_COOKIE_NAME in request.cookies,
        }

    return app


class NativeProxyTest(unittest.TestCase):
    def test_local_proxy_authenticates_then_injects_second_hop_credential(self):
        backend = protected_backend()
        proxy = create_app(
            TEST_TOKEN,
            upstream_url="http://backend",
            upstream_transport=ASGITransport(app=backend),
        )
        with TestClient(proxy, base_url="http://local-proxy") as client:
            self.assertEqual(client.get("/").status_code, 401)
            exchanged = client.get(
                "/__native_auth",
                headers={"X-Sanjian-Device-Token": TEST_TOKEN},
                follow_redirects=False,
            )
            self.assertEqual(exchanged.status_code, 302)
            cookie = exchanged.headers["set-cookie"]
            self.assertIn(f"{PROXY_COOKIE_NAME}=", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=strict", cookie)

            proxied = client.get("/")
            self.assertEqual(proxied.status_code, 200)
            self.assertTrue(proxied.json()["ok"])
            self.assertFalse(proxied.json()["proxy_cookie_forwarded"])
            self.assertNotIn("sanjian_native_session=", proxied.headers.get("set-cookie", ""))

    def test_wrong_native_token_never_reaches_backend(self):
        backend = protected_backend()
        proxy = create_app(
            TEST_TOKEN,
            upstream_url="http://backend",
            upstream_transport=ASGITransport(app=backend),
        )
        with TestClient(proxy, base_url="http://local-proxy") as client:
            response = client.get(
                "/__native_auth",
                headers={TOKEN_HEADER: "x" * 48},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 401)

    def test_backend_session_cannot_be_replayed_as_proxy_session(self):
        backend = protected_backend()
        backend_session = DeviceAuth(TEST_TOKEN, enabled=True).issue_session()
        proxy = create_app(
            TEST_TOKEN,
            upstream_url="http://backend",
            upstream_transport=ASGITransport(app=backend),
        )
        with TestClient(proxy, base_url="http://local-proxy") as client:
            client.cookies.set(PROXY_COOKIE_NAME, backend_session)
            self.assertEqual(client.get("/").status_code, 401)


if __name__ == "__main__":
    unittest.main()
