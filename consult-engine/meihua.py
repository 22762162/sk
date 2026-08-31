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
    """报数起卦:n1→上卦,n2→下卦,(n1+n2+时辰序)%6 定动爻(0 作 6)。

    纯确定性:同输入必得相同输出。报数范围上限由 App 适配层限制;
    此处只保证类型与合法域(拒绝布尔/浮点等同值异类)。
    """
    for v in (n1, n2):
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError("两数须为正整数,不接受布尔/浮点/字符串")
    if not isinstance(hour_branch, str) or hour_branch not in HOUR_INDEX:
        raise ValueError("时辰须为十二地支之一")
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
    # 事实层与解释层分离(预检第3条):relation_code 为确定性生克事实,
    # relation 为传统流派解释文案,标注 relation_kind,不作事实 Oracle
    if te == ye:
        code, rel = "bihe", "体用比和(顺)"
    elif _SHENG[ye] == te:
        code, rel = "yong_sheng_ti", "用生体(吉)"
    elif _SHENG[te] == ye:
        code, rel = "ti_sheng_yong", "体生用(耗)"
    elif _KE[ye] == te:
        code, rel = "yong_ke_ti", "用克体(凶)"
    else:
        code, rel = "ti_ke_yong", "体克用(可成但费力)"
    return {
        "rules_version": RULES_VERSION, "method": "numbers",
        "inputs": {"n1": n1, "n2": n2, "hour_branch": hour_branch},
        "ben": _hex_name(bits), "hu": _hex_name(hu), "bian": _hex_name(changed),
        "moving": moving,
        "ti": {"trigram": ti, "elem": te}, "yong": {"trigram": yong, "elem": ye},
        "relation_code": code,
        "relation": rel,
        "relation_kind": "traditional_school_reading",
    }
