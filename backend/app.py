"""三鉴 V1.0 本地测试后端(L5 研究观察窗口的最小实现)。

职责边界:时区换算(IANA tzdata,INV-01 允许的历法事实来源)与节气注入数据的组装
在这里完成;一切干支计算都交给确定性引擎 paipan-cli(JSONL 协议,contracts 附录 A)。

运行:make v1-serve(先构建 release 引擎,再起 uvicorn)。
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "golden-tests" / "oracle-sources" / "solar_terms_de440s_1900_2100.jsonl"
CLI = Path(os.environ.get("PAIPAN_CLI", ROOT / "engine-paipan" / "target" / "release" / "paipan-cli"))
REDLINE_WORDS_FILE = ROOT / "infra" / "compliance" / "redline-words.txt"
QUICKREAD_PROMPT_FILE = ROOT / "prompts" / "base" / "quickread.md"

sys.path.insert(0, str(ROOT / "consult-engine"))
import gateway  # noqa: E402  (L3 网关;密钥仅在其进程内使用)
import consult  # noqa: E402  (L4 会诊编排)
import predictions  # noqa: E402  (预测记录与命中率验证)
import luck  # noqa: E402  (流年/大运推算)
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
            # 起运推算所需:出生时刻与所处节气边界(标准北京时)
            "birth_unix": t, "birth_year": std.year,
            "jie_unix": _jie_unix[i], "next_jie_unix": _jie_unix[i + 1],
            "sources": "节气:JPL DE440s 自算(经 HKO 核对);日柱锚点:KASI+中研院双源",
        },
    })


def _redline_filter(text: str) -> tuple[str, bool]:
    """对模型动态输出做红线词遮蔽(INV-04;静态文案由 make redline 把关)。"""
    hit = False
    if REDLINE_WORDS_FILE.exists():
        for line in REDLINE_WORDS_FILE.read_text(encoding="utf-8").splitlines():
            w = line.strip()
            if w and not w.startswith("#") and w in text:
                text = text.replace(w, "◌" * len(w))
                hit = True
    return text, hit


def _quickread_system_prompt() -> str:
    raw = QUICKREAD_PROMPT_FILE.read_text(encoding="utf-8")
    return raw.split("## system", 1)[1].strip()


@app.post("/api/quickread")
def quickread(req: PaipanReq) -> JSONResponse:
    """单模型速览(DESIGN §11 P2):L1 计算事实 + 单模型概览,分层标注,fail_closed。"""
    chart_resp = paipan(req)
    if chart_resp.status_code != 200:
        return chart_resp
    chart = json.loads(bytes(chart_resp.body))
    o = chart["output"]
    chart_line = (f"年柱 {o['year']['ganzhi']},月柱 {o['month']['ganzhi']},"
                  f"日柱 {o['day']['ganzhi']},时柱 {o['hour']['ganzhi']}(八字年 {o['bazi_year']})")

    claims = [{
        "claim_id": "c-000",
        "claim_type": "computed_fact",
        "origin": "engine-paipan",
        "engine_version": "0.1.0",
        "calculation_hash": hashlib.sha256(
            json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "school": None,
        "claim": f"计算得四柱:{chart_line}"
                 + ("(该时刻邻近判界,存在候选盘,见排盘页提示)"
                    if chart.get("result_status") == "ambiguous" else ""),
        "evidence": [],
        "counterevidence": [],
        "support_status": "supported",
        "confidence": {"confidence_label": "high", "confidence_basis": "source_support",
                       "calibration_version": None},
        "limitations": [],
    }]

    try:
        route = {"provider": "anthropic", "model": os.environ.get(
            "SANJIAN_QUICKREAD_MODEL", "claude-sonnet-5")}
        result = gateway.call(route["provider"], route["model"],
                              system=_quickread_system_prompt(),
                              user=f"四柱:{chart_line}。请按 system 要求输出 JSON 数组。",
                              temperature=-1,  # 让模型用默认(sonnet-5 不接受显式 temperature)
                              max_tokens=3000,  # 中文长回答需足量,避免截断致 JSON 不闭合
                              output_schema_version="quickread-v1")
    except gateway.GatewayError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)

    text = result["text"].strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    # 稳健提取:截取首个 [ 到末个 ] 之间的数组(容忍模型前后附言)
    lo, hi = text.find("["), text.rfind("]")
    if lo != -1 and hi > lo:
        text = text[lo:hi + 1]
    try:
        items = json.loads(text)
        assert isinstance(items, list)
    except (ValueError, AssertionError):
        return JSONResponse({"ok": False, "error": "模型未返回合法 JSON,本次速览作废(fail_closed)"},
                            status_code=502)

    for i, it in enumerate(items[:5], 1):
        if not isinstance(it, dict) or not str(it.get("claim", "")).strip():
            continue
        body, hit = _redline_filter(str(it["claim"]))
        lims = [str(x) for x in it.get("limitations", []) if str(x).strip()]
        if "未经规则库佐证" not in "".join(lims):
            lims.append("未经规则库佐证")
        if hit:
            lims.append("命中受限词,已遮蔽")
        label = it.get("confidence_label", "low")
        claims.append({
            "claim_id": f"c-{i:03d}",
            "claim_type": "model_synthesis",
            "origin": route["model"],
            "engine_version": None, "calculation_hash": None, "school": None,
            "claim": body,
            "evidence": [], "counterevidence": [],
            "support_status": "unsupported",
            "confidence": {"confidence_label": label if label in ("low", "medium") else "low",
                           "confidence_basis": "synthesis", "calibration_version": None},
            "limitations": lims,
        })

    return JSONResponse({"ok": True, "claims": claims, "run_id": result["run_id"],
                         "model": route["model"], "token_usage": result["token_usage"]})


class ConsultReq(PaipanReq):
    arm: str = "D3J"  # S1 | P3 | D3 | D3J
    gender: str = ""  # male | female(算大运用;空则跳过大运,仅流年)
    industry: str = ""    # 行业(推演结合实际处境,拒绝大路货)
    occupation: str = ""  # 职业/岗位
    situation: str = ""   # 补充:目前状况/最想问的事(可选)


def _run_consult_payload(req: ConsultReq) -> dict:
    """执行一场会诊,返回可直接 JSON 化的载荷(含 ok 字段)。同步端点与异步任务共用。"""
    chart_resp = paipan(req)
    if chart_resp.status_code != 200:
        return {"ok": False, "error": "排盘失败,会诊未开始"}
    chart = json.loads(bytes(chart_resp.body))
    o = chart["output"]
    chart_line = (f"年柱 {o['year']['ganzhi']},月柱 {o['month']['ganzhi']},"
                  f"日柱 {o['day']['ganzhi']},时柱 {o['hour']['ganzhi']}(八字年 {o['bazi_year']})")
    # 种子取命盘哈希,保证同盘同轮换、可复现(DESIGN 可复现:可审计可回放)
    seed = int(hashlib.sha256(chart_line.encode()).hexdigest(), 16) % 3
    liunian = luck.liunian(datetime.now().year, 8)  # 未来 8 年流年,供逐年推演
    meta = chart.get("meta", {})
    branches = [o[p]["branch"] for p in ("year", "month", "day", "hour")]
    shensha = luck.shensha(o["day"]["stem"], o["day"]["branch"], o["year"]["branch"], branches)
    dayun = None
    if req.gender in ("male", "female") and meta.get("birth_unix"):
        dtn = (meta["next_jie_unix"] - meta["birth_unix"]) / 86400
        dfp = (meta["birth_unix"] - meta["jie_unix"]) / 86400
        dayun = luck.dayun(o["month"]["ganzhi"], o["year"]["stem"], req.gender,
                           dtn, dfp, meta.get("birth_year", datetime.now().year))
    # 本人背景(职业/行业/处境):贯穿辩手与白话,推演落到实际处境(拒绝大路货)
    parts = []
    if req.industry.strip():
        parts.append(f"行业:{req.industry.strip()}")
    if req.occupation.strip():
        parts.append(f"职业:{req.occupation.strip()}")
    if req.gender in ("male", "female"):
        parts.append("性别:" + ("男" if req.gender == "male" else "女"))
    if req.situation.strip():
        parts.append(f"补充:{req.situation.strip()[:300]}")
    profile = "；".join(parts)
    try:
        result = consult.run_consultation(o, chart_line, arm=req.arm, seed=seed,
                                          liunian=liunian, dayun=dayun, shensha=shensha,
                                          profile=profile)
    except consult.ConsultError as exc:
        return {"ok": False, "error": f"会诊失败(fail_closed):{exc}"}

    # 动态文案红线遮蔽(INV-04):对辩手/裁判/白话所有可见文本过滤
    def scrub(text: str) -> str:
        return _redline_filter(str(text))[0]

    for d in result["debaters"]:
        for c in d.get("claims", []):
            if "claim" in c:
                c["claim"] = scrub(c["claim"])
    if result.get("judge"):
        for it in result["judge"].get("issues", []):
            it["topic"] = scrub(it.get("topic", ""))
            it["rationale"] = scrub(it.get("rationale", ""))
        result["judge"]["summary"] = scrub(result["judge"].get("summary", ""))
    ps = result.get("plain_summary")
    if ps:
        for k in ("overview", "consensus", "divergence"):
            ps[k] = scrub(ps.get(k, ""))
        for dm in ps.get("domains", []):
            if isinstance(dm, dict):
                dm["reading"] = scrub(dm.get("reading", ""))
        for yr in ps.get("yearly", []):
            if isinstance(yr, dict):
                yr["reading"] = scrub(yr.get("reading", ""))

    return {
        "ok": True,
        "chart": {"line": chart_line, "output": o,
                  "result_status": chart.get("result_status", "exact"),
                  "dayun": dayun, "shensha": shensha},
        "consultation": result,
        "disclaimer": "本会诊为多模型互证的研究观察:计算部分为引擎确定性结果;命理解读为模型综合、"
                      "概率化措辞,准不准以事后命中率为准,不因多模型一致即为真。分歧透明保留。",
    }


@app.post("/api/consult")
def consult_endpoint(req: ConsultReq) -> JSONResponse:
    """三模型会诊(同步;供本地 / CLI。耗时 1–2 分钟,经代理易被超时,浏览器请用异步端点)。"""
    payload = _run_consult_payload(req)
    return JSONResponse(payload, status_code=200 if payload.get("ok") else 502)


# 异步会诊:点击立刻返回 job_id,前端轮询结果。避开代理 / 隧道对长请求的超时(如 cloudflared ~100s)。
_CONSULT_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


@app.post("/api/consult/start")
def consult_start(req: ConsultReq) -> JSONResponse:
    """启动一场会诊(后台线程),立刻返回 job_id;结果用 /api/consult/result 轮询。"""
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _CONSULT_JOBS[job_id] = {"status": "running", "payload": None}

    def worker() -> None:
        try:
            payload = _run_consult_payload(req)
            status = "done" if payload.get("ok") else "error"
        except Exception as exc:  # noqa: BLE001  兜底:任何异常都落到 job,不静默丢失
            payload, status = {"ok": False, "error": f"会诊异常:{exc}"}, "error"
        with _JOBS_LOCK:
            _CONSULT_JOBS[job_id] = {"status": status, "payload": payload}

    threading.Thread(target=worker, daemon=True).start()
    return JSONResponse({"ok": True, "job_id": job_id})


class ChatReq(BaseModel):
    question: str
    history: list = []       # [{role: user|assistant, text}]
    context: dict = {}       # {chart_line, profile, dayun_text, shensha_text, plain_summary}


@app.post("/api/chat/start")
def chat_start(req: ChatReq) -> JSONResponse:
    """会诊后追问/质疑(异步,1 次模型调用);结果同样用 /api/consult/result 轮询。"""
    q = req.question.strip()[:500]
    if not q:
        return JSONResponse({"ok": False, "error": "问题不能为空"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _CONSULT_JOBS[job_id] = {"status": "running", "payload": None}

    def worker() -> None:
        try:
            obj = consult.chat_followup(req.context or {}, req.history or [], q)
            for k in ("answer", "revised", "suggestion"):
                obj[k] = _redline_filter(str(obj.get(k, "")))[0]
            payload, status = {"ok": True, "chat": {k: obj.get(k, "") for k in
                                                    ("answer", "revised", "suggestion")}}, "done"
        except Exception as exc:  # noqa: BLE001
            payload, status = {"ok": False, "error": f"追问失败:{exc}"}, "error"
        with _JOBS_LOCK:
            _CONSULT_JOBS[job_id] = {"status": status, "payload": payload}

    threading.Thread(target=worker, daemon=True).start()
    return JSONResponse({"ok": True, "job_id": job_id})


@app.get("/api/consult/result")
def consult_result(job_id: str) -> JSONResponse:
    """查询会诊任务:running / done / error。此响应立即返回,不长挂,故不会被隧道超时。"""
    with _JOBS_LOCK:
        job = _CONSULT_JOBS.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "status": "unknown", "error": "任务不存在或已过期"},
                            status_code=404)
    if job["status"] == "running":
        return JSONResponse({"ok": True, "status": "running"})
    return JSONResponse({"ok": True, "status": job["status"], "result": job["payload"]})


class PredictSaveReq(BaseModel):
    chart_line: str
    chart_hash: str = ""
    domain: str
    statement: str
    window_start: str
    window_end: str


class PredictReviewReq(BaseModel):
    id: str
    status: str          # hit | miss | partial
    note: str = ""


@app.post("/api/predict/save")
def predict_save(req: PredictSaveReq) -> JSONResponse:
    """登记一条预测(预测→验证闭环第 1 步:记录)。文本过红线兜底。"""
    stmt, _ = _redline_filter(req.statement)
    try:
        rec = predictions.save(req.chart_line, req.chart_hash, req.domain, stmt,
                               req.window_start, req.window_end)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True, "record": rec, "stats": predictions.stats()})


@app.get("/api/predict/list")
def predict_list(status: str = "") -> JSONResponse:
    """列出预测 + 到期待回访 + 命中率(第 2/3 步:回访、命中率)。"""
    return JSONResponse({"ok": True,
                         "records": predictions.listing(status or None),
                         "due": predictions.due(),
                         "stats": predictions.stats()})


@app.post("/api/predict/review")
def predict_review(req: PredictReviewReq) -> JSONResponse:
    """回访核对:标命中/未中/部分。"""
    try:
        rec = predictions.review(req.id, req.status, _redline_filter(req.note)[0])
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    if not rec:
        return JSONResponse({"ok": False, "error": "未找到该预测"}, status_code=404)
    return JSONResponse({"ok": True, "record": rec, "stats": predictions.stats()})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")
