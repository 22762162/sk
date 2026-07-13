//! 年柱：八字年判定与年柱干支。规格条款：paipan-spec 第 3 节（YP-1/YP-2/YP-3）。

use crate::ganzhi::GanZhi;

/// 判定时刻所属的八字年（spec 条款 YP-1）。
///
/// * `civil_year` — 时刻 t 所在的公历年号，由调用方按其时区语境解析。
/// * `t_unix` — 时刻 t 的 Unix 秒（UTC）。
/// * `lichun_unix` — `civil_year` 年立春时刻的 Unix 秒，**由权威历源数据注入**；
///   本函数不校验该事实（无从校验），只执行判界。
///
/// 判界（闭下界，spec 1.3）：`t_unix < lichun_unix` 归上一年；
/// 恰好等于立春时刻归当年。
#[must_use]
pub fn resolve_bazi_year(civil_year: i32, t_unix: i64, lichun_unix: i64) -> i32 {
    if t_unix < lichun_unix {
        civil_year - 1
    } else {
        civil_year
    }
}

/// 八字年 → 年柱干支（spec 条款 YP-2；锚点 YP-3：1984 = 甲子）。
///
/// 使用欧几里得取模，对 `Y < 4` 亦返回非负序号（spec 附录 B）。
///
/// # Panics
/// 不会 panic：`rem_euclid(10)` / `rem_euclid(12)` 的结果必然落在 `u8` 范围内。
#[must_use]
pub fn year_ganzhi(bazi_year: i32) -> GanZhi {
    let stem = u8::try_from((bazi_year - 4).rem_euclid(10)).expect("rem_euclid(10) ∈ [0,10)");
    let branch = u8::try_from((bazi_year - 4).rem_euclid(12)).expect("rem_euclid(12) ∈ [0,12)");
    GanZhi { stem, branch }
}

/// 年柱计算结果。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct YearPillar {
    /// 判定后的八字年。
    pub bazi_year: i32,
    /// 年柱干支。
    pub ganzhi: GanZhi,
}

/// 年柱组合函数（spec 3.3）：判定八字年并推年柱干支。
#[must_use]
pub fn year_pillar(civil_year: i32, t_unix: i64, lichun_unix: i64) -> YearPillar {
    let bazi_year = resolve_bazi_year(civil_year, t_unix, lichun_unix);
    YearPillar {
        bazi_year,
        ganzhi: year_ganzhi(bazi_year),
    }
}
