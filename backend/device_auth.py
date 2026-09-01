"""Device-bound access for the private App.

The native container sends its provisioned device token only on navigation.  A
successful request exchanges it for an HttpOnly, SameSite session cookie, so
page JavaScript never receives either the device token or the Brain access
token.  Development stays opt-in; production must explicitly enable the gate.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response


TOKEN_HEADER = "x-sanjian-device-token"
COOKIE_NAME = "sanjian_native_session"
SESSION_CONTEXT = b"sanjian-native-session-v1"
MAX_TOKEN_LENGTH = 256
COOKIE_SECONDS = 30 * 24 * 60 * 60


class DeviceAuthConfigError(RuntimeError):
    """Unsafe or incomplete production configuration."""


def _valid_token(value: str) -> bool:
    return 48 <= len(value) <= MAX_TOKEN_LENGTH and value.isascii() and value.isprintable()


def read_device_token_file(token_file: str) -> str:
    """Read an owner-only device token or fail closed without exposing its value."""
    if not token_file:
        raise DeviceAuthConfigError("SANJIAN_DEVICE_TOKEN_FILE is required")
    try:
        path = Path(token_file)
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise DeviceAuthConfigError("device token file permissions are too broad")
        token = path.read_text(encoding="utf-8").strip()
    except DeviceAuthConfigError:
        raise
    except OSError as exc:
        raise DeviceAuthConfigError("device token file is unavailable") from exc
    if not _valid_token(token):
        raise DeviceAuthConfigError("device token file contains an invalid token")
    return token


class DeviceAuth:
    def __init__(self, token: str = "", *, enabled: bool = False,
                 session_context: bytes = SESSION_CONTEXT) -> None:
        if enabled and not _valid_token(token):
            raise DeviceAuthConfigError("device auth is enabled but its token is missing or invalid")
        if enabled and not session_context:
            raise DeviceAuthConfigError("device session context is missing")
        self.enabled = enabled
        self._token = token if enabled else ""
        self._signing_key = token.encode() if enabled else b""
        self._session_context = session_context if enabled else b""

    @classmethod
    def from_environment(cls) -> "DeviceAuth":
        enabled = os.environ.get("SANJIAN_REQUIRE_DEVICE_AUTH", "") == "1"
        if not enabled:
            return cls()
        token_file = os.environ.get("SANJIAN_DEVICE_TOKEN_FILE", "")
        return cls(read_device_token_file(token_file), enabled=True)

    def _matches(self, supplied: str, expected: str) -> bool:
        return (isinstance(supplied, str) and len(supplied) <= MAX_TOKEN_LENGTH
                and hmac.compare_digest(supplied.encode(), expected.encode()))

    def _session_for(self, issued_at: int) -> str:
        return self.issue_session(issued_at)

    def issue_session(self, issued_at: int | None = None) -> str:
        """Create a signed session value without exposing the device token."""
        if not self.enabled:
            raise DeviceAuthConfigError("device auth is disabled")
        if issued_at is None:
            issued_at = int(time.time())
        timestamp = str(issued_at)
        signature = hmac.new(
            self._signing_key,
            self._session_context + b":" + timestamp.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{timestamp}.{signature}"

    def _valid_session(self, supplied: str) -> bool:
        return self.valid_session(supplied)

    def valid_session(self, supplied: str) -> bool:
        """Validate signature and server-side age for a session value."""
        if not isinstance(supplied, str) or len(supplied) > 96:
            return False
        try:
            timestamp, signature = supplied.split(".", 1)
            issued_at = int(timestamp)
        except (ValueError, TypeError):
            return False
        now = int(time.time())
        if issued_at > now + 300 or now - issued_at > COOKIE_SECONDS:
            return False
        return hmac.compare_digest(supplied.encode(), self.issue_session(issued_at).encode())

    def authorize(self, request: Request) -> tuple[bool, bool]:
        """Return (authorized, refresh_cookie)."""
        if not self.enabled:
            return True, False
        supplied = request.headers.get(TOKEN_HEADER, "")
        if self._matches(supplied, self._token):
            return True, True
        return self.valid_session(request.cookies.get(COOKIE_NAME, "")), False

    async def middleware(self, request: Request, call_next) -> Response:
        authorized, refresh_cookie = self.authorize(request)
        request.state.device_authenticated = bool(self.enabled and authorized)
        if not authorized:
            response = JSONResponse({"detail": "Device authorization required"}, status_code=401)
        else:
            response = await call_next(request)
        if refresh_cookie:
            response.set_cookie(
                key=COOKIE_NAME,
                value=self.issue_session(),
                max_age=COOKIE_SECONDS,
                httponly=True,
                secure=True,
                samesite="strict",
                path="/",
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def request_is_device_authenticated(request: Request) -> bool:
    return bool(getattr(request.state, "device_authenticated", False))
