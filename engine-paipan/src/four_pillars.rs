//! 四柱：月柱/日柱/时柱与组合。规格条款：paipan-spec v0.2 第 4 章
//! （LT-1、MP-1/2、DP-1/2/3/4、HP-1/2、four_pillars）。

use crate::ganzhi::GanZhi;
use crate::year_pillar::{resolve_bazi_year, year_ganzhi};

/// 本地民用时刻（spec LT-1）：由调用方按其时区语境解析注入，引擎不做时区换算。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LocalTime {
    /// 公历年（天文年号，`y ≥ 1`）。
    pub y: i32,
    /// 月 1–12。
    pub m: u8,
    /// 日 1–31（按历月合法性校验）。
    pub d: u8,
    /// 时 0–23。
    pub hh: u8,
    /// 分 0–59。
    pub mm: u8,
    /// 秒 0–59。
    pub ss: u8,
}

impl LocalTime {
    /// LT-1 合法性校验：格里历日期时间。
    #[must_use]
    pub fn is_valid(self) -> bool {
        self.y >= 1
            && (1..=12).contains(&self.m)
            && self.d >= 1
            && self.d <= days_in_month(self.y, self.m)
            && self.hh < 24
            && self.mm < 60
            && self.ss < 60
    }
}

/// 格里历某月天数（纯数学，服务 LT-1 校验）。
#[must_use]
pub fn days_in_month(y: i32, m: u8) -> u8 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if (y % 4 == 0 && y % 100 != 0) || y % 400 == 0 {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

/// 节气月上下文（spec MP-1）：由权威历源注入，引擎只执行判界。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MonthCtx {
    /// 节序号 0–11（0=立春 … 11=小寒）。
    pub jie_seq: u8,
    /// 该节交节时刻（Unix 秒）。
    pub jie_unix: i64,
    /// 下一节交节时刻（Unix 秒）。
    pub next_jie_unix: i64,
}

/// 早晚子时流派配置（spec DP-4；真实流派分歧转配置项，不裁对错）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ZiHourMode {
    /// 早晚子时：日柱按当地 00:00 换日；23 点起的时干用次日日干起遁。
    Split,
    /// 子时换日：23:00 起日柱、时柱一并记入次日。
    Unified,
}

/// 四柱结果。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FourPillars {
    /// YP-1 判定的八字年。
    pub bazi_year: i32,
    /// 年柱。
    pub year: GanZhi,
    /// 月柱。
    pub month: GanZhi,
    /// 日柱。
    pub day: GanZhi,
    /// 时柱。
    pub hour: GanZhi,
}

/// 格里历儒略日数（spec DP-2；纯整数运算，对 `y ≥ 1` 成立）。
#[must_use]
pub fn jdn(y: i32, m: u8, d: u8) -> i64 {
    let (y, m, d) = (i64::from(y), i64::from(m), i64::from(d));
    let a = (14 - m).div_euclid(12);
    let y2 = y + 4800 - a;
    let m2 = m + 12 * a - 3;
    d + (153 * m2 + 2).div_euclid(5) + 365 * y2 + y2.div_euclid(4) - y2.div_euclid(100)
        + y2.div_euclid(400)
        - 32045
}

/// 日干支序（spec DP-1/DP-3）：锚点 JDN 2451545 = 戊午（序 54）。
///
/// # Panics
/// 不会 panic：`rem_euclid(60)` 结果必然落在 `u8` 范围内。
#[must_use]
pub fn day_ganzhi_index(jdn: i64) -> u8 {
    u8::try_from((54 + (jdn - 2_451_545)).rem_euclid(60)).expect("rem_euclid(60) ∈ [0,60)")
}

fn ganzhi_from_index(n: u8) -> GanZhi {
    GanZhi {
        stem: n % 10,
        branch: n % 12,
    }
}

/// 四柱组合（spec 4.4）。校验失败返回 `Err(错误说明)`。
///
/// # Errors
/// LT-1 非法 local、MP-1 窗口不含 t 或 `jie_seq` 越界时返回错误。
///
/// # Panics
/// 不会 panic：时支序计算 `(..) % 12` 必然落在 `u8` 范围内。
pub fn four_pillars(
    t_unix: i64,
    lichun_unix: i64,
    local: LocalTime,
    month_ctx: MonthCtx,
    mode: ZiHourMode,
) -> Result<FourPillars, String> {
    if !local.is_valid() {
        return Err("invalid local civil time (LT-1)".to_string());
    }
    if month_ctx.jie_seq > 11 {
        return Err("jie_seq out of range (MP-1)".to_string());
    }
    if !(month_ctx.jie_unix <= t_unix && t_unix < month_ctx.next_jie_unix) {
        return Err("t_unix outside month_ctx window (MP-1)".to_string());
    }

    // 年柱（YP-1/YP-2；civil_year := local.y，spec 4.4）
    let bazi_year = resolve_bazi_year(local.y, t_unix, lichun_unix);
    let year = year_ganzhi(bazi_year);

    // 月柱（MP-1/MP-2 五虎遁）
    let month = GanZhi {
        stem: ((year.stem % 5) * 2 + 2 + month_ctx.jie_seq) % 10,
        branch: (2 + month_ctx.jie_seq) % 12,
    };

    // 日柱（DP-2/DP-3/DP-4）
    let base_jdn = jdn(local.y, local.m, local.d);
    let day_jdn = match mode {
        ZiHourMode::Unified if local.hh >= 23 => base_jdn + 1,
        _ => base_jdn,
    };
    let day = ganzhi_from_index(day_ganzhi_index(day_jdn));

    // 时柱（HP-1/HP-2 五鼠遁；split 模式晚子时用次日日干起遁）
    let secs = i64::from(local.hh) * 3600 + i64::from(local.mm) * 60 + i64::from(local.ss);
    let hour_branch = u8::try_from(((secs + 3600) / 7200) % 12).expect("(..)%12 ∈ [0,12)");
    let effective_day_stem = match mode {
        ZiHourMode::Split if local.hh >= 23 => day_ganzhi_index(base_jdn + 1) % 10,
        _ => day.stem,
    };
    let hour = GanZhi {
        stem: ((effective_day_stem % 5) * 2 + hour_branch) % 10,
        branch: hour_branch,
    };

    Ok(FourPillars {
        bazi_year,
        year,
        month,
        day,
        hour,
    })
}

