"""Synthetic device-session tests; no runtime credential is read."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "consult-engine"))

from backend.device_auth import (
    COOKIE_NAME,
    DeviceAuth,
    DeviceAuthConfigError,
    request_is_device_authenticated,
)
from backend import brain_routes


TEST_TOKEN = "synthetic-device-token-not-a-runtime-secret-000000000000"


def app_for(gate: DeviceAuth) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def protected(request, call_next):
        return await gate.middleware(request, call_next)

    @app.get("/")
    def root(request: Request):
        return {"ok": True, "device": request_is_device_authenticated(request)}

    return app


def brain_app_for(gate: DeviceAuth) -> FastAPI:
    class SyntheticClient:
        @staticmethod
        def scopes():
            return [{"id": "synthetic-scope", "label": "合成授权范围"}]

    class SyntheticService:
        client = SyntheticClient()

    app = FastAPI()

    @app.middleware("http")
    async def protected(request, call_next):
        return await gate.middleware(request, call_next)

    app.include_router(brain_routes.router(SyntheticService()))
    return app


class DeviceAuthTest(unittest.TestCase):
    def test_header_is_exchanged_for_httponly_strict_cookie(self):
        with TestClient(app_for(DeviceAuth(TEST_TOKEN, enabled=True)), base_url="https://testserver") as client:
            self.assertEqual(client.get("/").status_code, 401)
            exchanged = client.get("/", headers={
                "X-Sanjian-Device-Token": TEST_TOKEN,
                "X-Forwarded-Proto": "https",
            })
            self.assertEqual(exchanged.status_code, 200)
            self.assertTrue(exchanged.json()["device"])
            cookie = exchanged.headers["set-cookie"]
            self.assertIn(f"{COOKIE_NAME}=", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=strict", cookie)
            self.assertIn("Secure", cookie)
            self.assertNotIn(TEST_TOKEN, cookie)
            automatic = client.get("/")
            self.assertEqual(automatic.status_code, 200)
            self.assertTrue(automatic.json()["device"])

    def test_wrong_header_and_cookie_from_other_device_secret_are_rejected(self):
        first = DeviceAuth(TEST_TOKEN, enabled=True)
        second = DeviceAuth(TEST_TOKEN + "-rotated", enabled=True)
        with TestClient(app_for(first), base_url="https://testserver") as client:
            exchanged = client.get("/", headers={"X-Sanjian-Device-Token": TEST_TOKEN})
            old_cookie = exchanged.cookies.get(COOKIE_NAME)
        with TestClient(app_for(second), base_url="https://testserver") as client:
            client.cookies.set(COOKIE_NAME, old_cookie)
            self.assertEqual(client.get("/").status_code, 401)
            self.assertEqual(client.get("/", headers={"X-Sanjian-Device-Token": "x" * 48}).status_code, 401)

    def test_server_rejects_expired_or_future_session_even_if_cookie_is_replayed(self):
        gate = DeviceAuth(TEST_TOKEN, enabled=True)
        with patch("backend.device_auth.time.time", return_value=1_000_000):
            with TestClient(app_for(gate), base_url="https://testserver") as client:
                exchanged = client.get("/", headers={"X-Sanjian-Device-Token": TEST_TOKEN})
                cookie = exchanged.cookies.get(COOKIE_NAME)
        with patch("backend.device_auth.time.time", return_value=1_000_000 + 30 * 24 * 60 * 60 + 1):
            with TestClient(app_for(gate), base_url="https://testserver") as client:
                client.cookies.set(COOKIE_NAME, cookie)
                self.assertEqual(client.get("/").status_code, 401)
        future_cookie = gate._session_for(1_000_601)
        with patch("backend.device_auth.time.time", return_value=1_000_000):
            with TestClient(app_for(gate), base_url="https://testserver") as client:
                client.cookies.set(COOKIE_NAME, future_cookie)
                self.assertEqual(client.get("/").status_code, 401)

    def test_device_session_authorizes_brain_route_without_browser_secret(self):
        app = brain_app_for(DeviceAuth(TEST_TOKEN, enabled=True))
        with TestClient(app, base_url="https://testserver") as client:
            first = client.get("/api/app/brain/scopes", headers={
                "X-Sanjian-Device-Token": TEST_TOKEN,
            })
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["scopes"][0]["id"], "synthetic-scope")
            second = client.get("/api/app/brain/scopes")
            self.assertEqual(second.status_code, 200)
            self.assertNotIn(TEST_TOKEN, second.text)

    def test_enabled_configuration_fails_closed(self):
        with self.assertRaises(DeviceAuthConfigError):
            DeviceAuth("short", enabled=True)
        with patch.dict("os.environ", {"SANJIAN_REQUIRE_DEVICE_AUTH": "1"}, clear=True):
            with self.assertRaises(DeviceAuthConfigError):
                DeviceAuth.from_environment()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device-token"
            path.write_text(TEST_TOKEN, encoding="utf-8")
            path.chmod(0o600)
            with patch.dict("os.environ", {
                "SANJIAN_REQUIRE_DEVICE_AUTH": "1",
                "SANJIAN_DEVICE_TOKEN_FILE": str(path),
            }, clear=True):
                self.assertTrue(DeviceAuth.from_environment().enabled)

    def test_browser_bundle_contains_no_brain_access_field_or_header(self):
        root = Path(__file__).resolve().parents[2]
        html = (root / "web/app.html").read_text(encoding="utf-8")
        script = (root / "web/brain.js").read_text(encoding="utf-8")
        self.assertNotIn('id="brain-access"', html)
        self.assertNotIn("X-Sanjian-Brain-Access", script)
        self.assertIn('id="brain-reconnect"', html)

    def test_development_mode_preserves_existing_synthetic_test_access(self):
        with TestClient(app_for(DeviceAuth())) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["device"])


if __name__ == "__main__":
    unittest.main()
