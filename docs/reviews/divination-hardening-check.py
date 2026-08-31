"""Reviewer-owned before/after regression; NOT an independent divination oracle.

Run from this worktree: python3 docs/reviews/divination-hardening-check.py
Only reads this repository's pre-hardening source with git show, never reference source.
"""
from itertools import product
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
import liuyao
import meihua

# Immutable PR45 candidate commit at the start of this review, not a moving branch.
BASE = "5002b6b6466fa332446bb2dc6b27a3167b5ff0b1"


def before(name):
    code = subprocess.check_output(
        ["git", "show", f"{BASE}:consult-engine/{name}.py"], cwd=ROOT, text=True)
    module = types.ModuleType(f"before_{name}")
    exec(compile(code, f"{BASE}/{name}.py", "exec"), module.__dict__)
    return module


def main():
    old_liuyao, old_meihua = before("liuyao"), before("meihua")
    stems, branches = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
    days = [stems[i % 10] + branches[i % 12] for i in range(60)]
    count = 0
    for values in product((6, 7, 8, 9), repeat=6):
        original = list(values)
        for day_index, day in enumerate(days):
            month = branches[day_index % 12]
            expected = old_liuyao.cast(original, day, month)
            actual = liuyao.cast(original, day, month)
            if actual != expected or original != list(values):
                raise AssertionError(("liuyao valid-input regression", values, day, month))
            count += 1
    print(f"Liuyao: {count} valid-input before/after cases unchanged (4096 x 60)", flush=True)
    count = 0
    for n1, n2, hour in product(range(1, 49), range(1, 49), branches):
        expected = old_meihua.cast_numbers(n1, n2, hour)
        actual = meihua.cast_numbers(n1, n2, hour)
        # Two explicitly documented additive metadata fields; historical output is unchanged.
        metadata = {k: actual.pop(k) for k in ("relation_code", "relation_kind")}
        codes = {"体用比和": "bihe", "用生体": "yong_sheng_ti", "体生用": "ti_sheng_yong",
                 "用克体": "yong_ke_ti", "体克用": "ti_ke_yong"}
        expected_code = codes[expected["relation"].split("(")[0]]
        if (actual != expected or metadata["relation_kind"] != "traditional_school_reading"
                or metadata["relation_code"] != expected_code):
            raise AssertionError(("meihua valid-input regression", n1, n2, hour))
        count += 1
    print(f"Meihua: {count} valid-input cases unchanged except documented metadata", flush=True)
    print("Engineering regression only; no independent oracle or predictive-accuracy claim.")


if __name__ == "__main__":
    main()
