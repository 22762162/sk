"""巴纳姆盲测揭盲评分(DESIGN §10;预注册 §7/§8)。

只在主体作答固定后执行:读 choices.json(experiment.html 导出)+ packet.key.json(私有答案),
比对评分,并按预注册的精确二项检验对随机水平给出点估计与结论边界提示。

顺序不可逆:严禁先看 key 再作答。本脚本假定 choices.json 已先行生成。

用法:
    python3 evals/barnum/score_packet.py --choices choices.json --key evals/barnum/out/packet.key.json
"""

from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path


def binom_tail_ge(k: int, n: int, p: float) -> float:
    """P(X >= k) 精确二项(单侧);标准库实现,无需 scipy。"""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--choices", required=True)
    ap.add_argument("--key", required=True)
    args = ap.parse_args()
    choices = json.loads(Path(args.choices).read_text(encoding="utf-8"))
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))

    # 强制匹配(单题):命中真报告?对照随机水平 1/k。
    fc_pick = choices.get("forced_choice_pick")
    fc_real = key["forced_choice_real_opt"]
    fc_hit = fc_pick == fc_real

    # 成对比较:统计有效试次(排除弃权)与命中真报告数。
    real_side = {p["pair_id"]: p["real_side"] for p in key["pairwise"]}
    valid = hits = abstain = 0
    for c in choices.get("pairwise", []):
        pick = c.get("pick")
        if pick == "abstain" or pick not in ("left", "right"):
            abstain += 1
            continue
        valid += 1
        if pick == real_side.get(c["pair_id"]):
            hits += 1

    p_pair = binom_tail_ge(hits, valid, 0.5) if valid else None

    print("=== 巴纳姆自盲实验 · 揭盲评分 ===")
    print(f"[强制匹配] 选 {fc_pick} · 真报告 {fc_real} · {'命中' if fc_hit else '未中'}(随机水平仅一题,不足以单独下结论)")
    print(f"[成对比较] 有效 {valid} 次,命中真报告 {hits} 次,弃权 {abstain} 次")
    if valid:
        rate = round(hits / valid, 3)
        print(f"           「更像我」命中率 {rate}(对照 0.5);单侧精确二项 P(X≥{hits}) = {round(p_pair,4)}")
    print()
    print("结论边界(预注册 §9,强制):")
    print("  · 单主体先导样本量先天不足,统计功效不够,主结论只能判「不确定」;")
    print("  · 显著与否均只形成研究记录,powered 判定须多主体扩展达成后进行;")
    print("  · 阳性亦不等于命理有效,仅表示该报告文本对本主体可区分。")

    Path(args.choices).with_name("score.json").write_text(json.dumps({
        "forced_choice_hit": fc_hit, "pairwise_valid": valid, "pairwise_hits": hits,
        "pairwise_abstain": abstain, "pairwise_p_value": p_pair,
        "verdict": "inconclusive_pilot", "note": "单主体先导,功效不足,判定不确定(预注册 §9)。",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
