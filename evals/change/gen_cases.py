"""生成 100 例分层合成用例 v2(整改版;确定性 seed,生成后冻结 lock)。

整改(P19 审查第 5 条):
- 八字材料改为**中性结构合成盘**(四柱从六十甲子采样+性别),不含"身强财旺"类预解释,
  并显式标注"结构合成,非真实历法盘"——本集仅支撑结构/合规试验,不支撑测算有效性结论。
- 问句自带期限词(月内/两周内/季度内),deadline 按期限词锁齐,不再随机漂移。
用法:python3 evals/change/gen_cases.py → cases/sanshu-v100.jsonl + sanshu-v100.lock
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

SEED = 20260901
GENERATOR_VERSION = 2
OUT = Path(__file__).parent / "cases"
STEMS, BRANCHES = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

# (期限词, deadline) 锁齐;问句模板内嵌期限词
HORIZONS = {"月内": "2026-09-30", "两周内": "2026-09-14", "季度内": "2026-11-30"}
QUESTIONS = {
    "事业": [("月内", "核心业务目标月内能否推进到位"), ("月内", "关键岗位调整月内能否落定"),
             ("两周内", "两周内团队排班调整能否理顺"), ("季度内", "新业务线季度内能否立项通过"),
             ("月内", "月内考核目标达成有无变数")],
    "财务": [("月内", "月内回款能否达到既定水平"), ("两周内", "两周内成本超支能否刹住"),
             ("月内", "预算审批月内能否走完"), ("季度内", "季度内分成结算是否顺利"),
             ("月内", "月内资金周转是否宽裕")],
    "合作": [("月内", "与候选伙伴的洽谈月内有无结果"), ("两周内", "两周内续约分歧能否谈拢"),
             ("月内", "新渠道合作月内能否签署"), ("季度内", "季度内新供应方能否落地"),
             ("月内", "合作纠纷月内能否化解")],
    "时机": [("两周内", "两周内启动新企划是否合适"), ("月内", "月内对外发布消息是否得时"),
             ("月内", "月内变更既定安排是否顺利"), ("两周内", "两周内出行安排是否顺遂"),
             ("季度内", "季度内择机扩张是否有利")],
    "进度": [("月内", "在建项目月内能否如期交付"), ("两周内", "两周内验收环节能否一次通过"),
             ("月内", "拖延事项月内能否收尾"), ("季度内", "季度内里程碑能否按计划达成"),
             ("月内", "整改事项月内能否完成")],
}


def neutral_chart(rng: random.Random) -> str:
    """中性结构盘:只给结构事实,零解释倾向。"""
    p = [rng.choice(JIAZI) for _ in range(4)]
    gender = rng.choice(["乾造", "坤造"])
    return (f"{gender}(结构合成,非真实历法盘):年柱{p[0]} 月柱{p[1]} 日柱{p[2]} 时柱{p[3]};"
            f"本集仅作结构/合规试验材料")


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    i = 0
    for scene in ("personal", "company"):
        for method in ("liuyao", "meihua"):
            for domain, qs in QUESTIONS.items():
                for horizon, q in qs:
                    i += 1
                    case = {"id": f"v100-{i:03d}", "scene": scene, "method": method,
                            "domain": domain, "horizon": horizon, "question": q,
                            "deadline": HORIZONS[horizon],
                            "bazi_material": neutral_chart(rng),
                            "facts_summary": (rng.choice(
                                ["上期完成率约七成,两项在谈(合成)",
                                 "近四周指标缓升,一项延期(合成)",
                                 "上月新增三个候选项,一项搁置(合成)", ""])
                                if scene == "company" else "")}
                    if method == "liuyao":
                        case.update(lines=[rng.choice((6, 7, 8, 9)) for _ in range(6)],
                                    day_ganzhi=rng.choice(JIAZI),
                                    month_branch=rng.choice(BRANCHES))
                    else:
                        case.update(n1=rng.randint(1, 64), n2=rng.randint(1, 64),
                                    hour_branch=rng.choice(BRANCHES))
                    rows.append(case)
    assert len(rows) == 100
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 100
    body = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n"
    (OUT / "sanshu-v100.jsonl").write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode()).hexdigest()
    (OUT / "sanshu-v100.lock").write_text(json.dumps({
        "file": "sanshu-v100.jsonl", "sha256": digest, "seed": SEED,
        "generator_version": GENERATOR_VERSION, "n": 100, "unique_ids": True,
        "strata": "scene2×method2×domain5×variant5",
        "material_policy": "中性结构合成盘,无预解释;仅支撑结构/合规试验,不支撑测算有效性结论",
        "note": "冻结用例集:哈希不匹配即拒跑;变更须新版本+本人确认"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"v100(gen v{GENERATOR_VERSION}) 已生成并冻结 sha256={digest[:16]}…")


if __name__ == "__main__":
    main()
