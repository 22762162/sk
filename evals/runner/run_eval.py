"""四实验臂评测 runner(DESIGN §7.1)。

对合成盘数据集,逐盘跑 S1/P3/D3/D3J 各臂,计算自动指标,产出对照报告
(JSON + markdown,写入 evals/reports/,gitignored)。

诚实性(DESIGN §10 结论边界):小样本 smoke 只用于验证框架与观察差异,
**不构成统计结论**;报告显式标注样本量与"不确定"边界。

用法(需 .env 密钥;每盘 4 臂约 17 次调用):
    make eval-smoke                       # 跑 datasets/smoke.jsonl 全部盘 × 全部臂
    python3 evals/runner/run_eval.py --dataset evals/datasets/smoke.jsonl \
        --arms S1,P3,D3,D3J --out evals/reports/eval-<时间>.json
"""

from __future__ import annotations

import argparse
import bisect
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
sys.path.insert(0, str(ROOT / "evals"))
import consult  # noqa: E402
import metrics as M  # noqa: E402

CLI = ROOT / "engine-paipan" / "target" / "release" / "paipan-cli"
SOURCES = ROOT / "golden-tests" / "oracle-sources" / "solar_terms_de440s_1900_2100.jsonl"
TZ = ZoneInfo("Asia/Shanghai")
JIE = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
       "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]

_ju: list[int] = []
_js: list[int] = []
_lc: dict[int, int] = {}


def _load_terms() -> None:
    pairs = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        r = json.loads(line)
        if r["term"] in JIE:
            pairs.append((r["unix"], JIE.index(r["term"])))
        if r["term"] == "立春":
            _lc[r["civil_year"]] = r["unix"]
    pairs.sort()
    _ju.extend(u for u, _ in pairs)
    _js.extend(s for _, s in pairs)


def chart_of(birth: str, mode: str) -> tuple[dict, str]:
    """合成盘 → 四柱(复用引擎 CLI;与 backend 同口径)。"""
    naive = datetime.fromisoformat(birth)
    t = int(naive.replace(tzinfo=TZ).timestamp())
    std = datetime.fromtimestamp(t, timezone(timedelta(hours=8)))
    i = bisect.bisect_right(_ju, t) - 1
    case = {"case_id": "eval", "op": "four_pillars", "input": {
        "t_unix": t, "lichun_unix": _lc[std.year],
        "local": {"y": std.year, "m": std.month, "d": std.day,
                  "hh": std.hour, "mm": std.minute, "ss": std.second},
        "month_ctx": {"jie_seq": _js[i], "jie_unix": _ju[i], "next_jie_unix": _ju[i + 1]},
        "zi_hour_mode": mode}}
    proc = subprocess.run([str(CLI)], input=json.dumps(case, ensure_ascii=False) + "\n",
                          capture_output=True, text=True, timeout=10, check=True)
    o = json.loads(proc.stdout.strip().splitlines()[-1])["output"]
    line = (f"年柱 {o['year']['ganzhi']},月柱 {o['month']['ganzhi']},"
            f"日柱 {o['day']['ganzhi']},时柱 {o['hour']['ganzhi']}(八字年 {o['bazi_year']})")
    return o, line


def run_case(chart: dict, line: str, arm: str, seed: int) -> dict:
    t0 = time.monotonic()
    res = consult.run_consultation(chart, line, arm=arm, seed=seed)
    latency = time.monotonic() - t0
    # 调用数:从 manifest run_ids 统计(成本代理)
    calls = sum(len(d.get("claims", [])) and 1 for d in res["debaters"])  # 至少每辩手 1 次
    calls = len(res["debaters"]) + len(res.get("cross_exam", [])) + (1 if res.get("judge") else 0)
    return M.compute(res, latency, calls)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--arms", default="S1,P3,D3,D3J")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    _load_terms()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]

    cases = [json.loads(x) for x in Path(args.dataset).read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.startswith("#")]
    rows = []
    for c in cases:
        chart, line = chart_of(c["birth"], c.get("zi_hour_mode", "split"))
        seed = int(__import__("hashlib").sha256(line.encode()).hexdigest(), 16) % 3
        print(f"[{c['case_id']}] {line}")
        for arm in arms:
            m = run_case(chart, line, arm, seed)
            m["case_id"] = c["case_id"]
            rows.append(m)
            print(f"    {arm}: 观点 {m['claims_total']} · 弃权率 {m['unresolved_rate']} · "
                  f"调用 {m['calls']} · {m['latency_seconds']}s · 红线 {m['redline_hits']}")

    # 逐臂聚合(跨盘平均)
    agg = {}
    for arm in arms:
        ar = [r for r in rows if r["arm"] == arm]
        def avg(k):
            vals = [r[k] for r in ar if isinstance(r[k], (int, float))]
            return round(sum(vals) / len(vals), 3) if vals else None
        agg[arm] = {
            "n_cases": len(ar), "avg_claims": avg("claims_total"),
            "avg_hedge_rate": avg("hedge_rate"), "total_redline_hits": sum(r["redline_hits"] for r in ar),
            "total_high_conf": sum(r["confidence_high_count"] for r in ar),
            "avg_unresolved_rate": avg("unresolved_rate"), "avg_dissent_rate": avg("dissent_rate"),
            "avg_calls": avg("calls"), "avg_latency_s": avg("latency_seconds"),
        }

    report = {"dataset": args.dataset, "n_cases": len(cases), "arms": arms,
              "per_run": rows, "aggregate": agg,
              "honesty_note": ("小样本 smoke,仅验证框架与观察差异,不构成统计结论;"
                               "统计功效不足时结果判为不确定(DESIGN §10)。规则依据类指标待规则库启用。")}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown 对照表
    md = [f"# 四实验臂评测对照(smoke)\n",
          f"- 数据集:`{args.dataset}`,合成盘 {len(cases)} 例",
          f"- 实验臂:{', '.join(arms)}",
          f"- {report['honesty_note']}\n",
          "| 臂 | 说明 | 均观点数 | 概率化措辞率 | 红线命中 | 过度自信 | 均弃权率 | 均分歧率 | 均调用数 | 均延迟(s) |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    arm_desc = {"S1": "单模型基线", "P3": "三模型独立·不辩论",
                "D3": "三模型辩论·无裁判", "D3J": "三模型辩论·裁判盲评"}
    for arm in arms:
        a = agg[arm]
        md.append(f"| {arm} | {arm_desc.get(arm, arm)} | {a['avg_claims']} | {a['avg_hedge_rate']} "
                  f"| {a['total_redline_hits']} | {a['total_high_conf']} | {a['avg_unresolved_rate']} "
                  f"| {a['avg_dissent_rate']} | {a['avg_calls']} | {a['avg_latency_s']} |")
    md += ["\n## 读法",
           "- **弃权率(unresolved)仅 D3J 有**:裁判在证据不足处判『未决』的比例——这是单模型基线(S1)"
           "结构上缺失的诚实机制,也是会诊相对单模型最直接的可观测增益。",
           "- **成本代理(调用数)** 随臂递增:S1≈1 → D3J≈7;增益需对得起这个倍数,否则依 DESIGN §7.1 "
           "『D3J 相对 S1 无显著增益而成本数倍』本身即有效研究结论。",
           "- 概率化措辞率、红线命中、过度自信为合规护栏,各臂都应达标(红线 0、过度自信 0)。",
           "- 规则忠实度、无依据论断率等待规则库启用后补入(当前所有解读均为 model_synthesis)。"]
    Path(args.out).with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n报告 → {args.out}\n对照表 → {Path(args.out).with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