/// 不确定性来源名(spec AMB-5 固定顺序)。
pub const UNCERTAINTY_SOURCE_NAMES: [&str; 4] = [
    "lichun_boundary",
    "jie_boundary",
    "hour_boundary",
    "day_boundary",
];

/// 不确定性判定结果(spec 4.5)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Uncertainty {
    /// 是否 ambiguous(任一来源距离 < precision)。
    pub ambiguous: bool,
    /// 四类边界距离的最小值(秒)。
    pub boundary_distance_seconds: i64,
    /// 距离 < precision 的来源,按 AMB-5 固定顺序。
    pub sources: Vec<&'static str>,
}

/// 边界距离与不确定性判定(spec 条款 AMB-1…5)。
///
/// 前置条件与 [`four_pillars`] 相同;本函数不重复校验,调用方应先通过 [`four_pillars`]。
#[must_use]
pub fn uncertainty(
    t_unix: i64,
    lichun_unix: i64,
    local: LocalTime,
    month_ctx: MonthCtx,
    mode: ZiHourMode,
    precision_seconds: i64,
) -> Uncertainty {
    let d_lichun = (t_unix - lichun_unix).abs();
    let d_jie = (t_unix - month_ctx.jie_unix)
        .abs()
        .min((t_unix - month_ctx.next_jie_unix).abs());
    let s = i64::from(local.hh) * 3600 + i64::from(local.mm) * 60 + i64::from(local.ss);
    let x = (s + 3600) % 7200;
    let d_hour = x.min(7200 - x);
    let d_day = match mode {
        ZiHourMode::Split => s.min(86_400 - s),
        ZiHourMode::Unified => {
            let v = (s - 82_800).abs();
            v.min(86_400 - v)
        }
    };

    let distances = [d_lichun, d_jie, d_hour, d_day];
    let sources: Vec<&'static str> = UNCERTAINTY_SOURCE_NAMES
        .iter()
        .zip(distances)
        .filter(|&(_, d)| d < precision_seconds)
        .map(|(&name, _)| name)
        .collect();
    Uncertainty {
        ambiguous: !sources.is_empty(),
        boundary_distance_seconds: distances.into_iter().min().unwrap_or(0),
        sources,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// DP-2：JDN 公式对锚点日期自洽（2000-01-01 = 2451545，spec 定义性数值）。
    #[test]
    fn jdn_anchor_date() {
        assert_eq!(jdn(2000, 1, 1), 2_451_545);
    }

    /// DP-1/DP-3：锚点日干支序 54（戊午）。
    #[test]
    fn day_index_anchor() {
        assert_eq!(day_ganzhi_index(2_451_545), 54);
        let gz = ganzhi_from_index(54);
        assert_eq!((gz.stem_name(), gz.branch_name()), ("戊", "午"));
    }

    /// HP-1：整点界闭下界（23:00 归子、01:00 恰好归丑、22:59:59 仍亥）。
    #[test]
    fn hour_branch_boundaries() {
        let cases = [
            (23, 0, 0, 0u8),
            (0, 30, 0, 0),
            (0, 59, 59, 0),
            (1, 0, 0, 1),
            (22, 59, 59, 11),
            (11, 0, 0, 6),
        ];
        for (hh, mm, ss, want) in cases {
            let secs = i64::from(hh) * 3600 + i64::from(mm) * 60 + i64::from(ss);
            let got = u8::try_from(((secs + 3600) / 7200) % 12).unwrap();
            assert_eq!(got, want, "{hh}:{mm}:{ss}");
        }
    }

    /// LT-1：非法 local 拒绝（2 月 30 日、hh=24、1900 非闰年 2/29、2000 闰年 2/29 合法）。
    #[test]
    fn local_validity() {
        let ok = LocalTime {
            y: 2000,
            m: 2,
            d: 29,
            hh: 0,
            mm: 0,
            ss: 0,
        };
        assert!(ok.is_valid());
        let feb29_1900 = LocalTime {
            y: 1900,
            m: 2,
            d: 29,
            ..ok
        };
        assert!(!feb29_1900.is_valid());
        let feb30 = LocalTime { m: 2, d: 30, ..ok };
        assert!(!feb30.is_valid());
        let h24 = LocalTime { hh: 24, ..ok };
        assert!(!h24.is_valid());
    }
}
