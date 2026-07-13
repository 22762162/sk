#!/usr/bin/env python3
"""由 JPL 星历自算 1900–2100 年二十四节气时刻(定气法)。

历源候选方案之三「HORIZONS/VSOP87 自算校验」的实现(见 golden-tests/README.md)。
本脚本产出 oracle-sources/ 下的权威历源数据文件;它本身不属于排盘引擎,
不受 engine-paipan「仅注入数据」红线约束,但所有天文事实均来自:

  - 星历: JPL DE440s(ephemeris/de440s.bsp,NAIF 官方分发,公有领域)
  - 岁差/章动/光行差模型: Skyfield(MIT 许可)所实现的 IAU 标准模型
  - ΔT(TT−UT1): Skyfield 内置时标数据(IERS 观测 + 长期模型外推;
    未来年份为预测值,与各天文年历的处理一致)

定气法定义(GB/T 33661-2017;香港天文台「二十四节气」页同):
太阳视黄经(真春分点岁差章动坐标系,含光行差)每达 15° 整倍数为一个节气。
λ=315° 为立春。本映射为定义性事实,非模型记忆的历法数值。

运行(需网络下载依赖,星历文件须已就位):
    uv run --with skyfield python3 gen_solar_terms.py \
        --bsp ../oracle-sources/ephemeris/de440s.bsp --start 1900 --end 2100 \
        --out ../oracle-sources/solar_terms_de440s_1900_2100.jsonl

输出 JSONL 逐行:
    {"term":"立春","lambda_deg":315,"civil_year":1984,
     "unix":444727140,"utc":"1984-02-04T15:19:00Z",
     "beijing":"1984-02-04 23:19:00 +08:00"}
unix 为四舍五入到秒的 Unix 秒(UTC);civil_year 为北京时间(UTC+8)所在公历年。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from skyfield.api import load
from skyfield.framelib import ecliptic_frame
from skyfield.searchlib import find_discrete

# λ = 15°×k 的节气名,k = 0..23(0°=春分 … 315°=立春 … 345°=惊蛰)。
TERM_BY_SECTOR = [
    "春分", "清明", "谷雨", "立夏", "小满", "芒种",
    "夏至", "小暑", "大暑", "立秋", "处暑", "白露",
    "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
    "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
]

BEIJING = dt.timezone(dt.timedelta(hours=8))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bsp", required=True, help="JPL 星历文件路径(de440s.bsp)")
    ap.add_argument("--start", type=int, default=1900, help="起始公历年(含)")
    ap.add_argument("--end", type=int, default=2100, help="结束公历年(含)")
    ap.add_argument("--out", required=True, help="输出 JSONL 路径")
    args = ap.parse_args()

    ts = load.timescale()  # 内置 ΔT/闰秒数据,无需联网
    eph = load(args.bsp)
    earth, sun = eph["earth"], eph["sun"]

    def sector(t):
        lon = earth.at(t).observe(sun).apparent().frame_latlon(ecliptic_frame)[1]
        return (lon.degrees % 360.0) // 15.0

    sector.step_days = 5.0  # 相邻节气间隔约 15 天,5 天步长不会漏跳变

    # 前后各留 5 天余量,保证首尾年份的小寒/大寒不因区间截断而丢失
    t0 = ts.utc(args.start, 1, 1) - 5.0
    t1 = ts.utc(args.end + 1, 1, 1) + 5.0
    # epsilon 单位为天;1e-7 天 ≈ 0.009 秒,满足 ±1 秒精度要求
    times, sectors = find_discrete(t0, t1, sector, epsilon=1e-7)

    rows = []
    for t, k in zip(times, sectors):
        # find_discrete 返回跳变后的取值;跳变时刻即太阳视黄经恰达 15°×k
        term = TERM_BY_SECTOR[int(k)]
        utc = t.utc_datetime()
        unix = round(utc.timestamp())
        utc_rounded = dt.datetime.fromtimestamp(unix, dt.timezone.utc)
        beijing = utc_rounded.astimezone(BEIJING)
        if not (args.start <= beijing.year <= args.end):
            continue
        rows.append(
            {
                "term": term,
                "lambda_deg": int(k) * 15,
                "civil_year": beijing.year,
                "unix": unix,
                "utc": utc_rounded.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "beijing": beijing.strftime("%Y-%m-%d %H:%M:%S +08:00"),
            }
        )

    expected = (args.end - args.start + 1) * 24
    if len(rows) != expected:
        print(f"错误:期望 {expected} 条节气记录,实际 {len(rows)} 条", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(
            "# source: JPL DE440s (NAIF 官方) + Skyfield 定气自算;"
            "生成脚本 tools/gen_solar_terms.py;禁止手改本文件\n"
        )
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"已生成 {len(rows)} 条节气记录 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
