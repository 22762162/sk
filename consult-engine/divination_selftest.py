"""六爻/梅花装卦自检(黄金用例;CI 与本地均可跑:python3 divination_selftest.py)。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import liuyao  # noqa: E402
import meihua  # noqa: E402


def test_palaces() -> None:
    p = liuyao.PALACES
    assert len(p) == 64, f"八宫应生成 64 卦,得 {len(p)}"
    # 已知样本:宫、宫内序、世爻位(京房八宫经典结论)
    for name, palace, idx, shi in [
        ("乾为天", "乾", 0, 6), ("天风姤", "乾", 1, 1), ("火地晋", "乾", 6, 4),
        ("火天大有", "乾", 7, 3), ("水泽节", "坎", 1, 1), ("泽火革", "坎", 4, 4),
        ("地火明夷", "坎", 6, 4), ("地水师", "坎", 7, 3), ("雷泽归妹", "兑", 7, 3),
        ("天火同人", "离", 7, 3), ("水天需", "坤", 6, 4), ("水地比", "坤", 7, 3),
        ("山雷颐", "巽", 6, 4), ("泽风大过", "震", 6, 4), ("风泽中孚", "艮", 6, 4),
    ]:
        got = p[name]
        assert (got["palace"], got["index"], got["shi"]) == (palace, idx, shi), \
            f"{name}: 期望 {palace}/{idx}/世{shi},得 {got}"
    # 世应隔三位关系全量校验
    for name, info in p.items():
        assert info["ying"] == ((info["shi"] - 1 + 3) % 6) + 1, name


def test_qian_cast() -> None:
    """全老阳:乾为天,六爻皆动变坤;纳支/六亲/六神/旬空黄金断言。"""
    r = liuyao.cast([9] * 6, "甲子", "午")
    assert r["ben"]["name"] == "乾为天" and r["bian"]["name"] == "坤为地"
    assert r["ben"]["shi"] == 6 and r["ben"]["ying"] == 3
    assert [y["branch"] for y in r["yao"]] == ["子", "寅", "辰", "午", "申", "戌"]
    assert [y["liuqin"] for y in r["yao"]] == ["子孙", "妻财", "父母", "官鬼", "兄弟", "父母"]
    assert [y["liushen"] for y in r["yao"]] == ["青龙", "朱雀", "勾陈", "腾蛇", "白虎", "玄武"]
    assert r["kongwang"] == "戌亥" and r["yao"][5]["kong"] is True  # 甲子旬空戌亥,上爻戌落空
    assert [y["change_branch"] for y in r["yao"]] == ["未", "巳", "卯", "丑", "亥", "酉"]  # 变坤纳支


def test_jing_cast() -> None:
    """静卦+部分动:水火既济(坎宫三世),仅二爻动;六神起于丙(朱雀)。"""
    # 既济 bits: 下离(1,0,1) 上坎(0,1,0) → lines 阳阴阳 阴阳阴;二爻动=老阴6
    r = liuyao.cast([7, 6, 7, 8, 7, 8], "丙寅", "子")
    assert r["ben"]["name"] == "水火既济" and r["ben"]["palace"] == "坎" and r["ben"]["shi"] == 3
    assert r["moving"] == [2] and r["bian"]["name"] == "水天需"  # 二爻阴动变阳:下卦离→乾
    assert r["yao"][0]["liushen"] == "朱雀"  # 丙丁起朱雀
    assert r["yao"][1]["change_branch"] is not None and r["yao"][0]["change_branch"] is None


def test_meihua() -> None:
    r = meihua.cast_numbers(3, 5, "午")
    assert r["ben"].startswith("火风")  # 上离3下巽5 → 火风鼎
    assert r["moving"] == (3 + 5 + 7) % 6  # =3,动在下卦
    assert r["yong"]["trigram"] == "巽" and r["ti"]["trigram"] == "离"
    assert r["relation"] == "用生体(吉)"  # 巽木生离火
    r2 = meihua.cast_numbers(8, 6, "丑")  # 余0作8:上坤;动=(8+6+2)%6=4 → 上卦为用
    assert r2["ben"] == "地水师" and r2["moving"] == 4 and r2["yong"]["trigram"] == "坤"
    e = meihua.cast_numbers(1, 1, "子")
    assert e["ben"] == "乾为天" and e["moving"] == 3


def test_system_cast_shape() -> None:
    import divination_casting  # 随机性住在适配层(INV-01),引擎侧无 secrets
    for _ in range(50):
        rec = divination_casting.system_cast_liuyao()
        assert rec["method"] == "system_random"
        assert len(rec["lines"]) == 6 and all(v in (6, 7, 8, 9) for v in rec["lines"])
    assert not hasattr(liuyao, "system_cast") and not hasattr(liuyao, "secrets")


if __name__ == "__main__":
    test_palaces()
    test_qian_cast()
    test_jing_cast()
    test_meihua()
    test_system_cast_shape()
    print("六爻/梅花装卦自检:全部通过 ✓(八宫64卦生成校验+黄金用例)")
