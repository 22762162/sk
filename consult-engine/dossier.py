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


def add_fact(birth: str, year: int, text: str) -> dict:
    """记一条已知实录(某年真实发生的事 / 当年现状与变化)。事实锚点,注入后续推演校准。"""
    t = text.strip()[:200]
    if not t:
        raise ValueError("内容不能为空")
    d = _load(birth)
    d.setdefault("facts", [])
    fact = {"id": hashlib.sha256(f"{year}|{t}|{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:8],
            "year": int(year), "text": t,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    d["facts"].append(fact)
    DIR.mkdir(parents=True, exist_ok=True)
    _path(birth).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return fact


def del_fact(birth: str, fact_id: str) -> bool:
    d = _load(birth)
    before = len(d.get("facts", []))
    d["facts"] = [f for f in d.get("facts", []) if f.get("id") != fact_id]
    if len(d["facts"]) == before:
        return False
    _path(birth).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return True


def facts(birth: str) -> list[dict]:
    return sorted(_load(birth).get("facts", []), key=lambda f: (f.get("year", 0), f.get("at", "")))


def stats(birth: str) -> dict:
    """此人档案统计:验证次数、总打分、命中率。"""
    d = _load(birth)
    scored = [e for b in d["backcasts"] for e in b["events"] if e.get("score") in ("hit", "miss")]
    hit = sum(1 for e in scored if e["score"] == "hit")
    return {"backcast_rounds": len(d["backcasts"]), "scored": len(scored), "hit": hit,
            "hit_rate": round(hit / len(scored), 3) if scored else None}


def summary(birth: str) -> str:
    """档案摘要(注入会诊/追问做校准);无档案返回空串。

    已知实录排最前(事实锚点,推演不得与之矛盾);其后是盘前验证打分。
    注意:本摘要绝不喂给 backcast(盲测防作弊)。
    """
    d = _load(birth)
    fs = sorted(d.get("facts", []), key=lambda f: f.get("year", 0))
    if not d["backcasts"] and not fs:
        return ""
    parts0 = []
    if fs:
        parts0.append("已知实录(本人提供的既成事实——事实不容否认,但盘理解释必须诚实:"
                      "盘上确有依据才引盘,盘上看不出的就明说「此事此盘不显」,严禁事后强行圆盘):"
                      + "；".join(f"{f['year']}年:{f['text']}" for f in fs[-14:]))
    if not d["backcasts"]:
        return "。".join(parts0)
    all_ev = [e for b in d["backcasts"] for e in b["events"]]
    hits = [e for e in all_ev if e.get("score") == "hit"]
    misses = [e for e in all_ev if e.get("score") == "miss"]
    parts = parts0
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
