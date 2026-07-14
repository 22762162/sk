"""预测记录与命中率验证(DESIGN §10 精神:让命理能被检验,而非自说自话)。

把每次会诊给出的吉凶预测记下来、留时间窗,到期回访核对命中/未中/部分,自动算命中率——
这是「数据越多越准」落到实处的唯一方式:用生活结果检验解读,而不是靠感觉。

存储:consult-engine/predictions/predictions.jsonl(**gitignored、本机私有**;含命盘信息)。
纯标准库、无网络、无密钥。命中率含部分命中按 0.5 计;样本少时仅供参考,非统计结论。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE_DIR = ROOT / "consult-engine" / "predictions"
STORE = STORE_DIR / "predictions.jsonl"
OUTCOMES = {"hit", "miss", "partial"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _write_all(records: list[dict]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    STORE.write_text(body + ("\n" if records else ""), encoding="utf-8")


def save(chart_line: str, chart_hash: str, domain: str, statement: str,
         window_start: str, window_end: str) -> dict:
    """登记一条预测(状态 pending)。statement/时间窗由上游给具体,便于日后可核对。"""
    if not statement.strip():
        raise ValueError("预测内容不能为空")
    recs = _load()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rid = f"pred-{stamp}-" + hashlib.sha256((statement + _now_iso()).encode()).hexdigest()[:6]
    rec = {
        "id": rid, "created_at": _now_iso(),
        "chart_line": chart_line, "chart_hash": chart_hash,
        "domain": domain, "statement": statement,
        "window_start": window_start, "window_end": window_end,
        "status": "pending", "reviewed_at": None, "note": "",
    }
    recs.append(rec)
    _write_all(recs)
    return rec


def review(rid: str, status: str, note: str = "") -> dict | None:
    """回访:标记命中/未中/部分。找不到返回 None。"""
    if status not in OUTCOMES:
        raise ValueError(f"结果只能是 {OUTCOMES}")
    recs = _load()
    found = None
    for r in recs:
        if r["id"] == rid:
            r["status"], r["note"], r["reviewed_at"] = status, note, _now_iso()
            found = r
    if found:
        _write_all(recs)
    return found


def listing(status: str | None = None) -> list[dict]:
    recs = _load()
    if status:
        recs = [r for r in recs if r["status"] == status]
    return sorted(recs, key=lambda r: r["created_at"], reverse=True)


def due(today: str | None = None) -> list[dict]:
    """到期待回访:时间窗末已过、仍 pending 的预测。"""
    today = today or date.today().isoformat()
    return [r for r in _load()
            if r["status"] == "pending" and r.get("window_end") and r["window_end"] <= today]


def stats() -> dict:
    """命中率统计。部分命中按 0.5 计;按领域分解。"""
    recs = _load()
    reviewed = [r for r in recs if r["status"] in OUTCOMES]
    hit = sum(1 for r in reviewed if r["status"] == "hit")
    partial = sum(1 for r in reviewed if r["status"] == "partial")
    miss = sum(1 for r in reviewed if r["status"] == "miss")
    n = len(reviewed)
    by_domain: dict[str, dict] = {}
    for r in reviewed:
        d = by_domain.setdefault(r["domain"], {"n": 0, "hit": 0, "partial": 0})
        d["n"] += 1
        if r["status"] == "hit":
            d["hit"] += 1
        elif r["status"] == "partial":
            d["partial"] += 1
    for v in by_domain.values():
        v["hit_rate"] = round((v["hit"] + 0.5 * v["partial"]) / v["n"], 3) if v["n"] else None
    return {
        "total": len(recs), "pending": len(recs) - n, "reviewed": n,
        "hit": hit, "partial": partial, "miss": miss,
        "hit_rate": round((hit + 0.5 * partial) / n, 3) if n else None,
        "by_domain": by_domain,
        "honesty": "命中率含部分命中按 0.5 计;样本少时仅供参考,非统计结论。数据越多越可信。",
    }
