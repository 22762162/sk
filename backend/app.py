"""三鉴 V1.0 本地测试后端(L5 研究观察窗口的最小实现)。

职责边界:时区换算(IANA tzdata,INV-01 允许的历法事实来源)与节气注入数据的组装
在这里完成;一切干支计算都交给确定性引擎 paipan-cli(JSONL 协议,contracts 附录 A)。

运行:make v1-serve(先构建 release 引擎,再起 uvicorn)。
"""

from __future__ import annotations

import bisect
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "golden-tests" / "oracle-sources" / "solar_terms_de440s_1900_2100.jsonl"
CLI = Path(os.environ.get("PAIPAN_CLI", ROOT / "engine-paipan" / "target" / "release" / "paipan-cli"))
TZ = ZoneInfo("Asia/Shanghai")
JIE_NAMES = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
             "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]

app = FastAPI(title="三鉴 V1.0 排盘测试页", docs_url=None, redoc_url=None)

_jie_unix: list[int] = []
_jie_seq: list[int] = []
_lichun: dict[int, int] = {}


@app.on_event("startup")
def load_solar_terms() -> None:
    pairs = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        if row["term"] in JIE_NAMES:
            pairs.append((row["unix"], JIE_NAMES.index(row["term"])))
        if row["term"] == "立春":
            _lichun[row["civil_year"]] = row["unix"]
    pairs.sort()
    _jie_unix.extend(u for u, _ in pairs)
    _jie_seq.extend(s for _, s in pairs)


class PaipanReq(BaseModel):
    birth: str  # "YYYY-MM-DDTHH:MM" 或含秒
    zi_hour_mode: str = "split"


@app.post("/api/paipan")
def paipan(req: PaipanReq) -> JSONResponse:
    try:
        naive = datetime.fromisoformat(req.birth)
    except ValueError:
        return JSONResponse({"ok": False, "error": "日期时间格式无法解析"}, status_code=422)
    if naive.tzinfo is not None:
        return JSONResponse({"ok": False, "error": "请输入不带时区的当地(北京)时间"}, status_code=422)
    if not 1901 <= naive.year <= 2099:
        return JSONResponse(
            {"ok": False, "error": "当前历源数据覆盖 1901–2099 年"}, status_code=422
        )

    aware = naive.replace(tzinfo=TZ)  # IANA tzdata:含历史时差与 1986–91 夏令时
    t = int(aware.timestamp())
    # 时辰/日界按标准北京时间(UTC+8)判定:夏令时年份用户填的钟面时间被拨快一小时,
    # 此处经 tzdata 换算回标准时(主流排盘做法);引擎收到的 local 即标准时表示。
    std = datetime.fromtimestamp(t, timezone(timedelta(hours=8)))
    i = bisect.bisect_right(_jie_unix, t) - 1
    if i < 0 or i + 1 >= len(_jie_unix):
        return JSONResponse({"ok": False, "error": "超出节气数据覆盖范围"}, status_code=422)

    def engine_input(tt: int, op: str, extra: dict | None = None) -> dict | None:
        """按时刻 tt 组装引擎注入(标准北京时间上下文);超出数据覆盖返回 None。"""
        loc = datetime.fromtimestamp(tt, timezone(timedelta(hours=8)))
        j = bisect.bisect_right(_jie_unix, tt) - 1
        if j < 0 or j + 1 >= len(_jie_unix) or loc.year not in _lichun:
            return None
        inp = {
            "t_unix": tt,
            "lichun_unix": _lichun[loc.year],
            "local": {"y": loc.year, "m": loc.month, "d": loc.day,
                      "hh": loc.hour, "mm": loc.minute, "ss": loc.second},
            "month_ctx": {"jie_seq": _jie_seq[j], "jie_unix": _jie_unix[j],
                          "next_jie_unix": _jie_unix[j + 1]},
            "zi_hour_mode": req.zi_hour_mode,
        }
        if extra:
            inp.update(extra)
        return {"case_id": f"web-{op}-{tt}", "op": op, "input": inp}

    def run_engine(cases: list[dict]) -> list[dict] | None:
        payload = "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n"
        proc = subprocess.run(
            [str(CLI)], input=payload,
            capture_output=True, text=True, timeout=10, check=False,
        )
        if proc.returncode != 0:
            return None
        return [json.loads(line) for line in proc.stdout.strip().splitlines()]

    # 时间输入到分 → 精度 60 秒(spec 4.5 调用方候选盘协议)
    precision = 60
    case = engine_input(t, "four_pillars_uncertainty",
                        {"input_time_precision_seconds": precision})
    results = run_engine([case]) if case else None
    if results is None:
        return JSONResponse({"ok": False, "error": "引擎进程异常"}, status_code=500)
    result = results[0]
    if not result.get("ok"):
        return JSONResponse({"ok": False, "error": result.get("error", "引擎拒绝该输入")},
                            status_code=422)

    out = result["output"]
    candidates = []
    if out.get("result_status") == "ambiguous":
        side_cases = [c for c in
                      (engine_input(t - precision, "four_pillars"),
                       engine_input(t + precision, "four_pillars")) if c]
        side = run_engine(side_cases) or []
        seen = []
        for r in side:
            if r.get("ok") and r["output"] not in seen:
                seen.append(r["output"])
        candidates = seen
    dst = bool(aware.dst())
    return JSONResponse({
        "ok": True,
        "claim_type": "computed_fact",  # contracts/claim.schema.json 分层验收
        "output": out,
        "result_status": out.get("result_status", "exact"),
        "uncertainty_sources": out.get("uncertainty_sources", []),
        "candidate_charts": candidates,
        "meta": {
            "timezone": "Asia/Shanghai(IANA tzdata)",
            "dst_applied": dst,
            "zi_hour_mode": req.zi_hour_mode,
            "jie_window": {"seq": _jie_seq[i], "name": JIE_NAMES[_jie_seq[i]]},
            "sources": "节气:JPL DE440s 自算(经 HKO 核对);日柱锚点:KASI+中研院双源",
        },
    })


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")
