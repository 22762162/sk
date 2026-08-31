"""生成 100 例分层合成用例(DESIGN 口径;确定性 seed,生成后冻结 lock 哈希)。

分层:scene{personal,company} × method{liuyao,meihua} × domain{事业,财务,合作,时机,进度} × 5 变体 = 100。
全合成(INV-07):命盘材料为占位文本,事实为虚构数字;起卦输入由种子确定,可回放。
用法:python3 evals/change/gen_cases.py  → 写 cases/sanshu-v100.jsonl 与 sanshu-v100.lock
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

SEED = 20260901
OUT = Path(__file__).parent / "cases"
STEMS, BRANCHES = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
JIAZI = [STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)]

QUESTIONS = {
    "事业": ["本期核心业务目标能否推进到位", "月内关键岗位调整是否顺利落定", "本期团队扩编计划能否完成",
             "季度内新业务线能否立项通过", "本期考核目标达成有无变数"],
    "财务": ["本期回款能否达到既定水平", "月内成本控制目标能否守住", "本期预算审批能否按时通过",
             "季度分成结算是否顺利", "本期资金周转是否宽裕"],
    "合作": ["与候选伙伴的洽谈本期有无结果", "月内续约谈判能否谈拢", "新渠道合作本期能否签署",
             "合作分歧本期能否化解", "引入的新供应方本期能否落地"],
    "时机": ["两周内启动新企划是否合适", "本期是否适合对外发布消息", "月内择机变更安排是否顺利",
             "本期出行安排是否顺遂", "月末节点行动是否有利"],
    "进度": ["在建项目本期能否如期交付", "月内验收环节能否一次通过", "拖延事项本期能否收尾",
             "本期里程碑能否按计划达成", "整改事项月内能否完成"],
}
MATERIALS = ["合成乾造:身强财旺,月令生扶(占位)", "合成坤造:食伤生财,印绶护身(占位)",
             "合成乾造:官星显,比劫帮身(占位)", "合成坤造:财星入库,驿马暗动(占位)"]
FACTS = ["上期完成率约七成,两项在谈(合成)", "近四周指标呈缓升,一项延期(合成)",
         "上月新增三个候选项,一项搁置(合成)", ""]


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    i = 0
    for scene in ("personal", "company"):
        for method in ("liuyao", "meihua"):
            for domain, qs in QUESTIONS.items():
                for v in range(5):
                    i += 1
                    case = {"id": f"v100-{i:03d}", "scene": scene, "method": method,
                            "domain": domain, "question": qs[v],
                            "deadline": rng.choice(["2026-09-30", "2026-10-15", "2026-11-30"]),
                            "bazi_material": rng.choice(MATERIALS),
                            "facts_summary": rng.choice(FACTS) if scene == "company" else ""}
                    if method == "liuyao":
                        case.update(lines=[rng.choice((6, 7, 8, 9)) for _ in range(6)],
                                    day_ganzhi=rng.choice(JIAZI),
                                    month_branch=rng.choice(BRANCHES))
                    else:
                        case.update(n1=rng.randint(1, 64), n2=rng.randint(1, 64),
                                    hour_branch=rng.choice(BRANCHES))
                    rows.append(case)
    assert len(rows) == 100
    body = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n"
    (OUT / "sanshu-v100.jsonl").write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode()).hexdigest()
    (OUT / "sanshu-v100.lock").write_text(
        json.dumps({"file": "sanshu-v100.jsonl", "sha256": digest, "seed": SEED,
                    "n": 100, "strata": "scene2×method2×domain5×variant5",
                    "note": "冻结用例集:哈希不匹配即拒跑;变更须新版本+本人确认"},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已生成 100 例并冻结 sha256={digest[:16]}…")


if __name__ == "__main__":
    main()
