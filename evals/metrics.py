"""评测自动指标(DESIGN §7.2)。

当前规则库未启用,故 citation/规则依据类指标(citation_veracity 等)标记为 N/A(pending_rulebase);
本模块只计算此刻可诚实自动化的指标:格式合规、概率化措辞、红线洁净、置信分布、
弃权/未决率、成本(调用数)与延迟。共识率/分歧率仅作行为描述,不作优化目标。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REDLINE_FILE = ROOT / "infra" / "compliance" / "redline-words.txt"
HEDGES = ["倾向", "提示", "或有", "或", "可能", "宜", "未必", "较", "多", "偏", "恐", "似"]


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
        # 规则依据类指标待规则库启用:
        "unsupported_claim_rate": "N/A(pending_rulebase)",
        "citation_coverage": "N/A(pending_rulebase)",
    }
