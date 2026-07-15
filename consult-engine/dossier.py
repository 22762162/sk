"""个人档案(按出生时刻聚合;本机私有,gitignored)——越用越准的关键。

聚合三类数据:① 盘前验证(铁口直断过去)的本人打分;② 预测回访命中率;③ 历次会诊数。
生成「档案摘要」注入后续会诊/追问做校准:已被本人确认「准」的推断是可依赖的锚点,
被否定「不准」的推断提示同类错误要避开。纯标准库、无网络、无密钥。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "consult-engine" / "dossier"
SCORES = {"hit", "miss", "unsure"}


def _path(birth: str) -> Path:
    return DIR / (hashlib.sha256(birth.strip().encode()).hexdigest()[:16] + ".json")


def _load(birth: str) -> dict:
    p = _path(birth)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"birth": birth.strip(), "backcasts": []}


def save_backcast(birth: str, events: list[dict]) -> float | None:
    """存一次盘前验证(events 各含 score: hit|miss|unsure)。返回本次命中率(unsure 不计)。"""
    d = _load(birth)
    clean = []
    for e in events:
        if not isinstance(e, dict):
            continue
        clean.append({k: e.get(k) for k in ("year", "ganzhi", "domain", "claim", "confidence", "score")})
    scored = [e for e in clean if e.get("score") in ("hit", "miss")]
    hit = sum(1 for e in scored if e["score"] == "hit")
    rate = round(hit / len(scored), 3) if scored else None
    d["backcasts"].append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "events": clean, "hit_rate": rate,
    })
    DIR.mkdir(parents=True, exist_ok=True)
    _path(birth).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return rate


def stats(birth: str) -> dict:
    """此人档案统计:验证次数、总打分、命中率。"""
    d = _load(birth)
    scored = [e for b in d["backcasts"] for e in b["events"] if e.get("score") in ("hit", "miss")]
    hit = sum(1 for e in scored if e["score"] == "hit")
    return {"backcast_rounds": len(d["backcasts"]), "scored": len(scored), "hit": hit,
            "hit_rate": round(hit / len(scored), 3) if scored else None}


def summary(birth: str) -> str:
    """档案摘要(注入会诊/追问做校准);无档案返回空串。"""
    d = _load(birth)
    if not d["backcasts"]:
        return ""
    all_ev = [e for b in d["backcasts"] for e in b["events"]]
    hits = [e for e in all_ev if e.get("score") == "hit"]
    misses = [e for e in all_ev if e.get("score") == "miss"]
    parts = []
    n = len(hits) + len(misses)
    if n:
        parts.append(f"过去验证:本人已对 {n} 条过去推断打分,命中 {len(hits)} 条")
    if hits:
        parts.append("已确认「准」的推断(可作依赖锚点):"
                     + "；".join(f"{e.get('year')}年[{e.get('domain')}]{str(e.get('claim'))[:42]}" for e in hits[:6]))
    if misses:
        parts.append("已被否定「不准」的推断(避免再犯同类错误):"
                     + "；".join(f"{e.get('year')}年[{e.get('domain')}]{str(e.get('claim'))[:32]}" for e in misses[:4]))
    return "。".join(parts)
