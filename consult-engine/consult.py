"""L4 会诊编排引擎(DESIGN V3.0 §2)。

三辩手绑流派独立出观点 → 匿名互相质证 → 轮换裁判盲评(允许 unresolved);
落 consultation-manifest(contracts/schemas 合规)+ judge 明细。

四实验臂(DESIGN §7.1):
  S1  = 单模型一次作答(基线)
  P3  = 三模型独立作答 + 确定性合并,无质证
  D3  = 三模型质证,无 judge
  D3J = 三模型质证 + judge 盲评(旗舰)

确定性 = 除模型调用外无随机;身份脱敏顺序由 seed 决定(可复现)。
密钥仅经 gateway 从环境读取,本引擎不接触明文。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "consult-engine"))
import gateway  # noqa: E402

PROMPTS = ROOT / "prompts"
MANIFEST_DIR = ROOT / "consult-engine" / "manifests"
PROTOCOL_VERSION = "consult-v1"

# 白话综述员(L5 呈现层):把专业观点翻成人话。这步是归纳/翻译,非思考型快模型足够且更稳、更快
#(思考型模型在这步慢且方差大,会拖长整场会诊)。可用环境变量改回其它模型。
PRESENTER = {"provider": os.environ.get("SANJIAN_PRESENTER_PROVIDER", "deepseek"),
             "model": os.environ.get("SANJIAN_PRESENTER_MODEL", "deepseek-chat")}

# 三个供应商(模型层);流派为可轮换维度(DESIGN §2.3 拉丁方)
PROVIDERS_ORDER = [
    {"role": "debater_a", "provider": "anthropic", "model": "claude-sonnet-5"},
    {"role": "debater_b", "provider": "openai", "model": "gpt-5.1"},
    {"role": "debater_c", "provider": "deepseek", "model": "deepseek-chat"},
]
SCHOOL_NAMES = {"ziping": "子平格局派", "wangshuai": "旺衰扶抑派", "tiaohou": "调候派"}

# 观察模式默认绑定(DESIGN §2.1):模型 → 固定流派
DEBATERS = [
    {**PROVIDERS_ORDER[0], "school": "ziping", "school_name": SCHOOL_NAMES["ziping"]},
    {**PROVIDERS_ORDER[1], "school": "wangshuai", "school_name": SCHOOL_NAMES["wangshuai"]},
    {**PROVIDERS_ORDER[2], "school": "tiaohou", "school_name": SCHOOL_NAMES["tiaohou"]},
]

# 研究模式 3×3 拉丁方(DESIGN §2.3):每模型演每流派各一次,解模型×流派混杂
LATIN_SQUARE = {
    "A": ["ziping", "wangshuai", "tiaohou"],   # Claude 子平 / GPT 旺衰 / DeepSeek 调候
    "B": ["wangshuai", "tiaohou", "ziping"],   # Claude 旺衰 / GPT 调候 / DeepSeek 子平
    "C": ["tiaohou", "ziping", "wangshuai"],   # Claude 调候 / GPT 子平 / DeepSeek 旺衰
}


def latin_batch_debaters(batch: str) -> list[dict]:
    """按拉丁方批次给三个模型分配流派。"""
    schools = LATIN_SQUARE[batch]
    return [{**PROVIDERS_ORDER[i], "school": schools[i], "school_name": SCHOOL_NAMES[schools[i]]}
            for i in range(3)]


def run_latin_cells(chart_line: str) -> list[dict]:
    """研究模式:跑全部 3 批 × 3 模型 = 9 个 (模型,流派) 单元(仅第一轮观点,供效应分析)。

    返回每单元 {batch, provider, model, school, school_name, claims, run_id}。
    只做第一轮独立发言(质证/裁判不参与效应归因,省成本且减噪)。
    """
    cells = []
    for batch in ("A", "B", "C"):
        debaters = latin_batch_debaters(batch)
        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(lambda d: _call_debater(d, chart_line), debaters))
        for r in results:
            cells.append({"batch": batch, "provider": r["provider"], "model": r["model"],
                          "school": r["school"], "school_name": r["school_name"],
                          "claims": r["claims"], "run_id": r["run_id"]})
    return cells


class ConsultError(RuntimeError):
    """会诊失败(fail_closed):向上如实报错,不伪造成功。"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt_system(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("## system", 1)[1].strip()


