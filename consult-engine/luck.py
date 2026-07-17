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


# 五虎遁:流年年干 → 寅月(正月)天干
_WUHU = {"甲": "丙", "己": "丙", "乙": "戊", "庚": "戊", "丙": "庚",
         "辛": "庚", "丁": "壬", "壬": "壬", "戊": "甲", "癸": "甲"}


def liuyue_ganzhi(year_stem: str) -> list[str]:
    """某流年的十二流月干支(寅月起,五虎遁定首月天干)。"""
    first = STEMS.index(_WUHU[year_stem])
    return [STEMS[(first + k) % 10] + BRANCHES[(2 + k) % 12] for k in range(12)]


def _cycle_index(gz: str) -> int:
    s, b = STEMS.index(gz[0]), BRANCHES.index(gz[1])
    for n in range(60):
        if n % 10 == s and n % 12 == b:
            return n
    raise ValueError(f"非法干支:{gz}")


def _cycle_gz(n: int) -> str:
    n %= 60
    return STEMS[n % 10] + BRANCHES[n % 12]


def dayun(month_ganzhi: str, year_stem: str, gender: str,
          days_to_next_jie: float, days_from_prev_jie: float,
          birth_year: int, count: int = 8) -> dict:
    """大运推算(需性别)。阳年生男/阴年生女顺排,否则逆排;从月柱起、每柱十年;
    起运岁 = 到下一节(顺)/上一节(逆)的天数 ÷ 3(3 天折 1 岁,近似到岁)。

    返回 {direction, start_age, periods:[{ganzhi, start_age, end_age, start_year, end_year}]}。
    """
    yang_year = STEMS.index(year_stem) % 2 == 0  # 甲丙戊庚壬 为阳
    forward = (yang_year and gender == "male") or (not yang_year and gender == "female")
    days = days_to_next_jie if forward else days_from_prev_jie
    # 起运精到月:3 天折 1 岁 ⇒ 1 天折 4 个月(传统折算);月数向最近取整
    total_months = max(0, round(days * 4))
    start_age = total_months // 12
    start_rem_months = total_months % 12
    m = _cycle_index(month_ganzhi)
    periods = []
    for k in range(count):
        step = (k + 1) if forward else -(k + 1)
        a0 = start_age + 10 * k
        periods.append({
            "ganzhi": _cycle_gz(m + step),
            "start_age": a0, "end_age": a0 + 10,
            "start_year": birth_year + a0, "end_year": birth_year + a0 + 10,
        })
    return {"direction": "顺行" if forward else "逆行", "start_age": start_age,
            "start_months": start_rem_months,
            "start_detail": f"{start_age}岁{start_rem_months}个月" if start_rem_months else f"{start_age}岁整",
            "periods": periods}


# —— 神煞(以标准规则计算,作为具体抓手;解读由模型给出)——
_SANHE = {"申": "申子辰", "子": "申子辰", "辰": "申子辰", "寅": "寅午戌", "午": "寅午戌",
          "戌": "寅午戌", "巳": "巳酉丑", "酉": "巳酉丑", "丑": "巳酉丑",
          "亥": "亥卯未", "卯": "亥卯未", "未": "亥卯未"}
_TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "巳酉丑": "午", "亥卯未": "子"}
_YIMA = {"申子辰": "寅", "寅午戌": "申", "巳酉丑": "亥", "亥卯未": "巳"}
_HUAGAI = {"申子辰": "辰", "寅午戌": "戌", "巳酉丑": "丑", "亥卯未": "未"}
_GUIREN = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申",
           "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳", "辛": "午寅"}
_WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉", "己": "酉",
             "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}
_YANGREN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}  # 仅阳日干
_LUSHEN = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午",
           "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
_HONGLUAN = {"子": "卯", "丑": "寅", "寅": "丑", "卯": "子", "辰": "亥", "巳": "戌",
             "午": "酉", "未": "申", "申": "未", "酉": "午", "戌": "巳", "亥": "辰"}
_JIANGXING = {"申子辰": "子", "寅午戌": "午", "巳酉丑": "酉", "亥卯未": "卯"}
# 孤辰/寡宿(按年支三会方):亥子丑→孤寅寡戌;寅卯辰→孤巳寡丑;巳午未→孤申寡辰;申酉戌→孤亥寡未
_GUCHEN = {"亥": ("寅", "戌"), "子": ("寅", "戌"), "丑": ("寅", "戌"),
           "寅": ("巳", "丑"), "卯": ("巳", "丑"), "辰": ("巳", "丑"),
           "巳": ("申", "辰"), "午": ("申", "辰"), "未": ("申", "辰"),
           "申": ("亥", "未"), "酉": ("亥", "未"), "戌": ("亥", "未")}


def kongwang(day_ganzhi: str) -> str:
    """旬空(空亡):由日柱所在旬确定的两个空亡地支,如甲子旬空戌亥。"""
    idx = _cycle_index(day_ganzhi)
    start_branch = (idx - idx % 10) % 12
    return BRANCHES[(start_branch + 10) % 12] + BRANCHES[(start_branch + 11) % 12]


def shensha(day_stem: str, day_branch: str, year_branch: str, branches: list[str]) -> list[dict]:
    """列出本命带的常见神煞(触发地支出现在四柱中即计)。以日支/年支/日干起,标准规则。"""
    present = set(branches)
    found = []

    def add(name, target, note):
        if target and target in present:
            found.append({"name": name, "branch": target, "note": note})

    for ref in (day_branch, year_branch):  # 桃花/驿马/华盖:以日支或年支三合起
        grp = _SANHE.get(ref)
        if grp:
            add("桃花", _TAOHUA[grp], "人缘、异性缘、才艺")
            add("驿马", _YIMA[grp], "走动、变迁、出行")
            add("华盖", _HUAGAI[grp], "孤高、玄思、宗教艺术")
    for b in _GUIREN.get(day_stem, ""):  # 天乙贵人:以日干起
        add("天乙贵人", b, "逢凶得助、贵人扶持")
    add("文昌", _WENCHANG.get(day_stem), "利读书、文思、考试")
    add("羊刃", _YANGREN.get(day_stem), "刚烈、冲劲、双刃")
    add("禄神", _LUSHEN.get(day_stem), "本禄之地、衣食根基")
    add("红鸾", _HONGLUAN.get(year_branch), "婚恋喜庆之星")
    hl = _HONGLUAN.get(year_branch)
    if hl:  # 天喜 = 红鸾对冲之支
        add("天喜", BRANCHES[(BRANCHES.index(hl) + 6) % 12], "喜事临门、人缘和悦")
    for ref in (year_branch, day_branch):  # 将星:三合旺位,以年支或日支起
        grp = _SANHE.get(ref)
        if grp:
            add("将星", _JIANGXING[grp], "统御、担当、掌权之象")
    gc = _GUCHEN.get(year_branch)
    if gc:
        add("孤辰", gc[0], "性孤、独立,婚缘宜迟")
        add("寡宿", gc[1], "静独之星,情感易疏离")
    # 空亡:日柱旬空之支落在年/月/时支 → 标注落空
    kw = kongwang(day_stem + day_branch)
    for b in kw:
        if b in present:
            found.append({"name": "空亡", "branch": b, "note": "该支落空,力量减弱、事多虚悬"})
    # 去重(同名同支只留一条)
    uniq, seen = [], set()
    for f in found:
        key = (f["name"], f["branch"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq
