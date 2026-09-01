"""独立安全探针(Claude 审查方;PR#54;纯合成 token,零真实数据/密钥/网络)。
不改作者实现;仅从攻击者视角验证 device_auth 的授权边界。"""
from __future__ import annotations
import os, sys, time, importlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import device_auth as da  # noqa: E402

SYN = "s" * 64  # 合成 device token(64 ASCII)

class Req:
    """最小 Request 替身:headers/cookies/state。"""
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        class _S: ...
        self.state = _S()

def auth(): return da.DeviceAuth(SYN, enabled=True)

def test_disabled_is_open_but_marks_state_false():
    a = da.DeviceAuth(enabled=False)
    ok, refresh = a.authorize(Req())
    assert ok is True and refresh is False
    r = Req(); a.authorize(r)  # state 未注入即视为未认证
    assert da.request_is_device_authenticated(r) is False

def test_enabled_requires_valid_token_or_session():
    a = auth()
    assert a.authorize(Req())[0] is False                     # 空请求拒
    assert a.authorize(Req(headers={da.TOKEN_HEADER: "wrong"*13}))[0] is False
    ok, refresh = a.authorize(Req(headers={da.TOKEN_HEADER: SYN}))
    assert ok is True and refresh is True

def test_session_from_other_secret_rejected():
    good = auth()
    other = da.DeviceAuth("z" * 64, enabled=True)
    forged = other._session_for(int(time.time()))            # 用别的密钥签
    assert good.authorize(Req(cookies={da.COOKIE_NAME: forged}))[0] is False

def test_session_tamper_and_expiry():
    a = auth(); now = int(time.time())
    valid = a._session_for(now)
    assert a._valid_session(valid) is True
    ts, sig = valid.split(".", 1)
    replacement = "0" if sig[-1] != "0" else "1"
    assert a._valid_session(f"{ts}.{sig[:-1]}{replacement}") is False  # 确保实际篡改签名
    assert a._valid_session(f"{int(now)+1}.{sig}") is False   # 篡改时间戳
    assert a._valid_session(a._session_for(now - da.COOKIE_SECONDS - 10)) is False  # 过期
    assert a._valid_session(a._session_for(now + 3600)) is False  # 未来签发

def test_rotation_invalidates_old_sessions():
    old = auth(); sess = old._session_for(int(time.time()))
    rotated = da.DeviceAuth("n" * 64, enabled=True)           # 轮换 token(重启后)
    assert rotated._valid_session(sess) is False

def test_config_fail_closed():
    with pytest.raises(da.DeviceAuthConfigError):
        da.DeviceAuth("short", enabled=True)                 # token 太短
    with pytest.raises(da.DeviceAuthConfigError):
        da.DeviceAuth("\x01" * 64, enabled=True)             # 非可打印

def test_env_missing_token_file_fails_closed(monkeypatch):
    monkeypatch.setenv("SANJIAN_REQUIRE_DEVICE_AUTH", "1")
    monkeypatch.delenv("SANJIAN_DEVICE_TOKEN_FILE", raising=False)
    with pytest.raises(da.DeviceAuthConfigError):
        da.DeviceAuth.from_environment()

def test_env_broad_permissions_rejected(tmp_path, monkeypatch):
    f = tmp_path / "tok.txt"; f.write_text(SYN, encoding="utf-8")
    f.chmod(0o644)                                            # group/other 可读
    monkeypatch.setenv("SANJIAN_REQUIRE_DEVICE_AUTH", "1")
    monkeypatch.setenv("SANJIAN_DEVICE_TOKEN_FILE", str(f))
    with pytest.raises(da.DeviceAuthConfigError):
        da.DeviceAuth.from_environment()
    f.chmod(0o600)                                            # 收紧后可载
    assert da.DeviceAuth.from_environment().enabled is True

def test_disabled_env_ignores_token_file(monkeypatch):
    monkeypatch.setenv("SANJIAN_REQUIRE_DEVICE_AUTH", "0")
    a = da.DeviceAuth.from_environment()
    assert a.enabled is False and a._token == ""             # 关闭态不持密钥

def test_int_parse_quirks_do_not_bypass():
    a = auth(); now = int(time.time())
    _, sig = a._session_for(now).split(".", 1)
    for weird in (f"{now}_0.{sig}", f"+{now}.{sig}", f" {now}.{sig}"):
        assert a._valid_session(weird) is False              # 规范化比较兜底

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