def _school_module(school: str) -> str:
    return (PROMPTS / "schools" / f"{school}.md").read_text(encoding="utf-8")


def _debater_system(template_path: Path, school: str) -> str:
    return _prompt_system(template_path).replace("{{SCHOOL_MODULE}}", _school_module(school))


def _extract_json(text: str, want_array: bool):
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").lstrip("json").strip()
    op, cl = ("[", "]") if want_array else ("{", "}")
    lo, hi = t.find(op), t.rfind(cl)
    if lo != -1 and hi > lo:
        t = t[lo:hi + 1]
    obj = json.loads(t)
    if want_array and not isinstance(obj, list):
        raise ValueError("expected array")
    if not want_array and not isinstance(obj, dict):
        raise ValueError("expected object")
    return obj


def _call_json(provider: str, model: str, system: str, user: str, *, want_array: bool,
               max_tokens: int, schema: str):
    """调用模型并解析 JSON;解析失败自动重试一次(模型偶发格式瑕疵)。返回 (obj, run_id, usage)。"""
    last_exc = None
    for _ in range(2):
        res = gateway.call(provider, model, system=system, user=user,
                           temperature=-1, max_tokens=max_tokens, output_schema_version=schema)
        try:
            return _extract_json(res["text"], want_array=want_array), res["run_id"], res["token_usage"]
        except ValueError as exc:
            last_exc = exc
    raise ConsultError(f"{provider}/{model} 未返回合法 JSON({schema})") from last_exc


def _call_debater(d: dict, chart_line: str, profile: str = "") -> dict:
    """第一轮:一位辩手独立出观点(主环节,fail_closed)。profile 为本人职业/处境背景,用于具体化。"""
    system = _debater_system(PROMPTS / "base" / "debaters" / "debater.md", d["school"])
    ctx = f"\n本人背景(结合它把观察落到此人的实际处境,不泛泛而谈):{profile}" if profile else ""
    claims, run_id, usage = _call_json(
        d["provider"], d["model"], system,
        f"四柱:{chart_line}。{ctx}\n请按 system 要求输出 JSON 数组。",
        want_array=True, max_tokens=8000, schema="debater-v1")
    return {**d, "claims": claims[:5], "run_id": run_id, "usage": usage}


def _call_cross_exam(d: dict, others_blob: str) -> dict:
    """第二轮质证(次要环节,单家解析失败优雅降级为跳过,不作废整场)。"""
    system = _debater_system(PROMPTS / "base" / "debaters" / "cross_exam.md", d["school"])
    try:
        obj, run_id, _ = _call_json(
            d["provider"], d["model"], system,
            f"另外两位辩手的观察(匿名、顺序随机):\n{others_blob}\n请按 system 输出 JSON 对象。",
            want_array=False, max_tokens=7000, schema="crossexam-v1")
    except ConsultError:
        return {"role": d["role"], "cross": {"agreements": [], "challenges": [], "revise": [],
                                             "skipped": "该辩手质证输出格式异常,本轮已跳过"},
                "run_id": None}
    return {"role": d["role"], "cross": obj, "run_id": run_id}


def _anon_blob(claims_by_role: dict, exclude_role: str, order: list[str]) -> str:
    """把除 exclude_role 外的观察脱敏拼接(隐去身份/流派名,顺序由 order 决定)。"""
    lines, tag = [], iter(["甲", "乙", "丙"])
    for role in order:
        if role == exclude_role:
            continue
        label = next(tag)
        for c in claims_by_role[role]:
            lines.append(f"[匿名{label}] {c.get('claim', '')}(理由:{c.get('basis', '')})")
    return "\n".join(lines)


