"""流年(及后续大运)推算(DESIGN §11 落地态:年度分析素材)。

流年干支:六十甲子循环,锚定 1984 = 甲子(公历年,以立春为界的八字年;此处按公历年标注,
交节细节由呈现层说明,不做逐日精推)。纯标准库、确定性。

注:大运需性别 + 起运节气距,属后续增量;本模块先提供流年,供会诊做逐年分析。
"""

from __future__ import annotations

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_ANCHOR = 1984  # 1984 = 甲子年


def year_ganzhi(year: int) -> str:
    i = year - _ANCHOR
    return STEMS[i % 10] + BRANCHES[i % 12]


def liunian(start_year: int, n: int = 8) -> list[dict]:
    """未来 n 年流年:[{year, ganzhi, stem, branch}]。"""
    out = []
    for y in range(start_year, start_year + n):
        gz = year_ganzhi(y)
        out.append({"year": y, "ganzhi": gz, "stem": gz[0], "branch": gz[1]})
    return out
