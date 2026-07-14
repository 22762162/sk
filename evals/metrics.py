"""评测自动指标(DESIGN §7.2)。

当前规则库未启用,故 citation/规则依据类指标(citation_veracity 等)标记为 N/A(pending_rulebase);
本模块只计算此刻可诚实自动化的指标:格式合规、概率化措辞、红线洁净、置信分布、
弃权/未决率、成本(调用数)与延迟。共识率/分歧率仅作行为描述,不作优化目标。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REDLINE_FILE = ROOT / "infra" / "compliance" / "redline-words.txt"
HEDGES = ["倾向", "提示", "或有", "或", "可能", "宜", "未必", "较", "多", "偏", "恐", "似"]

# 巴纳姆自动代理(DESIGN §10,INV-13):仅描述性,不替代人类盲判、不作优化目标。
sys.path.insert(0, str(ROOT / "evals" / "barnum"))
try:
    import anchors as _anchors  # noqa: E402
except ImportError:  # 词表缺位时代理指标降级为 N/A,不阻断其它指标
    _anchors = None


def _redline_words() -> list[str]:
    if not REDLINE_FILE.exists():
        return []
    out = []
    for line in REDLINE_FILE.read_text(encoding="utf-8").splitlines():
        w = line.strip()
        if w and not w.startswith("#"):
            out.append(w)
    return out


def claim_texts(result: dict) -> list[str]:
    """从会诊/单模型结果里抽出全部辩手 claim 文本。"""
    texts = []
    for d in result.get("debaters", []):
        for c in d.get("claims", []):
            if c.get("claim"):
                texts.append(str(c["claim"]))
    return texts


def barnum_proxy(texts: list[str]) -> dict:
    """巴纳姆自动代理指标(词面代理,DESIGN §10 §3.2;非语义、非确证)。

    - barnum_rate:命中预注册巴纳姆语句库的 claim 占比(可识别模板化泛化的下界)。
    - specificity_rate:引用具体命盘实体(干支/十神/大运流年/五行生克)的 claim 占比。
    - falsifiable_rate:含可现实核对断言(领域 + 时间窗/方向)的 claim 占比。
    预期:高 barnum + 低 specificity ⇒ 人类辨识应更接近随机(仅记录,不作停止依据)。
    """
    n = len(texts)
    if _anchors is None:
        return {k: "N/A(anchors_missing)" for k in
                ("barnum_rate", "specificity_rate", "falsifiable_rate")}
    if n == 0:
        return {"barnum_rate": None, "specificity_rate": None, "falsifiable_rate": None}
    bank = _anchors.load_barnum_bank()
    barnum = sum(1 for t in texts if _anchors.is_barnum(t, bank))
    specific = sum(1 for t in texts if _anchors.is_specific(t))
    falsifiable = sum(1 for t in texts if _anchors.is_falsifiable(t))
    return {
        "barnum_rate": round(barnum / n, 3),
        "specificity_rate": round(specific / n, 3),
        "falsifiable_rate": round(falsifiable / n, 3),
    }


def compute(result: dict, latency_s: float, calls: int) -> dict:
    """对一次实验臂运行结果计算自动指标。"""
    texts = claim_texts(result)
    n = len(texts)
    redline = _redline_words()

    redline_hits = sum(1 for t in texts for w in redline if w in t)
    hedged = sum(1 for t in texts if any(h in t for h in HEDGES))
    conf = {"low": 0, "medium": 0, "high": 0}
    for d in result.get("debaters", []):
        for c in d.get("claims", []):
            lbl = c.get("confidence_label")
            if lbl in conf:
                conf[lbl] += 1

    judge = result.get("judge")
    issues = (judge or {}).get("issues", []) if judge else []
    n_iss = len(issues)
    verdicts = {"consensus": 0, "dissent": 0, "unresolved": 0}
    for it in issues:
        v = it.get("verdict")
        if v in verdicts:
            verdicts[v] += 1

    return {
        "arm": result.get("arm"),
        "claims_total": n,
        "hedge_rate": round(hedged / n, 3) if n else None,          # 概率化措辞占比(越高越合规)
        "redline_hits": redline_hits,                                # 红线词命中(应为 0)
        "confidence_high_count": conf["high"],                       # 过度自信条数(应为 0)
        "confidence_dist": conf,
        "unresolved_rate": round(verdicts["unresolved"] / n_iss, 3) if n_iss else None,  # 弃权率(有 judge 时)
        "dissent_rate": round(verdicts["dissent"] / n_iss, 3) if n_iss else None,        # 分歧率(描述性)
        "issue_count": n_iss,
        "calls": calls,                                              # 成本代理(模型调用数)
        "latency_seconds": round(latency_s, 1),
        # 巴纳姆自动代理(描述性,非确证;INV-13):
        **barnum_proxy(texts),
        # 规则依据类指标待规则库启用:
        "unsupported_claim_rate": "N/A(pending_rulebase)",
        "citation_coverage": "N/A(pending_rulebase)",
    }
