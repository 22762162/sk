"""研究模式评测:3×3 拉丁方,分离模型效应与流派效应(DESIGN §2.3)。

固定绑定下,辩手输出的差异分不清来自模型还是流派。拉丁方让每个模型演每个流派
各一次,于是可用边际均值把两个因素拆开:
  - 模型效应:某模型跨全部流派的均值(它固有的输出倾向)
  - 流派效应:某流派跨全部模型的均值(该派固有的输出形态)
本模块只做**描述性**分离(观察量:观点数、概率化措辞率、置信构成),不主张因果或优劣。

用法(需 .env 密钥;1 盘 = 9 次调用):
    make research-smoke
    python3 evals/runner/run_research.py --birth 1990-06-15T08:30 --out evals/reports/research.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "evals" / "runner"))
import consult  # noqa: E402
import metrics as M  # noqa: E402
from run_eval import chart_of, _load_terms  # noqa: E402


def _cell_metrics(cell: dict) -> dict:
    fake = {"debaters": [cell]}  # 复用 metrics.compute 的 claim 抽取
    texts = M.claim_texts(fake)
    n = len(texts)
    hedged = sum(1 for t in texts if any(h in t for h in M.HEDGES))
    high = sum(1 for c in cell["claims"] if c.get("confidence_label") == "high")
    return {"claims": n, "hedge_rate": round(hedged / n, 3) if n else 0.0,
            "high_conf": high}


def _marginal(cells: list[dict], key: str) -> dict:
    """按 key(provider 或 school)聚合边际均值。"""
    out = {}
    for c in cells:
        out.setdefault(c[key], []).append(c["_m"])
    agg = {}
    for k, ms in out.items():
        agg[k] = {
            "avg_claims": round(sum(m["claims"] for m in ms) / len(ms), 2),
            "avg_hedge_rate": round(sum(m["hedge_rate"] for m in ms) / len(ms), 3),
            "total_high_conf": sum(m["high_conf"] for m in ms),
            "n_cells": len(ms),
        }
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--birth", required=True)
    ap.add_argument("--zi-hour-mode", default="split")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    _load_terms()
    chart, line = chart_of(args.birth, args.zi_hour_mode)
    print(f"研究模式(拉丁方)· {line}")

    cells = consult.run_latin_cells(line)
    for c in cells:
        c["_m"] = _cell_metrics(c)
        print(f"  批{c['batch']} · {c['provider']}×{c['school_name']}: "
              f"观点 {c['_m']['claims']} · 措辞率 {c['_m']['hedge_rate']}")

    by_model = _marginal(cells, "provider")
    by_school = _marginal(cells, "school_name")

    # 变异分解(粗略):模型间极差 vs 流派间极差,谁大谁更主导观察差异
    def spread(agg, k):
        vals = [v[k] for v in agg.values()]
        return round(max(vals) - min(vals), 3) if vals else 0.0
    model_spread = spread(by_model, "avg_claims")
    school_spread = spread(by_school, "avg_claims")

    report = {
        "birth": args.birth, "chart": line, "design": "3x3-latin-square",
        "cells": [{k: c[k] for k in ("batch", "provider", "school", "school_name")} | c["_m"]
                  for c in cells],
        "marginal_by_model": by_model, "marginal_by_school": by_school,
        "spread": {"claims_model_range": model_spread, "claims_school_range": school_spread,
                   "dominant": "模型" if model_spread > school_spread else
                               ("流派" if school_spread > model_spread else "相当")},
        "honesty_note": ("单盘拉丁方为机制演示,非统计结论;描述性分离,不主张因果或优劣。"
                         "多盘 + 重复方能估计交互与显著性(DESIGN §10)。"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# 拉丁方研究模式(单盘机制演示)\n", f"- 命盘:{line}",
          f"- {report['honesty_note']}\n",
          "## 3×3 单元(模型 × 流派)——观点数 / 概率化措辞率\n",
          "| 模型＼流派 | 子平格局派 | 旺衰扶抑派 | 调候派 |",
          "| --- | --- | --- | --- |"]
    prov_name = {"anthropic": "Claude", "openai": "GPT", "deepseek": "DeepSeek"}
    grid = {(c["provider"], c["school"]): c["_m"] for c in cells}
    for p in ("anthropic", "openai", "deepseek"):
        row = [prov_name[p]]
        for s in ("ziping", "wangshuai", "tiaohou"):
            m = grid.get((p, s), {})
            row.append(f"{m.get('claims','–')} / {m.get('hedge_rate','–')}")
        md.append("| " + " | ".join(row) + " |")
    md += ["\n## 边际均值(效应分离)\n",
           "**按模型**(跨全部流派 → 模型固有倾向):"]
    for k, v in by_model.items():
        md.append(f"- {prov_name.get(k,k)}:均观点 {v['avg_claims']} · 均措辞率 {v['avg_hedge_rate']}")
    md.append("\n**按流派**(跨全部模型 → 流派固有形态):")
    for k, v in by_school.items():
        md.append(f"- {k}:均观点 {v['avg_claims']} · 均措辞率 {v['avg_hedge_rate']}")
    md += [f"\n## 变异主导(粗略)\n",
           f"- 模型间观点数极差 {model_spread} vs 流派间极差 {school_spread} → "
           f"本盘观察差异更受【{report['spread']['dominant']}】驱动。",
           "- 这是拉丁方的价值:固定绑定时此二者不可分,轮换后才可归因。单盘仅演示机制。"]
    Path(args.out).with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n报告 → {args.out}\n矩阵 → {Path(args.out).with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
