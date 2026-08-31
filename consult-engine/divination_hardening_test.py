"""六爻/梅花工程加固测试(PR-45 预检第 1/2/4 条):
4096 组爻值穷举、六十日干支全覆盖、非法输入矩阵、同输入重放一致性。
运行:python3 consult-engine/divination_hardening_test.py(pytest 亦可发现)。
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import divination_casting  # noqa: E402
import liuyao  # noqa: E402
import luck  # noqa: E402
import meihua  # noqa: E402


def test_liuyao_exhaustive_4096() -> None:
    """全部 4^6=4096 组爻值:结构不变量逐组断言;64 本卦全部现身。"""
    seen_ben = set()
    for lines in itertools.product((6, 7, 8, 9), repeat=6):
        r = liuyao.cast(list(lines), "甲子", "寅")
        info = liuyao.PALACES[r["ben"]["name"]]
        assert (r["ben"]["palace"], r["ben"]["shi"]) == (info["palace"], info["shi"])
        expect_moving = [i + 1 for i, v in enumerate(lines) if v in (6, 9)]
        assert r["moving"] == expect_moving
        assert (r["bian"] is not None) == bool(expect_moving)
        assert len(r["yao"]) == 6
        shi_flags = [y["shi"] for y in r["yao"]]
        ying_flags = [y["ying"] for y in r["yao"]]
        assert shi_flags.count(True) == 1 and ying_flags.count(True) == 1
        for i, y in enumerate(r["yao"]):
            assert y["pos"] == i + 1
            assert y["branch"] in luck.BRANCHES and y["elem"] == luck.BRANCH_ELEM[y["branch"]]
            assert y["liuqin"] in {"兄弟", "父母", "子孙", "官鬼", "妻财"}
            assert y["liushen"] in liuyao.LIUSHEN
            assert y["yang"] == (lines[i] in (7, 9))
            assert y["moving"] == (lines[i] in (6, 9))
            assert (y["change_branch"] is not None) == y["moving"]
            assert y["kong"] == (y["branch"] in "戌亥")  # 甲子日旬空戌亥
        if r["bian"]:
            assert r["bian"]["name"] in liuyao.PALACES
        seen_ben.add(r["ben"]["name"])
    assert len(seen_ben) == 64, f"应覆盖 64 卦,得 {len(seen_ben)}"


def test_liuyao_all_sixty_days() -> None:
    """六十甲子日全覆盖:六神起法与旬空逐日校验。"""
    days = sorted(liuyao.JIAZI)
    assert len(days) == 60
    for day in days:
        r = liuyao.cast([7, 8, 7, 8, 7, 8], day, "午")
        start = liuyao.LIUSHEN_START[day[0]]
        assert [y["liushen"] for y in r["yao"]] == [
            liuyao.LIUSHEN[(start + i) % 6] for i in range(6)]
        assert r["kongwang"] == luck.kongwang(day)


def test_liuyao_replay_deterministic() -> None:
    """同输入重放:两次装卦逐字段一致(含 JSON 序列化字节级)。"""
    for lines in ([9, 6, 7, 8, 9, 6], [7] * 6, [6] * 6):
        a = liuyao.cast(list(lines), "癸亥", "子")
        b = liuyao.cast(list(lines), "癸亥", "子")
        assert a == b
        assert json.dumps(a, ensure_ascii=False, sort_keys=True) == \
               json.dumps(b, ensure_ascii=False, sort_keys=True)


def _rejects(fn, *args) -> bool:
    try:
        fn(*args)
        return False
    except ValueError:
        return True
    except Exception:
        return False  # 只允许受控的 ValueError,其余异常视为未通过


def test_liuyao_rejects_illegal_inputs() -> None:
    ok = [7, 8, 7, 8, 7, 8]
    cases = [
        ([6.0, 7, 8, 9, 7, 8], "甲子", "寅"),   # 浮点同值异类
        ([True, 7, 8, 9, 7, 8], "甲子", "寅"),  # bool 是 int 子类
        (["7", 7, 8, 9, 7, 8], "甲子", "寅"),
        ([7, 8, 7, 8, 7], "甲子", "寅"),        # 5 爻
        ([7, 8, 7, 8, 7, 8, 7], "甲子", "寅"),  # 7 爻
        ([5, 7, 8, 9, 7, 8], "甲子", "寅"),     # 越域
        (ok, "甲丑", "寅"),                     # 干支不成对(非六十甲子)
        (ok, "子甲", "寅"),
        (ok, "", "寅"),
        (ok, None, "寅"),
        (ok, "甲子", "天"),                     # 非地支月建
        (ok, "甲子", ""),
        (ok, "甲子", None),
    ]
    for args in cases:
        assert _rejects(liuyao.cast, *args), f"未拒绝:{args}"


def test_meihua_rejects_illegal_inputs() -> None:
    cases = [(True, 5, "午"), (3, False, "午"), (0, 5, "午"), (-1, 5, "午"),
             (3.0, 5, "午"), (3, 5.5, "午"), ("3", 5, "午"),
             (3, 5, "天"), (3, 5, ""), (3, 5, None), (3, 5, 7)]
    for args in cases:
        assert _rejects(meihua.cast_numbers, *args), f"未拒绝:{args}"


def test_meihua_boundaries_and_replay() -> None:
    # 余 0 作 8/作 6 的边界:8/16/24 → 坤;和+时辰整除 6 → 上爻动
    r = meihua.cast_numbers(8, 16, "子")   # 动=(8+16+1)%6=1
    assert r["ben"] == "坤为地" and r["moving"] == 1
    r2 = meihua.cast_numbers(1, 2, "卯")   # 动=(1+2+4)%6=1
    assert r2["moving"] == 1
    r3 = meihua.cast_numbers(2, 2, "寅")   # 动=(2+2+3)%6=1
    assert r3["moving"] == 1
    r4 = meihua.cast_numbers(3, 3, "子")   # 动=(3+3+1)%6=1
    assert r4["moving"] == 1
    r5 = meihua.cast_numbers(5, 6, "子")   # 动=(5+6+1)%6=0→6 上爻动:用=上卦巽,体=下卦坎
    assert r5["moving"] == 6 and r5["yong"]["trigram"] == "巽" and r5["ti"]["trigram"] == "坎"
    big = meihua.cast_numbers(987654321, 123456789, "亥")  # 大整数不炸,可重放
    assert big == meihua.cast_numbers(987654321, 123456789, "亥")
    # 事实/解释分层字段
    assert big["relation_code"] in {"bihe", "yong_sheng_ti", "ti_sheng_yong", "yong_ke_ti", "ti_ke_yong"}
    assert big["relation_kind"] == "traditional_school_reading"
    # 全时辰×全余数组合的轻量穷举:输出结构合法
    for hb in "子丑寅卯辰巳午未申酉戌亥":
        for n1 in range(1, 9):
            for n2 in range(1, 9):
                r = meihua.cast_numbers(n1, n2, hb)
                assert r["ben"] in liuyao.PALACES and r["hu"] in liuyao.PALACES \
                    and r["bian"] in liuyao.PALACES and 1 <= r["moving"] <= 6


def test_adapter_boundary() -> None:
    """随机只在适配层;引擎模块不得含 secrets/随机依赖。"""
    import importlib
    src = (Path(__file__).parent / "liuyao.py").read_text(encoding="utf-8")
    assert "secrets" not in src and "random" not in src
    src2 = (Path(__file__).parent / "meihua.py").read_text(encoding="utf-8")
    assert "secrets" not in src2 and "random" not in src2
    rec = divination_casting.system_cast_liuyao()
    r = liuyao.cast(rec["lines"], "甲子", "寅")  # 适配层输出可直接喂引擎
    assert r["ben"]["name"] in liuyao.PALACES
    assert importlib.import_module("divination_casting").manual_cast_liuyao([7] * 6)["method"] == "manual_coins"


if __name__ == "__main__":
    test_liuyao_exhaustive_4096()
    test_liuyao_all_sixty_days()
    test_liuyao_replay_deterministic()
    test_liuyao_rejects_illegal_inputs()
    test_meihua_rejects_illegal_inputs()
    test_meihua_boundaries_and_replay()
    test_adapter_boundary()
    print("加固测试全部通过 ✓(4096 爻值穷举 + 六十日干支 + 非法输入矩阵 + 重放一致 + 适配层边界)")
