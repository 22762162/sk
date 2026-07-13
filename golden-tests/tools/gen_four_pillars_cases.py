#!/usr/bin/env python3
"""生成四柱黄金用例(spec v0.2 附录 B/C 覆盖)。

期望值来源纪律(golden-tests/README.md):
  - 判界与干支推导:paipan-spec v0.2 条款公式(spec-math);
  - 节气时刻:oracle-sources/solar_terms_de440s_1900_2100.jsonl(JPL 自算,经 HKO 核对);
  - 日柱抽查锚:KASI 官方接口记录值(docs/research-notes/calendar-facts-sources-2026-07-14.md),
    生成时逐例断言公式结果与 KASI 事实一致,不一致则生成失败。

本地时刻按 UTC+8(北京时间)固定偏移换算(生成器职责,引擎不做时区)。

用法(仅标准库):
    python3 gen_four_pillars_cases.py \
        --sources ../oracle-sources/solar_terms_de440s_1900_2100.jsonl --out-dir ..
产出:
    boundary/four-pillars-jie.jsonl   十二节交接三连(2026 年全部 12 节)
    fixed/four-pillars-core.jsonl     KASI 抽查锚 + 早晚子时四例
    fixed/four-pillars-err.jsonl      错误路径
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
JIE_NAMES = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
             "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]
BJT = dt.timezone(dt.timedelta(hours=8))

# KASI 抽查锚(考证记录第一节;干支为 KASI 返回的日辰)
KASI_DAY_FACTS = {(2000, 1, 1): "戊午", (1984, 2, 2): "丙寅", (2026, 7, 14): "己丑"}


def jdn(y: int, m: int, d: int) -> int:
    """spec DP-2。"""
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def pillar(stem: int, branch: int) -> dict:
    return {"stem": STEMS[stem], "branch": BRANCHES[branch],
            "ganzhi": STEMS[stem] + BRANCHES[branch]}


def four_pillars_expected(t: int, lichun: int, local: dict, ctx: dict, mode: str) -> dict:
    """spec v0.2 条款公式(YP/MP/DP/HP)的期望值推导。"""
    y = local["y"]
    bazi_year = y - 1 if t < lichun else y
    ys, yb = (bazi_year - 4) % 10, (bazi_year - 4) % 12
    ms = ((ys % 5) * 2 + 2 + ctx["jie_seq"]) % 10
    mb = (2 + ctx["jie_seq"]) % 12
    base = jdn(y, local["m"], local["d"])
    day_jdn = base + 1 if (mode == "unified" and local["hh"] >= 23) else base
    dn = (54 + (day_jdn - 2451545)) % 60
    hb = ((local["hh"] * 3600 + local["mm"] * 60 + local["ss"] + 3600) // 7200) % 12
    eff = (54 + (base + 1 - 2451545)) % 60 % 10 if (mode == "split" and local["hh"] >= 23) else dn % 10
    hs = ((eff % 5) * 2 + hb) % 10
    return {"bazi_year": bazi_year, "year": pillar(ys, yb), "month": pillar(ms, mb),
            "day": pillar(dn % 10, dn % 12), "hour": pillar(hs, hb)}


def local_of(t: int) -> dict:
    l = dt.datetime.fromtimestamp(t, BJT)
    return {"y": l.year, "m": l.month, "d": l.day, "hh": l.hour, "mm": l.minute, "ss": l.second}


def case(cid: str, t: int, lichun: int, local: dict, ctx: dict, mode: str) -> str:
    exp = four_pillars_expected(t, lichun, local, ctx, mode)
    return json.dumps({
        "case_id": cid, "op": "four_pillars",
        "input": {"t_unix": t, "lichun_unix": lichun, "local": local,
                  "month_ctx": ctx, "zi_hour_mode": mode},
        "expected": {"ok": True, "output": exp},
    }, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    jies: list[tuple[int, int]] = []  # (unix, jie_seq)
    lichun_by_year: dict[int, int] = {}
    with open(args.sources, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            if row["term"] in JIE_NAMES:
                jies.append((row["unix"], JIE_NAMES.index(row["term"])))
            if row["term"] == "立春":
                lichun_by_year[row["civil_year"]] = row["unix"]
    jies.sort()

    def bracket(t: int) -> dict:
        """找包含 t 的相邻两节窗口(MP-1 month_ctx)。"""
        import bisect
        i = bisect.bisect_right([u for u, _ in jies], t) - 1
        if i < 0 or i + 1 >= len(jies):
            raise ValueError(f"t={t} 超出节气数据覆盖范围")
        return {"jie_seq": jies[i][1], "jie_unix": jies[i][0],
                "next_jie_unix": jies[i + 1][0]}

    header_math = ("# source: spec-math(v0.2 条款公式)+ oracle-sources/"
                   "solar_terms_de440s_1900_2100.jsonl(真实节气);"
                   "generated-by: tools/gen_four_pillars_cases.py;禁止手改\n")

    # 1) 2026 年全部 12 节交接三连(前1秒/恰好/后1秒)
    lines = []
    seq = 0
    for u, s in jies:
        year = dt.datetime.fromtimestamp(u, BJT).year
        if year != 2026:
            continue
        for off in (-1, 0, 1):
            t = u + off
            local = local_of(t)
            seq += 1
            lines.append(case(f"mp-jie-{seq:04d}", t, lichun_by_year[local["y"]],
                              local, bracket(t), "split"))
    with open(f"{args.out_dir}/boundary/four-pillars-jie.jsonl", "w", encoding="utf-8") as f:
        f.write(header_math + "\n".join(lines) + "\n")
    n_jie = len(lines)

    # 2) KASI 抽查锚(正午,断言公式=KASI 事实)+ 早晚子时边界
    lines = []
    for i, ((y, m, d), fact) in enumerate(sorted(KASI_DAY_FACTS.items()), 1):
        t = int(dt.datetime(y, m, d, 12, 0, 0, tzinfo=BJT).timestamp())
        local = local_of(t)
        ctx = bracket(t)
        exp = four_pillars_expected(t, lichun_by_year[y], local, ctx, "split")
        if exp["day"]["ganzhi"] != fact:
            print(f"错误:{y}-{m}-{d} 公式日柱 {exp['day']['ganzhi']} ≠ KASI {fact}",
                  file=sys.stderr)
            return 1
        lines.append(case(f"dp-anchor-{i:04d}", t, lichun_by_year[y], local, ctx, "split"))
    zi_points = [("dp-zimode-0001", (2000, 1, 1, 23, 30, 0), "split"),
                 ("dp-zimode-0002", (2000, 1, 1, 23, 30, 0), "unified"),
                 ("dp-zimode-0003", (2000, 1, 1, 23, 0, 0), "unified"),
                 ("dp-zimode-0004", (2000, 1, 1, 22, 59, 59), "unified"),
                 ("hp-latezi-0001", (1984, 2, 2, 23, 59, 59), "split"),
                 ("hp-branch-0001", (2026, 7, 14, 1, 0, 0), "split"),
                 ("hp-branch-0002", (2026, 7, 14, 0, 59, 59), "split")]
    for cid, (y, m, d, hh, mm, ss), mode in zi_points:
        t = int(dt.datetime(y, m, d, hh, mm, ss, tzinfo=BJT).timestamp())
        local = local_of(t)
        lines.append(case(cid, t, lichun_by_year[y], local, bracket(t), mode))
    with open(f"{args.out_dir}/fixed/four-pillars-core.jsonl", "w", encoding="utf-8") as f:
        f.write("# source: spec-math + oracle-sources 节气 + KASI 日柱抽查锚(考证记录);"
                "generated-by: tools/gen_four_pillars_cases.py;禁止手改\n"
                + "\n".join(lines) + "\n")
    n_core = len(lines)

    # 3) 错误路径(期望 ok:false;只断言失败)
    t0 = int(dt.datetime(2000, 6, 1, 8, 0, 0, tzinfo=BJT).timestamp())
    ctx0 = bracket(t0)
    lc0 = lichun_by_year[2000]
    good_local = local_of(t0)
    errs = [
        {"local": {**good_local, "m": 2, "d": 30}},                      # 非法历日
        {"local": {**good_local, "hh": 24}},                             # hh 越界
        {"zi_hour_mode": "half"},                                        # 非法模式
        {"month_ctx": {**ctx0, "next_jie_unix": t0}},                    # 窗口不含 t
        {"month_ctx": {**ctx0, "jie_seq": 12}},                          # jie_seq 越界
        {"t_unix": 0.5},                                                 # 浮点混入
        {"lichun_unix": True},                                           # 布尔混入
        {"drop": "local"},                                               # 缺字段
    ]
    lines = []
    for i, patch in enumerate(errs, 1):
        inp = {"t_unix": t0, "lichun_unix": lc0, "local": dict(good_local),
               "month_ctx": dict(ctx0), "zi_hour_mode": "split"}
        if patch.get("drop"):
            inp.pop(patch["drop"])
        else:
            inp.update(patch)
        lines.append(json.dumps({"case_id": f"fp-err-{i:04d}", "op": "four_pillars",
                                 "input": inp, "expected": {"ok": False}}, ensure_ascii=False))
    with open(f"{args.out_dir}/fixed/four-pillars-err.jsonl", "w", encoding="utf-8") as f:
        f.write("# source: spec v0.2 附录 B 错误路径枚举(只断言 ok:false);"
                "generated-by: tools/gen_four_pillars_cases.py;禁止手改\n"
                + "\n".join(lines) + "\n")

    print(f"已生成:节交接 {n_jie} 例 + 核心 {n_core} 例 + 错误路径 {len(lines)} 例")
    return 0


if __name__ == "__main__":
    sys.exit(main())
