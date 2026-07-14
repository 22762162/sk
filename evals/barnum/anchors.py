"""命盘实体词表与 claim 文本分类器(巴纳姆自动代理指标共用)。

这些是**词面代理**,不是语义理解:用于机制观察与预筛,不替代人类盲判(DESIGN §10,INV-13)。
纯标准库、无副作用,供 metrics.py / build_packet.py / score_packet.py 共同引用,保证一致口径。
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BANK = _ROOT / "evals" / "barnum" / "barnum-statements.jsonl"

# —— 具体命盘实体(specificity 锚点)——
# 注意:单个干支字(己/未/午…)会与常用词(自己/尚未/中午)碰撞,故干支必须落在**柱式上下文**里才算:
# 干+支相邻(庚午)、干+五行相邻(庚金/壬水)、或结构关键词(日主/月柱/透干…)。
STEMS = list("甲乙丙丁戊己庚辛壬癸")
BRANCHES = list("子丑寅卯辰巳午未申酉戌亥")
STRUCT_KEYWORDS = ["日主", "日元", "月令", "年柱", "月柱", "日柱", "时柱", "時柱",
                   "天干", "地支", "透干", "透出", "藏干", "本气", "命局", "格局"]
TEN_GODS = ["正官", "七杀", "偏官", "正财", "偏财", "正印", "偏印",
            "食神", "伤官", "比肩", "劫财", "比劫", "食伤", "官杀", "财星", "印星"]
FIVE_PHASES = list("金木水火土")
RELATIONS = ["生", "克", "剋", "泄", "洩", "耗", "制", "化", "合", "冲", "沖", "刑", "害", "会", "拱"]
LUCK = ["大运", "大運", "流年", "岁运", "歲運", "运程", "行运"]


def _has_ganzhi_context(text: str) -> bool:
    """干支须落在柱式上下文才算命中,避免 己/未/午 与常用词碰撞。"""
    if _contains_any(text, STRUCT_KEYWORDS):
        return True
    for i, ch in enumerate(text[:-1]):
        if ch in STEMS and (text[i + 1] in BRANCHES or text[i + 1] in FIVE_PHASES):
            return True  # 干+支(庚午)或 干+五行(庚金/壬水)
    return False

# —— 可证伪要素:领域 / 时间窗 / 方向 ——
DOMAINS = ["事业", "事業", "工作", "职业", "職業", "财", "財", "婚", "感情", "配偶", "健康",
           "学业", "學業", "考试", "考試", "人际", "人際", "六亲", "六親", "子女", "父母", "迁移", "遷移"]
TIME_WINDOWS = ["岁", "歲", "早年", "中年", "晚年", "青年", "少年", "近年", "近期", "未来", "未來",
                "今年", "明年", "上半年", "下半年", "本命年", "阶段", "階段", "运限", "運限"]
DIRECTIONS = ["增", "减", "減", "升", "降", "旺", "衰", "起", "落", "顺", "順", "逆", "有利", "不利",
              "利于", "利於", "受阻", "转好", "轉好", "转弱", "轉弱", "上升", "下滑"]


def _contains_any(text: str, vocab) -> bool:
    return any(v in text for v in vocab)


def specificity_anchors(text: str) -> list[str]:
    """返回命中的具体命盘实体类别(用于 specificity 判定与调试)。"""
    hits = []
    if _has_ganzhi_context(text):
        hits.append("干支")
    if _contains_any(text, TEN_GODS):
        hits.append("十神")
    if _contains_any(text, LUCK):
        hits.append("大运流年")
    # 五行 + 生克关系词同现,才算一条具体生克断言(单独"火"太弱)
    if _contains_any(text, FIVE_PHASES) and _contains_any(text, RELATIONS):
        hits.append("五行生克")
    return hits


def is_specific(text: str) -> bool:
    """claim 是否引用了至少一个具体命盘实体。"""
    return bool(specificity_anchors(text))


def is_falsifiable(text: str) -> bool:
    """claim 是否含可被现实核对的具体断言:领域 + (时间窗 或 方向)。"""
    if not _contains_any(text, DOMAINS):
        return False
    return _contains_any(text, TIME_WINDOWS) or _contains_any(text, DIRECTIONS)


def load_barnum_bank() -> list[dict]:
    """加载预注册巴纳姆语句库(冻结于 prereg;此处只读)。"""
    if not _BANK.exists():
        return []
    out = []
    for line in _BANK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            out.append(json.loads(line))
    return out


def is_barnum(text: str, bank: list[dict] | None = None) -> bool:
    """词面代理:claim 是否命中某条巴纳姆语句(标记词命中数 ≥ 该条 min_hits)。"""
    bank = load_barnum_bank() if bank is None else bank
    for entry in bank:
        markers = entry.get("markers", [])
        need = entry.get("min_hits", 2)
        if sum(1 for m in markers if m in text) >= need:
            return True
    return False