def _judge(provider: str, model: str, material: str) -> dict:
    system = _prompt_system(PROMPTS / "base" / "arbiter" / "judge.md")
    obj, run_id, usage = _call_json(
        provider, model, system,
        f"会诊材料(脱敏):\n{material}\n请按 system 输出 JSON 对象。",
        want_array=False, max_tokens=8000, schema="judge-v1")
    return {"provider": provider, "model": model, "verdict": obj, "run_id": run_id, "usage": usage}


def _plain_summary(chart_line: str, assignments: list[dict], judge: dict | None,
                   liunian: list[dict] | None = None, dayun: dict | None = None,
                   shensha: list[dict] | None = None, profile: str = "") -> dict | None:
    """把会诊观点翻成白话、按生活领域归纳(L5 呈现层)。

    可直说吉凶倾向但用概率化措辞;三条底线由提示词把关(不说必然/注定、不碰投资买卖、不断生死重病),
    后端再对文本过一遍红线兜底。失败返回 None,不拖垮整场会诊(白话是加值层,专业观点始终可返回)。
    """
    system = _prompt_system(PROMPTS / "base" / "presenter" / "plain_summary.md")
    lines = [f"四柱:{chart_line}"]
    if profile:
        lines.append(f"本人背景(推演必须结合它,把每个领域落到此人的实际职业与处境):{profile}")
    lines += ["", "各模型观察:"]
    for a in assignments:
        obs = "；".join(c.get("claim", "") for c in a["claims"])
        lines.append(f"- 从「{a['school_name']}」视角:{obs}")
    if judge and judge.get("verdict", {}).get("summary"):
        lines.append("")
        lines.append(f"综合结论:{judge['verdict']['summary']}")
    if shensha:
        lines.append("")
        lines.append("本命神煞(已按标准规则算出,供解读):"
                     + "、".join(f"{s['name']}({s['note']})" for s in shensha))
    if dayun and dayun.get("periods"):
        lines.append("")
        lines.append(f"大运({dayun['direction']},{dayun['start_age']}岁起运;十年一步,请判断本人现在及未来走哪步):")
        lines.append("、".join(f"{p['ganzhi']} {p['start_year']}-{p['end_year']}({p['start_age']}-{p['end_age']}岁)"
                              for p in dayun["periods"]))
    if liunian:
        lines.append("")
        lines.append("未来流年干支(逐年分析用,请结合命局与所在大运逐年推演):"
                     + "、".join(f"{x['year']}年 {x['ganzhi']}" for x in liunian))
    user = "\n".join(lines) + "\n\n请按 system 要求输出白话综述 JSON 对象(含 domains、dayun、yearly)。"
    try:
        obj, run_id, _ = _call_json(PRESENTER["provider"], PRESENTER["model"], system, user,
                                    want_array=False, max_tokens=4000, schema="plain-summary-v1")
    except ConsultError:
        return None
    obj["_run_id"] = run_id
    return obj


def backcast(chart_line: str, dayun: dict | None, past_liunian: list[dict],
             profile: str = "") -> dict:
    """盘前验证(铁口直断过去):反推过去哪些年发生过哪类事,供本人打分(单模型 1 次调用)。"""
    system = _prompt_system(PROMPTS / "base" / "presenter" / "backcast.md")
    lines = [f"四柱:{chart_line}"]
    if profile:
        lines.append(f"本人背景:{profile}")
    if dayun and dayun.get("periods"):
        lines.append(f"大运({dayun['direction']},{dayun['start_age']}岁起运):"
                     + "、".join(f"{p['ganzhi']} {p['start_year']}-{p['end_year']}"
                                 for p in dayun["periods"]))
    lines.append("过去流年(只能从这些年份里挑):"
                 + "、".join(f"{x['year']}年 {x['ganzhi']}" for x in past_liunian))
    lines.append("\n请按 system 要求输出 JSON 对象(events)。")
    obj, run_id, _ = _call_json(PRESENTER["provider"], PRESENTER["model"], system,
                                "\n".join(lines), want_array=False, max_tokens=3000,
                                schema="backcast-v1")
    obj["_run_id"] = run_id
    return obj


