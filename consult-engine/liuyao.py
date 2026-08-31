"""六爻装卦引擎(确定性;规格 docs/specs/liuyao-meihua-v1.md;rules: liuyao-rules-v1)。

铁律:代码装卦,AI 只解卦。八宫由纯卦程序生成(变初→…→游魂→归魂),
自检对已知卦名/宫/世断言双重校验,不手抄六十四行表。
"""

from __future__ import annotations

import secrets

from luck import BRANCH_ELEM, kongwang

RULES_VERSION = "liuyao-rules-v1"

# 三爻卦:自下而上的阴阳位(1=阳),先天数序 乾1兑2离3震4巽5坎6艮7坤8
TRIGRAMS = {
    "乾": (1, 1, 1), "兑": (1, 1, 0), "离": (1, 0, 1), "震": (1, 0, 0),
    "巽": (0, 1, 1), "坎": (0, 1, 0), "艮": (0, 0, 1), "坤": (0, 0, 0),
}
TRIGRAM_BY_BITS = {v: k for k, v in TRIGRAMS.items()}
XIANTIAN_ORDER = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]  # 先天数 1..8
TRIGRAM_NATURE = {"乾": "天", "兑": "泽", "离": "火", "震": "雷",
                  "巽": "风", "坎": "水", "艮": "山", "坤": "地"}
TRIGRAM_ELEM = {"乾": "金", "兑": "金", "离": "火", "震": "木",
                "巽": "木", "坎": "水", "艮": "土", "坤": "土"}

# 六十四卦名:(上卦,下卦) → 名
HEX_NAMES = {}
_ROWS = {
    "乾": ["乾为天", "天泽履", "天火同人", "天雷无妄", "天风姤", "天水讼", "天山遁", "天地否"],
    "兑": ["泽天夬", "兑为泽", "泽火革", "泽雷随", "泽风大过", "泽水困", "泽山咸", "泽地萃"],
    "离": ["火天大有", "火泽睽", "离为火", "火雷噬嗑", "火风鼎", "火水未济", "火山旅", "火地晋"],
    "震": ["雷天大壮", "雷泽归妹", "雷火丰", "震为雷", "雷风恒", "雷水解", "雷山小过", "雷地豫"],
    "巽": ["风天小畜", "风泽中孚", "风火家人", "风雷益", "巽为风", "风水涣", "风山渐", "风地观"],
    "坎": ["水天需", "水泽节", "水火既济", "水雷屯", "水风井", "坎为水", "水山蹇", "水地比"],
    "艮": ["山天大畜", "山泽损", "山火贲", "山雷颐", "山风蛊", "山水蒙", "艮为山", "山地剥"],
    "坤": ["地天泰", "地泽临", "地火明夷", "地雷复", "地风升", "地水师", "地山谦", "坤为地"],
}
for _up, _names in _ROWS.items():
    for _i, _low in enumerate(XIANTIAN_ORDER):
        HEX_NAMES[(_up, _low)] = _names[_i]

# 纳甲:各卦 内卦(初二三)/外卦(四五上) 的天干与三支
NAJIA = {
    "乾": {"inner": ("甲", ["子", "寅", "辰"]), "outer": ("壬", ["午", "申", "戌"])},
    "坎": {"inner": ("戊", ["寅", "辰", "午"]), "outer": ("戊", ["申", "戌", "子"])},
    "艮": {"inner": ("丙", ["辰", "午", "申"]), "outer": ("丙", ["戌", "子", "寅"])},
    "震": {"inner": ("庚", ["子", "寅", "辰"]), "outer": ("庚", ["午", "申", "戌"])},
    "巽": {"inner": ("辛", ["丑", "亥", "酉"]), "outer": ("辛", ["未", "巳", "卯"])},
    "离": {"inner": ("己", ["卯", "丑", "亥"]), "outer": ("己", ["酉", "未", "巳"])},
    "坤": {"inner": ("乙", ["未", "巳", "卯"]), "outer": ("癸", ["丑", "亥", "酉"])},
    "兑": {"inner": ("丁", ["巳", "卯", "丑"]), "outer": ("丁", ["亥", "酉", "未"])},
}

