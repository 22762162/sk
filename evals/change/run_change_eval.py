"""sanshu 三段封存 · Change Eval 执行器(P19;INV-12:本文件与候选提示词永不同 PR 改)。

模式:
  dry  — 注入合成 caller(结构合规样本),验证 用例→装卦→编排→校验→聚合 全管道,零模型调用。
  real — 经 gateway 调三家运行态模型(仅本机、需密钥、受 --cap 限)。
聚合报告写 reports/<ts>-summary.md(跨代理只传阅聚合);逐例原文写 reports/raw/(不传阅)。
用法:uv run --with httpx python3 evals/change/run_change_eval.py \
       --cases evals/change/cases/sanshu-v1-smoke8.jsonl --prompts-dir prompts/candidates \
       --mode dry|real --cap 90
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))

import liuyao  # noqa: E402
import meihua  # noqa: E402
import sanshu_orchestrator as so  # noqa: E402

PROVIDERS = [("anthropic", "claude-sonnet-5"), ("gemini", "gemini-3.6-flash"),
             ("deepseek", "deepseek-chat")]
REDLINE_FILE = ROOT / "infra" / "compliance" / "redline-words.txt"


def load_prompts(pdir: Path) -> dict:
    def body(name):
        text = (pdir / name).read_text(encoding="utf-8")
        return text.split("## system", 1)[1].strip() if "## system" in text else text
    return {"bazi": body("sanshu-bazi-v2.md"), "gua": body("sanshu-gua-v2.md"),
            "combined": body("sanshu-combined-v2.md")}


def build_cast(case: dict):
    if case["method"] == "liuyao":
        return liuyao.cast(case["lines"], case["day_ganzhi"], case["month_branch"])
    return meihua.cast_numbers(case["n1"], case["n2"], case["hour_branch"])


def redline_hits(text: str) -> list[str]:
    words = [w.strip() for w in REDLINE_FILE.read_text(encoding="utf-8").splitlines()
             if w.strip() and not w.startswith("#")]
    return [w for w in words if w in text]


def dry_caller_factory(cast_hash: str, method: str):
    def caller(role, system, user):
        ev = {"statement": "本窗口内目标事项出现明确进展", "window": {"start": "2026-09-01", "end": "2026-09-30"},
              "metric": {"indicator": "事项进展", "comparator": "发生", "threshold": None, "unit": None},
              "adjudication": "以本人当期记录为准判定发生与否"}
        base = {"status": "ok", "confidence": "medium",
                "yingqi": {"start": "2026-09-01", "end": "2026-09-30"},
                "verifiable_events": [ev], "method_basis": "干跑合成依据,仅验管道"}
        if role == "bazi":
            return json.dumps({**base, "reading": "干跑合成八字段落,长度补齐" + "验" * 10},
                              ensure_ascii=False), "dry-b"
        if role == "gua":
            return json.dumps({**base, "reading": "干跑合成卦段落,长度补齐" + "验" * 10,
                               "method": method, "cast_hash": cast_hash},
                              ensure_ascii=False), "dry-g"
        return json.dumps({**base, "answer": "干跑合成综合回答,先给结论示例",
                           "reasoning": "干跑合成推理,两段合参示意" + "验" * 8,
                           "dissent_note": ""}, ensure_ascii=False), "dry-c"
    return caller


def real_caller_factory(provider: str, model: str, budget: dict):
    import gateway  # noqa: PLC0415 仅 real 模式引入(需密钥环境)

    def caller(role, system, user):
        if budget["left"] <= 0:
            raise so.OrchestrationError("Change Eval 调用预算耗尽")
        budget["left"] -= 1
        text, run_id, _usage = gateway.call(provider, model, system=system, user=user,
                                            temperature=-1, max_tokens=2500,
                                            output_schema_version="sanshu-eval-v1")
        return text, run_id
    return caller


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--prompts-dir", required=True)
    ap.add_argument("--mode", choices=("dry", "real"), default="dry")
    ap.add_argument("--cap", type=int, default=90)
    args = ap.parse_args()
    try:
        prompts = load_prompts(Path(args.prompts_dir))
    except FileNotFoundError:
        if args.mode != "dry":
            raise
        prompts = dict.fromkeys(("bazi", "gua", "combined"), "DRY_PIPELINE_PLACEHOLDER_SYSTEM")
        print("[dry] 候选提示词未就位,使用占位 system(仅验管道)")
    cases = [json.loads(l) for l in Path(args.cases).read_text(encoding="utf-8").splitlines() if l.strip()]
    budget = {"left": args.cap}
    stats: dict = {}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = ROOT / "evals" / "change" / "reports" / "raw" / run_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    for provider, model in PROVIDERS:
        st = stats.setdefault(provider, {"n": 0, "valid_first": 0, "retried": 0, "failed": 0,
                                         "abstain": 0, "leak_blocked": 0, "leak_retained": 0, "redline": 0})
        for case in cases:
            cast = build_cast(case)
            ch = so.seal(cast)
            caller = (dry_caller_factory(ch, case["method"]) if args.mode == "dry"
                      else real_caller_factory(provider, model, budget))
            st["n"] += 1
            try:
                r = so.run_provider_chain(
                    caller, provider, prompts, case["question"], case["deadline"],
                    case["bazi_material"], cast, case["method"],
                    facts_summary=case.get("facts_summary", ""),
                    facts_meta={"known_at": "2026-08-30", "confirmed_at": "2026-08-31"})
            except so.OrchestrationError:
                st["failed"] += 1
                continue
            calls = r["manifest"]["calls"]
            attempts = [a for arr in calls.values() for a in arr if isinstance(a, dict) and "attempt" in a]
            if any(a["attempt"] > 1 for a in attempts):
                st["retried"] += 1
            else:
                st["valid_first"] += 1
            if any("独有词" in e for a in attempts for e in a.get("errors", [])):
                st["leak_blocked"] += 1
            import sanshu_validator as _sv
            for name, sec in (("bazi", r["bazi"]), ("gua", r["gua"]), ("combined", r["combined"])):
                if isinstance(sec, dict) and sec.get("status") == "abstain":
                    st["abstain"] += 1
                if isinstance(sec, dict):
                    st["redline"] += len(redline_hits(json.dumps(sec, ensure_ascii=False)))
                    banned = _sv.GUA_ONLY_TERMS if name == "bazi" else (_sv.BAZI_ONLY_TERMS if name == "gua" else ())
                    st["leak_retained"] += len(_sv.scan_banned(sec, banned))  # 留存泄漏实算
            (raw_dir / f"{provider}-{case['id']}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.mode == "dry":
            break  # 干跑验管道,一家即可
    ts = run_id
    rates = {p: (s["valid_first"] / s["n"] if s["n"] else 0) for p, s in stats.items()}
    spread = (max(rates.values()) - min(rates.values())) if len(rates) > 1 else 0.0
    lines = [f"# Change Eval 聚合 · sanshu-v1 · mode={args.mode} · {ts}", "",
             "| provider | n | valid_first | retried | failed | abstain | leak_blocked | leak_retained | redline |",
             "|---|---|---|---|---|---|---|---|---|"]
    for p, s in stats.items():
        lines.append(f"| {p} | {s['n']} | {s['valid_first']} ({rates[p]:.0%}) | {s['retried']} "
                     f"| {s['failed']} | {s['abstain']} | {s['leak_blocked']} "
                     f"| {s['leak_retained']} | {s['redline']} |")
    gates = {"valid_rate>=0.80": all(v >= 0.80 for v in rates.values()),
             "redline==0": all(s["redline"] == 0 for s in stats.values()),
             "leak_after_validator==0": all(s["leak_retained"] == 0 for s in stats.values()),
             "provider_spread<=0.20": spread <= 0.20}
    lines += ["", f"对称性极差:{spread:.2f}", "",
              "门槛判定:" + json.dumps(gates, ensure_ascii=False),
              "结论:" + ("DRY-PIPELINE-ONLY(非门槛判定,不得用于放行)" if args.mode == "dry"
                       else ("PASS(门槛为草案,待独立评审与本人确认后方有效)" if all(gates.values()) else "FAIL")),
              "", "说明:干跑仅验管道不作门槛判定依据;abstain 只披露不设门槛;逐例原文在 raw/ 不传阅。"]
    out = ROOT / "evals" / "change" / "reports" / f"{ts}-summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n聚合报告:{out}")
    return 0 if (args.mode == "dry" or all(gates.values())) else 1


if __name__ == "__main__":
    sys.exit(main())