def shichen_calibrate(candidates: list[dict], events_text: str, gender_cn: str = "") -> dict:
    """时辰校准:对比 12/13 个候选盘与本人已发生大事,排出最可能的前三(单模型 1 次调用)。

    candidates: [{time_range, hour_ganzhi, chart_line, note?}]
    """
    system = _prompt_system(PROMPTS / "base" / "presenter" / "shichen.md")
    lines = ["候选命盘(同一天,各时辰):"]
    for c in candidates:
        extra = f"({c['note']})" if c.get("note") else ""
        lines.append(f"- {c['time_range']} 时柱 {c['hour_ganzhi']}{extra}:{c['chart_line']}")
    if gender_cn:
        lines.append(f"性别:{gender_cn}")
    lines.append(f"\n本人自述已发生的大事:{events_text.strip()[:600]}")
    lines.append("\n请按 system 要求输出 JSON 对象(ranking 3 条 + note)。")
    obj, run_id, _ = _call_json(PRESENTER["provider"], PRESENTER["model"], system,
                                "\n".join(lines), want_array=False, max_tokens=2500,
                                schema="shichen-v1")
    obj["_run_id"] = run_id
    return obj


def chat_followup(context: dict, history: list[dict], question: str) -> dict:
    """会诊后的追问/质疑(单模型,1 次调用):基于已有会诊结果重新推算或解释。

    context: {chart_line, profile, dayun_text, shensha_text, plain_summary(dict)}
    history: [{role: user|assistant, text}](最近几轮,客户端维护)
    用户可提反对意见或补充新信息——按提示词要求把它当新数据重新推,而不是敷衍认同。
    """
    system = _prompt_system(PROMPTS / "base" / "presenter" / "chat.md")
    lines = [f"四柱:{context.get('chart_line', '')}"]
    if context.get("profile"):
        lines.append(f"本人背景:{context['profile']}")
    if context.get("shensha_text"):
        lines.append(f"神煞:{context['shensha_text']}")
    if context.get("dayun_text"):
        lines.append(f"大运:{context['dayun_text']}")
    ps = context.get("plain_summary") or {}
    if ps:
        lines.append("此前会诊结论(白话):" + json.dumps(
            {k: ps.get(k) for k in ("overview", "domains", "dayun", "yearly") if ps.get(k)},
            ensure_ascii=False))
    lines.append("")
    for h in history[-8:]:  # 只带最近 8 轮,防上下文膨胀
        who = "用户" if h.get("role") == "user" else "推演师"
        lines.append(f"{who}:{h.get('text', '')}")
    lines.append(f"用户:{question}")
    lines.append("\n请按 system 要求,只输出一个 JSON 对象。")
    obj, run_id, _ = _call_json(PRESENTER["provider"], PRESENTER["model"], system,
                                "\n".join(lines), want_array=False, max_tokens=2500,
                                schema="chat-followup-v1")
    obj["_run_id"] = run_id
    return obj


