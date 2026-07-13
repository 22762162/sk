#!/usr/bin/env python3
"""交叉核对:JPL 自算节气时刻 vs 香港天文台公开表(分钟级)。

HKO 页面时间为香港时间(UTC+8)、精度到分钟;自算数据精确到秒。
两来源天文数据独立(HKO 依据英国皇家航海历书局/美国海军天文台;
自算依据 JPL DE440s),分钟级吻合即为强交叉验证。

判定:|自算 − HKO 分钟值| ≤ TOLERANCE_S(默认 90 秒,覆盖 HKO
取整方式未知 [截断或四舍五入] + 自算 ±1 秒的最坏叠加)。

用法(仅标准库):
    python3 check_against_hko.py \
        --gen ../solar_terms_de440s_1900_2100.jsonl \
        --hko ../hko_solar_terms_2026_2028.jsonl
退出码:0 全部通过;1 存在超差或缺条目。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

TOLERANCE_S = 90
HKT = dt.timezone(dt.timedelta(hours=8))


def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True, help="自算节气 JSONL")
    ap.add_argument("--hko", required=True, help="HKO 对照 JSONL")
    args = ap.parse_args()

    gen = {(r["civil_year"], r["term"]): r["unix"] for r in load_jsonl(args.gen)}
    hko = load_jsonl(args.hko)

    failures = 0
    max_abs = 0
    for r in hko:
        key = (r["civil_year"], r["term"])
        hko_unix = int(
            dt.datetime.strptime(r["hkt"], "%Y-%m-%d %H:%M")
            .replace(tzinfo=HKT)
            .timestamp()
        )
        if key not in gen:
            print(f"缺条目: {key}")
            failures += 1
            continue
        diff = gen[key] - hko_unix
        max_abs = max(max_abs, abs(diff))
        if abs(diff) > TOLERANCE_S:
            print(f"超差: {key} 自算−HKO = {diff:+d} 秒")
            failures += 1

    print(f"核对 {len(hko)} 条;最大偏差 {max_abs} 秒;容差 {TOLERANCE_S} 秒;超差 {failures} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
