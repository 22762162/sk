"""Disposable synthetic UI preview. Never opens .env, real records, or model APIs.

uv run --with fastapi --with uvicorn --with httpx python3 backend/tests/preview_decision_desk.py
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.TemporaryDirectory(prefix="sanjian-desk-preview-")
os.environ["SANJIAN_APP_DB"] = str(Path(_tmp.name) / "synthetic.sqlite3")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import app as backend_app
from fastapi.responses import JSONResponse
import uvicorn


def blocked(*args, **kwargs):
    raise RuntimeError("合成预览不调用云端模型；提交范围校验已完成")


backend_app.gateway.call = blocked
backend_app._run_consult_payload = blocked
backend_app.dossier.facts = lambda *_: []
sample = {"id": "consult-preview-synthetic", "birth": "1990-06-15T08:30",
          "saved_at": "2026-08-01T10:00:00+08:00", "chart_line": "合成旧研究候选",
          "payload": {"consultation": {"plain_summary": {
              "overview": "合成研究参考：仅用于测试绑定，非已发生事实。"}}}}
backend_app.records.listing = lambda *_, **__: [sample]
backend_app.records.get = lambda rid: sample if rid == sample["id"] else None


@backend_app.app.middleware("http")
async def isolate_preview(request, call_next):
    path = request.url.path
    if path == "/legacy" or (path.startswith("/api/") and not path.startswith("/api/app/") and path != "/api/consult/result"):
        return JSONResponse({"ok": False, "error": "合成预览不开放旧系统数据"}, status_code=403)
    return await call_next(request)


for name, birth, gender in (("合成主体甲", "1990-06-15T08:30", "male"),
                            ("合成主体乙", "1993-04-05T10:20", "female")):
    backend_app.APP_STORE.create_profile({"name": name, "birth": birth, "gender": gender,
                                         "timezone": "Asia/Shanghai", "zi_hour_mode": "split"})

if __name__ == "__main__":
    try:
        uvicorn.run(backend_app.app, host="127.0.0.1", port=8792, log_level="warning", access_log=False)
    finally:
        _tmp.cleanup()
