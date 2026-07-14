"""巴纳姆盲测 packet 构建器(DESIGN §10;预注册 docs/prereg/barnum-2026-07-14.md)。

产出三件套:
  - packet.json      : 洗牌后的报告,**不含**真伪答案,可安全查看 / 交给 experiment.html
  - packet.key.json  : 真报告索引 + 洗牌种子 + packet.json 的 sha256(**gitignore,本机私有**)
  - experiment.html  : UI 实验模式(§0),只加载 packet.json;作答后本地记录选择,打开页面不泄漏答案

盲法不可逆:先由主体在 experiment.html 作答并导出 choices.json,再用 score_packet.py 读 key 揭盲评分。

两种模式:
  --birth 1990-06-15T08:30   真实模式:真盘走会诊管线,合成 k-1 张引擎合法干扰盘(不同日主)各走同管线,
                             按预注册匹配维度筛选(claim 数 ±1 / 措辞率 ±0.15 / 置信构成一致)。需 .env 密钥。
  --mock                     离线演示:用内置合成报告构建 packet,零 API、零密钥,仅演示流程与页面。

用法:
    python3 evals/barnum/build_packet.py --mock --out evals/barnum/out
    make barnum-smoke
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "barnum"))
sys.path.insert(0, str(ROOT / "consult-engine"))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "evals" / "runner"))
import anchors as A  # noqa: E402

# 预注册锁定参数(§4;改此处须新开预注册版本)
K_FORCED = 4
N_PAIRS = 6
HEDGES = ["倾向", "提示", "或有", "或", "可能", "宜", "未必", "较", "多", "偏", "恐", "似"]
MATCH = {"claims_delta": 1, "hedge_delta": 0.15, "low_frac_delta": 0.2}
REDRAW_LIMIT = 20


# ---------- 报告度量与匹配 ----------

def report_meta(lines: list[dict]) -> dict:
    n = len(lines)
    texts = [c["claim"] for c in lines]
    hedged = sum(1 for t in texts if any(h in t for h in HEDGES))
    low = sum(1 for c in lines if c.get("confidence_label") == "low")
    return {"claim_count": n,
            "hedge_rate": round(hedged / n, 3) if n else 0.0,
            "low_frac": round(low / n, 3) if n else 0.0}


def matches(real: dict, cand: dict) -> bool:
    return (abs(cand["claim_count"] - real["claim_count"]) <= MATCH["claims_delta"]
            and abs(cand["hedge_rate"] - real["hedge_rate"]) <= MATCH["hedge_delta"]
            and abs(cand["low_frac"] - real["low_frac"]) <= MATCH["low_frac_delta"])


def flatten(result: dict, rng: random.Random) -> list[dict]:
    """把会诊结果的辩手观察摊平为一份报告的条目(去重 + 洗牌,消除条目顺序线索)。"""
    seen, lines = set(), []
    for d in result.get("debaters", []):
        for c in d.get("claims", []):
            t = (c.get("claim") or "").strip()
            if t and t not in seen:
                seen.add(t)
                lines.append({"claim": t, "confidence_label": c.get("confidence_label", "low")})
    rng.shuffle(lines)
    return lines


# ---------- 真实模式(需 .env + 引擎)----------

def _real_reports(birth: str, mode: str, rng: random.Random) -> tuple[list[dict], list[list[dict]]]:
    import consult  # noqa: E402
    from run_eval import chart_of, _load_terms  # noqa: E402
    _load_terms()
    chart, line = chart_of(birth, mode)
    real = flatten(consult.run_consultation(chart, line, arm="D3J", seed=0), rng)
    real_m = report_meta(real)
    real_day = chart["day"]["ganzhi"]

    decoys: list[list[dict]] = []
    draws = 0
    while len(decoys) < K_FORCED - 1 and draws < REDRAW_LIMIT * (K_FORCED - 1):
        draws += 1
        # 合成合法盘:随机合法出生时刻 → 引擎排盘;要求日主与真盘不同
        y = rng.randint(1950, 2009)
        b = f"{y}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}T{rng.randint(0,23):02d}:{rng.randint(0,59):02d}"
        try:
            dchart, dline = chart_of(b, mode)
        except Exception:
            continue
        if dchart["day"]["ganzhi"] == real_day:
            continue
        rep = flatten(consult.run_consultation(dchart, dline, arm="D3J", seed=0), rng)
        if matches(real_m, report_meta(rep)):
            decoys.append(rep)
    if len(decoys) < K_FORCED - 1:
        raise SystemExit(f"干扰盘匹配未达 {K_FORCED-1} 张(重抽 {draws} 次超限);该 packet 作废(预注册 §6)。")
    return real, decoys


# ---------- 离线 mock(零 API,仅演示流程与页面)----------

def _mock_reports() -> tuple[list[dict], list[list[dict]]]:
    def r(*cl):
        return [{"claim": c, "confidence_label": lb} for c, lb in cl]
    real = r(
        ("日主偏弱,提示早年在事业上宜稳中求进,不利急进扩张。", "low"),
        ("印星透干,或有偏向学习型、需被认可的倾向。", "low"),
        ("大运走食伤,近年在表达与人际方面可能较为活跃。", "medium"),
    )
    d1 = r(
        ("身强财旺,提示中年在财务上或有较主动的进取倾向。", "low"),
        ("官星有力,或偏向规则明确的环境更觉安定。", "low"),
        ("流年逢冲,近期在迁移或变动方面可能有所提示。", "medium"),
    )
    d2 = r(
        ("比劫较旺,提示为人或较重朋友、讲义气。", "low"),
        ("食神生财,或有偏向以兴趣谋生的倾向。", "low"),
        ("大运转印,近年在学业进修方面可能较有心得。", "medium"),
    )
    d3 = r(
        ("日主中和,提示性情或较能在不同环境间调整自处。", "low"),
        ("财官相生,或偏向务实、看重稳定回报。", "low"),
        ("流年见伤官,近期在表达或创作方面可能较有想法。", "medium"),
    )
    return real, [d1, d2, d3]


# ---------- 组装盲测题 ----------

def build(real: list[dict], decoys: list[list[dict]], seed: int) -> tuple[dict, dict]:
    rng = random.Random(seed)
    reports = [{"report": real, "_real": True}] + [{"report": d, "_real": False} for d in decoys]

    # 强制匹配:洗牌,记录真报告落点
    fc = list(reports)
    rng.shuffle(fc)
    forced = {"k": len(fc), "options": [{"opt_id": f"O{i+1}", "report": o["report"]}
                                        for i, o in enumerate(fc)]}
    real_opt = next(f"O{i+1}" for i, o in enumerate(fc) if o["_real"])

    # 成对比较:真报告 vs 随机一张干扰盘,左右随机
    pairs, key_pairs = [], []
    for j in range(N_PAIRS):
        decoy = decoys[rng.randrange(len(decoys))]
        real_left = rng.random() < 0.5
        left, right = (real, decoy) if real_left else (decoy, real)
        pairs.append({"pair_id": f"P{j+1}", "left": left, "right": right})
        key_pairs.append({"pair_id": f"P{j+1}", "real_side": "left" if real_left else "right"})

    packet = {"design": "barnum-blind-v1", "prereg": "docs/prereg/barnum-2026-07-14.md",
              "forced_choice": forced, "pairwise": pairs,
              "note": "本文件不含真伪答案;揭盲用 score_packet.py 读 packet.key.json。"}
    key = {"forced_choice_real_opt": real_opt, "pairwise": key_pairs, "seed": seed}
    return packet, key


# ---------- experiment.html(UI 实验模式)----------

def experiment_html(packet: dict) -> str:
    data = json.dumps(packet, ensure_ascii=False)
    return _HTML_TEMPLATE.replace("__PACKET_JSON__", data)


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>三鉴 · 巴纳姆自盲实验(实验模式)</title>
<style>
 body{font-family:-apple-system,"PingFang SC",sans-serif;max-width:860px;margin:0 auto;padding:20px;color:#1c1c1e;background:#f5f5f7}
 .banner{background:#8a1c1c;color:#fff;padding:10px 14px;border-radius:8px;font-weight:600;margin-bottom:14px}
 h2{margin:22px 0 8px;font-size:18px} .sub{color:#555;font-size:13px;margin:0 0 12px}
 .cards{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
 .card{background:#fff;border:2px solid #e2e2e6;border-radius:10px;padding:12px;cursor:pointer}
 .card.sel{border-color:#0a67d3;box-shadow:0 0 0 2px #cfe2fb}
 .card h4{margin:0 0 8px;font-size:14px;color:#0a67d3} .card ul{margin:0;padding-left:18px} .card li{margin:5px 0;font-size:13px;line-height:1.5}
 .pair{background:#fff;border:1px solid #e2e2e6;border-radius:10px;padding:12px;margin:10px 0}
 .pair .cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .opt{border:2px solid #e2e2e6;border-radius:8px;padding:10px;cursor:pointer;font-size:13px;line-height:1.5}
 .opt.sel{border-color:#0a67d3;background:#f0f6ff} .opt ul{margin:0;padding-left:16px}
 .choices{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}
 .chip{border:1px solid #bbb;border-radius:16px;padding:4px 12px;cursor:pointer;font-size:12px;background:#fff}
 .chip.sel{background:#0a67d3;color:#fff;border-color:#0a67d3}
 button.go{margin:20px 0;background:#0a67d3;color:#fff;border:0;border-radius:8px;padding:12px 22px;font-size:15px;cursor:pointer}
 pre{background:#111;color:#0f0;padding:12px;border-radius:8px;overflow:auto;font-size:12px}
</style></head><body>
<div class="banner">实验模式 · 盲法进行中：本页不含任何真伪标注。请凭「哪一份更像在描述我」作答。</div>
<p class="sub">目的:检验会诊报告是否携带针对你本人的可辨识信息(而非人人都对的泛化)。作答完成后导出结果,再用 score_packet.py 揭盲。</p>

<h2>一、强制匹配</h2>
<p class="sub">下面 <span id="k"></span> 份报告中,只有一份是针对你本人的四柱生成的。选出你认为写的是你的那一份。</p>
<div class="cards" id="forced"></div>

<h2>二、成对比较</h2>
<p class="sub">每组两份报告,选「哪一份更像我」;若确实分不出,选「无法区分」(计为弃权,不算对错)。</p>
<div id="pairs"></div>

<button class="go" id="submit">完成并导出结果</button>
<pre id="out" style="display:none"></pre>

<script>
const P = __PACKET_JSON__;
const st = {forced:null, pairs:{}};
const rep = r => "<ul>"+r.map(c=>"<li>"+c.claim+"</li>").join("")+"</ul>";

document.getElementById("k").textContent = P.forced_choice.k;
const fc = document.getElementById("forced");
P.forced_choice.options.forEach((o,i)=>{
  const d=document.createElement("div"); d.className="card"; d.innerHTML="<h4>报告 "+(i+1)+"</h4>"+rep(o.report);
  d.onclick=()=>{st.forced=o.opt_id;[...fc.children].forEach(c=>c.classList.remove("sel"));d.classList.add("sel");};
  fc.appendChild(d);
});

const pc = document.getElementById("pairs");
P.pairwise.forEach(pr=>{
  const box=document.createElement("div"); box.className="pair";
  box.innerHTML="<b>"+pr.pair_id+"</b><div class='cols'><div class='opt' data-s='left'><b>左</b>"+rep(pr.left)+"</div><div class='opt' data-s='right'><b>右</b>"+rep(pr.right)+"</div></div>"+
    "<div class='choices'><span class='chip' data-c='left'>左更像我</span><span class='chip' data-c='right'>右更像我</span><span class='chip' data-c='abstain'>无法区分</span></div>";
  box.querySelectorAll(".chip").forEach(ch=>ch.onclick=()=>{
    st.pairs[pr.pair_id]=ch.dataset.c;
    box.querySelectorAll(".chip").forEach(x=>x.classList.remove("sel")); ch.classList.add("sel");
    box.querySelectorAll(".opt").forEach(o=>o.classList.toggle("sel", o.dataset.s===ch.dataset.c));
  });
  pc.appendChild(box);
});

document.getElementById("submit").onclick=()=>{
  if(!st.forced){alert("请先完成强制匹配");return;}
  const out={design:P.design, submitted:true,
    forced_choice_pick:st.forced,
    pairwise:P.pairwise.map(p=>({pair_id:p.pair_id, pick:st.pairs[p.pair_id]||"abstain"}))};
  const o=document.getElementById("out"); o.style.display="block";
  o.textContent="已记录你的选择(不含答案)。请把下面内容存为 choices.json,再运行:\n  python3 evals/barnum/score_packet.py --choices choices.json --key <你的 packet.key.json>\n\n"+JSON.stringify(out,null,2);
  const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="choices.json"; a.textContent="⬇ 下载 choices.json";
  a.style.cssText="display:block;margin-top:10px;color:#0a67d3"; o.after(a);
};
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--birth", help="真实主体出生(ISO);缺省需 --mock")
    ap.add_argument("--zi-hour-mode", default="split")
    ap.add_argument("--mock", action="store_true", help="离线演示,零 API")
    ap.add_argument("--seed", type=int, default=20260714)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    if args.mock:
        real, decoys = _mock_reports()
        print(f"[mock] 真报告 {report_meta(real)};干扰盘 {len(decoys)} 张(离线合成,仅演示)")
    else:
        if not args.birth:
            raise SystemExit("真实模式须给 --birth(或用 --mock 离线演示)")
        real, decoys = _real_reports(args.birth, args.zi_hour_mode, rng)
        print(f"[real] 真报告 {report_meta(real)};匹配干扰盘 {len(decoys)} 张")

    packet, key = build(real, decoys, args.seed)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    ptext = json.dumps(packet, ensure_ascii=False, indent=2)
    (outdir / "packet.json").write_text(ptext, encoding="utf-8")
    key["packet_sha256"] = hashlib.sha256(ptext.encode("utf-8")).hexdigest()
    (outdir / "packet.key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "experiment.html").write_text(experiment_html(packet), encoding="utf-8")

    print(f"packet   → {outdir/'packet.json'}(无答案,可查看)")
    print(f"key      → {outdir/'packet.key.json'}(私有,勿提交;揭盲用)")
    print(f"实验页面 → {outdir/'experiment.html'}(浏览器打开作答,§0 实验模式)")
    print(f"强制匹配随机水平 1/{packet['forced_choice']['k']};成对 {len(packet['pairwise'])} 组,随机水平 0.5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