def run_consultation(chart: dict, chart_line: str, arm: str = "D3J", seed: int = 0,
                     liunian: list[dict] | None = None, dayun: dict | None = None,
                     shensha: list[dict] | None = None, profile: str = "") -> dict:
    """执行一场会诊。chart 为 four_pillars 输出;返回观察模式所需的完整结构。"""
    if arm not in ("S1", "P3", "D3", "D3J"):
        raise ConsultError(f"未知实验臂:{arm}")
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    case_hash = _sha(json.dumps(chart, ensure_ascii=False, sort_keys=True))
    order = [DEBATERS[(i + seed) % 3]["role"] for i in range(3)]  # 脱敏呈现顺序(可复现)

    # S1:单模型基线(取 debater_a 一路,不辩论)
    if arm == "S1":
        d0 = _call_debater(DEBATERS[0], chart_line, profile)
        assignments = [d0]
        cross, judge = [], None
    else:
        # 第一轮:三辩手并发独立出观点(带本人职业/处境背景,推演落地不泛化)
        with ThreadPoolExecutor(max_workers=3) as ex:
            assignments = list(ex.map(lambda d: _call_debater(d, chart_line, profile), DEBATERS))
        claims_by_role = {a["role"]: a["claims"] for a in assignments}

        cross = []
        if arm in ("D3", "D3J"):
            # 第二轮:每位辩手看另两方匿名观点后质证(并发)
            with ThreadPoolExecutor(max_workers=3) as ex:
                cross = list(ex.map(
                    lambda d: _call_cross_exam(d, _anon_blob(claims_by_role, d["role"], order)),
                    DEBATERS))

        judge = None
        if arm == "D3J":
            # 裁判轮换:从三家取一路(由 seed 决定),盲评脱敏材料
            jd = DEBATERS[seed % 3]
            material_parts = []
            for role in order:
                a = next(x for x in assignments if x["role"] == role)
                label = "甲乙丙"[order.index(role)]
                obs = "；".join(c.get("claim", "") for c in a["claims"])
                material_parts.append(f"[匿名{label}] 观察:{obs}")
            for cx in cross:
                ch = cx["cross"].get("challenges", [])
                if ch:
                    material_parts.append("质证:" + "；".join(
                        f"{c.get('target', '')}←{c.get('reason', '')}" for c in ch))
            judge = _judge(jd["provider"], jd["model"], "\n".join(material_parts))

    # 白话综述(L5 呈现层):把专业观点翻成人话 + 大运/流年逐年推演,失败不拖垮会诊
    plain = _plain_summary(chart_line, assignments, judge, liunian, dayun, shensha, profile)

    # 组装 manifest(consultation-manifest.schema.json 合规)
    now = datetime.now(timezone.utc)
    cid = now.strftime("consult-%Y%m%d-%H%M%S-") + case_hash[:8]
    all_runs = [a["run_id"] for a in assignments] + [c["run_id"] for c in cross]
    if judge:
        all_runs.append(judge["run_id"])
    issues = (judge["verdict"].get("issues", []) if judge else [])
    unresolved = [f"issue-{i}" for i, it in enumerate(issues)
                  if it.get("verdict") == "unresolved"]
    top_verdict = "unresolved" if (issues and all(
        it.get("verdict") == "unresolved" for it in issues)) else "partial"

    manifest = {
        "consultation_id": cid,
        "protocol_version": PROTOCOL_VERSION,
        "case_id": "web",
        "case_input_hash": case_hash,
        "experiment_arm": arm,
        "model_school_assignments": [
            {"role": a["role"], "provider": a["provider"], "resolved_model_id": a["model"],
             "reasoning_mode": None, "school": a["school"], "run_ids": [a["run_id"]]}
            for a in assignments],
        "judge": ({"provider": judge["provider"], "resolved_model_id": judge["model"],
                   "run_id": judge["run_id"], "candidate_order_seed": seed} if judge else None),
        "evidence_pack": {"version": "none-v0(规则库未启用)", "content_hash": case_hash,
                          "retrieved_chunk_hashes": []},
        "randomization": {"assignment_seed": seed, "candidate_order_seed": seed,
                          "decoy_selection_seed": None},
        "outputs": {"final_claim_set_hash": _sha(json.dumps(
            [a["claims"] for a in assignments], ensure_ascii=False)),
            "verdict": top_verdict if judge else "partial",
            "unresolved_claim_ids": unresolved},
        "evaluation": None,
    }
    (MANIFEST_DIR / f"{cid}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "consultation_id": cid, "arm": arm, "order": order,
        "debaters": [{"role": a["role"], "provider": a["provider"], "model": a["model"],
                      "school": a["school"], "school_name": a["school_name"],
                      "claims": a["claims"]} for a in assignments],
        "cross_exam": [{"role": c["role"], **c["cross"]} for c in cross],
        "judge": ({"by": f"{judge['provider']}(轮换盲评)", **judge["verdict"]}
                  if judge else None),
        "plain_summary": ({k: v for k, v in plain.items() if k != "_run_id"} if plain else None),
        "manifest_id": cid,
    }
