#!/usr/bin/env python3
"""由真实立春时刻生成年柱黄金用例(立春前 1 秒 / 恰好 / 后 1 秒)。

期望值来源(黄金集数据来源纪律,见 golden-tests/README.md):
  - 判界与干支:paipan-spec 条款 YP-1/YP-2/YP-3 的数学定义(spec-math);
  - 立春时刻:oracle-sources/solar_terms_de440s_1900_2100.jsonl(JPL 自算,
    经 HKO 分钟级交叉核对),非模型记忆。

用法(仅标准库):
    python3 gen_year_pillar_cases.py \
        --sources ../oracle-sources/solar_terms_de440s_1900_2100.jsonl \
        --out ../boundary/year-pillar-lichun.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

# spec 2.1 / 2.2 的序号表(定义性事实)
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 覆盖:范围端点、锚点 1984、60 年回环(1924)、负时间戳年代、近未来
YEARS = [1900, 1924, 1949, 1984, 2000, 2026, 2044, 2100]

HEADER = (
    "# source: spec-math(YP-1/YP-2/YP-3 公式推期望值)+ "
    "oracle-sources/solar_terms_de440s_1900_2100.jsonl(真实立春时刻,JPL 自算、经 HKO 交叉核对)\n"
    "# generated-by: tools/gen_year_pillar_cases.py;禁止手改本文件\n"
)


def year_ganzhi(y: int) -> tuple[str, str]:
    """spec 条款 YP-2:s=(Y−4) mod 10,b=(Y−4) mod 12(欧几里得取模)。"""
    return STEMS[(y - 4) % 10], BRANCHES[(y - 4) % 12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    lichun: dict[int, int] = {}
    with open(args.sources, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            if row["term"] == "立春":
                lichun[row["civil_year"]] = row["unix"]

    missing = [y for y in YEARS if y not in lichun]
    if missing:
        print(f"错误:sources 缺少年份 {missing} 的立春", file=sys.stderr)
        return 1

    lines = []
    seq = 0
    for year in YEARS:
        lc = lichun[year]
        # (偏移, 归属八字年):YP-1 闭下界 —— 恰好立春归当年
        for offset, bazi_year in [(-1, year - 1), (0, year), (1, year)]:
            seq += 1
            stem, branch = year_ganzhi(bazi_year)
            case = {
                "case_id": f"yp-lichun-{seq:04d}",
                "op": "year_pillar",
                "input": {"civil_year": year, "t_unix": lc + offset, "lichun_unix": lc},
                "expected": {
                    "ok": True,
                    "output": {
                        "bazi_year": bazi_year,
                        "stem": stem,
                        "branch": branch,
                        "ganzhi": stem + branch,
                    },
                },
            }
            lines.append(json.dumps(case, ensure_ascii=False))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write("\n".join(lines) + "\n")

    print(f"已生成 {len(lines)} 例 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
