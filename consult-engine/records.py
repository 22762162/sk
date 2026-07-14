"""会诊记录存档(本机私有,gitignored;含命盘与个人背景)。

每场会诊完成即自动存档;追问对话也追加到对应记录。刷新/换设备(同一本机服务)不丢。
纯标准库、无网络、无密钥。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "consult-engine" / "records"

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _path(rid: str) -> Path | None:
    return (DIR / f"{rid}.json") if _SAFE.match(rid or "") else None


def save(payload: dict, birth: str, profile: str) -> str | None:
    """存一场完成的会诊(payload 为 /api/consult 的完整成功载荷)。返回记录 id。"""
    rid = (payload.get("consultation") or {}).get("consultation_id")
    p = _path(rid or "")
    if not p:
        return None
    DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "id": rid,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "birth": birth, "profile": profile,
        "payload": payload, "chats": [],
    }, ensure_ascii=False), encoding="utf-8")
    return rid


def listing() -> list[dict]:
    """记录摘要列表(新→旧):id/时间/生日/命盘一行/背景。"""
    if not DIR.exists():
        return []
    out = []
    for p in DIR.glob("*.json"):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out.append({
            "id": r.get("id"), "saved_at": r.get("saved_at", ""),
            "birth": r.get("birth", ""), "profile": r.get("profile", ""),
            "chart_line": ((r.get("payload") or {}).get("chart") or {}).get("line", ""),
            "n_chats": len(r.get("chats", [])),
        })
    return sorted(out, key=lambda x: x["saved_at"], reverse=True)


def get(rid: str) -> dict | None:
    p = _path(rid)
    if not p or not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def append_chat(rid: str, entry: dict) -> bool:
    """把一轮追问(问题+回答)追加到记录。"""
    p = _path(rid)
    if not p or not p.exists():
        return False
    r = json.loads(p.read_text(encoding="utf-8"))
    r.setdefault("chats", []).append(
        {**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    return True
