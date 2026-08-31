"""梅花易数起卦引擎(确定性;规格 docs/specs/liuyao-meihua-v1.md;rules: meihua-rules-v1)。

v1 只支持「报数起卦」(两数+时辰,经典口径、无历法依赖);
时间起卦需农历朔日表,列为 P3 决策项,不得用公历数字冒充农历。
"""

from __future__ import annotations

from liuyao import TRIGRAM_BY_BITS, TRIGRAMS, TRIGRAM_ELEM, XIANTIAN_ORDER, _hex_name

RULES_VERSION = "meihua-rules-v1"
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
HOUR_INDEX = {b: i + 1 for i, b in enumerate("子丑寅卯辰巳午未申酉戌亥")}


def _trigram_by_num(n: int) -> str:
    r = n % 8
    return XIANTIAN_ORDER[(r if r else 8) - 1]


def cast_numbers(n1: int, n2: int, hour_branch: str) -> dict:
    """报数起卦:n1→上卦,n2→下卦,(n1+n2+时辰序)%6 定动爻(0 作 6)。"""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("两数须为正整数")
    if hour_branch not in HOUR_INDEX:
        raise ValueError("时辰须为地支")
    up, low = _trigram_by_num(n1), _trigram_by_num(n2)
    total = n1 + n2 + HOUR_INDEX[hour_branch]
    moving = total % 6 or 6
    bits = TRIGRAMS[low] + TRIGRAMS[up]
    changed = tuple(b ^ (1 if i + 1 == moving else 0) for i, b in enumerate(bits))
    hu = bits[1:4] + bits[2:5]  # 互卦:二三四为下,三四五为上
    # 体用:动爻所在之卦为用,另一卦为体
    yong_pos = "low" if moving <= 3 else "up"
    ti, yong = (up, low) if yong_pos == "low" else (low, up)
    te, ye = TRIGRAM_ELEM[ti], TRIGRAM_ELEM[yong]
    if te == ye:
        rel = "体用比和(顺)"
    elif _SHENG[ye] == te:
        rel = "用生体(吉)"
    elif _SHENG[te] == ye:
        rel = "体生用(耗)"
    elif _KE[ye] == te:
        rel = "用克体(凶)"
    else:
        rel = "体克用(可成但费力)"
    return {
        "rules_version": RULES_VERSION, "method": "numbers",
        "inputs": {"n1": n1, "n2": n2, "hour_branch": hour_branch},
        "ben": _hex_name(bits), "hu": _hex_name(hu), "bian": _hex_name(changed),
        "moving": moving,
        "ti": {"trigram": ti, "elem": te}, "yong": {"trigram": yong, "elem": ye},
        "relation": rel,
    }