_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
LIUSHEN_START = {"甲": 0, "乙": 0, "丙": 1, "丁": 1, "戊": 2,
                 "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}
LIUSHEN = ["青龙", "朱雀", "勾陈", "腾蛇", "白虎", "玄武"]

# 八宫世应:宫内序(0=本宫纯卦..7=归魂) → 世爻位;应=世隔三位
SHI_POS = [6, 1, 2, 3, 4, 5, 4, 3]
# 宫内序 → 相对纯卦翻转的爻位集合(变初→…→游魂{1,2,3,5}→归魂{5})
_FLIPS = [set(), {1}, {1, 2}, {1, 2, 3}, {1, 2, 3, 4}, {1, 2, 3, 4, 5}, {1, 2, 3, 5}, {5}]


def _hex_name(bits: tuple) -> str:
    low = TRIGRAM_BY_BITS[bits[0:3]]
    up = TRIGRAM_BY_BITS[bits[3:6]]
    return HEX_NAMES[(up, low)]


def build_palaces() -> dict:
    """程序生成八宫六十四卦:卦名 → {palace, index, shi, ying}。"""
    out = {}
    for pure in XIANTIAN_ORDER:
        base = TRIGRAMS[pure] * 2
        for idx, flips in enumerate(_FLIPS):
            bits = tuple(b ^ (1 if (i + 1) in flips else 0) for i, b in enumerate(base))
            shi = SHI_POS[idx]
            out[_hex_name(bits)] = {"palace": pure, "palace_elem": TRIGRAM_ELEM[pure],
                                    "index": idx, "shi": shi, "ying": ((shi - 1 + 3) % 6) + 1}
    return out


PALACES = build_palaces()


def _liuqin(palace_elem: str, branch: str) -> str:
    e = BRANCH_ELEM[branch]
    if e == palace_elem:
        return "兄弟"
    if _SHENG[e] == palace_elem:
        return "父母"
    if _SHENG[palace_elem] == e:
        return "子孙"
    if _KE[e] == palace_elem:
        return "官鬼"
    return "妻财"


def _branches_of(bits: tuple) -> list[str]:
    low = TRIGRAM_BY_BITS[bits[0:3]]
    up = TRIGRAM_BY_BITS[bits[3:6]]
    return NAJIA[low]["inner"][1] + NAJIA[up]["outer"][1]


def system_cast() -> list[int]:
    """电子摇卦:三枚硬币×六次(背3字2),密码学随机,逐爻记录。"""
    return [sum(3 if secrets.randbelow(2) else 2 for _ in range(3)) for _ in range(6)]


def cast(lines: list[int], day_ganzhi: str, month_branch: str) -> dict:
    """装卦。lines 为初爻→上爻的 6/7/8/9;day_ganzhi 装六神与旬空;month_branch 为月建。"""
    if len(lines) != 6 or any(v not in (6, 7, 8, 9) for v in lines):
        raise ValueError("lines 须为 6 个 6/7/8/9(初爻在前)")
    bits = tuple(1 if v in (7, 9) else 0 for v in lines)
    moving = [i + 1 for i, v in enumerate(lines) if v in (6, 9)]
    changed = tuple(b ^ (1 if (i + 1) in moving else 0) for i, b in enumerate(bits))
    name = _hex_name(bits)
    info = PALACES[name]
    branches = _branches_of(bits)
    ch_branches = _branches_of(changed)
    kw = kongwang(day_ganzhi)
    start = LIUSHEN_START[day_ganzhi[0]]
    yao = []
    for i in range(6):
        yao.append({
            "pos": i + 1, "yang": bool(bits[i]), "moving": (i + 1) in moving,
            "branch": branches[i], "elem": BRANCH_ELEM[branches[i]],
            "liuqin": _liuqin(info["palace_elem"], branches[i]),
            "liushen": LIUSHEN[(start + i) % 6],
            "kong": branches[i] in kw,
            "shi": (i + 1) == info["shi"], "ying": (i + 1) == info["ying"],
            "change_branch": ch_branches[i] if (i + 1) in moving else None,
        })
    return {
        "rules_version": RULES_VERSION,
        "ben": {"name": name, "palace": info["palace"], "palace_elem": info["palace_elem"],
                "shi": info["shi"], "ying": info["ying"]},
        "bian": {"name": _hex_name(changed)} if moving else None,
        "moving": moving, "yao": yao,
        "day_ganzhi": day_ganzhi, "month_branch": month_branch, "kongwang": kw,
    }
