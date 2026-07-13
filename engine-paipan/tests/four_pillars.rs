//! 四柱集成测试与属性测试。规格条款:contracts/paipan-spec.md v0.2 第 4 章。

use engine_paipan::four_pillars::{
    day_ganzhi_index, four_pillars, jdn, LocalTime, MonthCtx, ZiHourMode,
};
use proptest::prelude::*;

fn lt(y: i32, m: u8, d: u8, hh: u8, mm: u8, ss: u8) -> LocalTime {
    LocalTime {
        y,
        m,
        d,
        hh,
        mm,
        ss,
    }
}

const CTX: MonthCtx = MonthCtx {
    jie_seq: 0,
    jie_unix: 0,
    next_jie_unix: 1_000_000,
};

/// MP-1 判界三连:窗口前 1 秒拒绝 / 恰好交节接受 / 窗口内接受 / 上界恰好拒绝。
#[test]
fn month_window_boundaries() {
    let local = lt(2000, 6, 1, 12, 0, 0);
    assert!(four_pillars(-1, 0, local, CTX, ZiHourMode::Split).is_err());
    assert!(four_pillars(0, 0, local, CTX, ZiHourMode::Split).is_ok());
    assert!(four_pillars(999_999, 0, local, CTX, ZiHourMode::Split).is_ok());
    assert!(four_pillars(1_000_000, 0, local, CTX, ZiHourMode::Split).is_err());
}

/// MP-2 五虎遁全表:寅月月干 甲己→丙 乙庚→戊 丙辛→庚 丁壬→壬 戊癸→甲(spec 考证记录)。
#[test]
fn wuhu_dun_first_month_stems() {
    // 年干序 y_stem 由 bazi_year 推出;构造 bazi_year 使年干为 0..=9。
    // (Y−4) mod 10 = s → Y = 4 + s。lichun 取 0、t 取 1(t≥lichun 归当年)。
    let expect = [2u8, 4, 6, 8, 0, 2, 4, 6, 8, 0]; // 甲乙丙丁戊己庚辛壬癸 → 丙戊庚壬甲…
    for s in 0u8..10 {
        let y = 4 + i32::from(s);
        let local = lt(y, 6, 1, 12, 0, 0);
        let fp = four_pillars(1, 0, local, CTX, ZiHourMode::Split).unwrap();
        assert_eq!(fp.year.stem, s);
        assert_eq!(fp.month.stem, expect[usize::from(s)], "year stem {s}");
        assert_eq!(fp.month.branch, 2, "jie_seq=0 → 寅月");
    }
}

/// DP-4/HP-2 早晚子时:split 模式 23 点日柱不换、时干用次日日干;unified 模式日柱换。
#[test]
fn zi_hour_modes() {
    let d1 = lt(2000, 1, 1, 23, 30, 0);
    let split = four_pillars(1, 0, d1, CTX, ZiHourMode::Split).unwrap();
    let unified = four_pillars(1, 0, d1, CTX, ZiHourMode::Unified).unwrap();

    // split:日柱 = 2000-01-01(序 54 戊午);unified:日柱 = 次日(序 55 己未)。
    assert_eq!((split.day.stem, split.day.branch), (4, 6), "戊午");
    assert_eq!((unified.day.stem, unified.day.branch), (5, 7), "己未");

    // 时支均为子(0);时干均以次日日干(己,序 5)起五鼠遁:(5%5)*2+0 = 0 = 甲。
    assert_eq!(split.hour.branch, 0);
    assert_eq!(unified.hour.branch, 0);
    assert_eq!(split.hour.stem, 0, "晚子时用次日日干起遁(HP-2)");
    assert_eq!(unified.hour.stem, 0);

    // 23:00:00 恰好归次日(unified,1.3 闭下界);22:59:59 不换。
    let at23 = lt(2000, 1, 1, 23, 0, 0);
    let before23 = lt(2000, 1, 1, 22, 59, 59);
    assert_eq!(
        four_pillars(1, 0, at23, CTX, ZiHourMode::Unified)
            .unwrap()
            .day
            .stem,
        5
    );
    assert_eq!(
        four_pillars(1, 0, before23, CTX, ZiHourMode::Unified)
            .unwrap()
            .day
            .stem,
        4
    );
}

/// LT-1 错误路径:非法日期/时刻必须拒绝。
#[test]
fn invalid_local_rejected() {
    for bad in [
        lt(2001, 2, 29, 0, 0, 0),
        lt(2000, 13, 1, 0, 0, 0),
        lt(2000, 1, 1, 24, 0, 0),
        lt(2000, 1, 1, 0, 60, 0),
        lt(0, 1, 1, 0, 0, 0),
    ] {
        assert!(
            four_pillars(1, 0, bad, CTX, ZiHourMode::Split).is_err(),
            "{bad:?}"
        );
    }
}

proptest! {
    /// DP-2/DP-3:相邻两日的日干支序恒差 1(mod 60)——60 日周期连续性。
    #[test]
    fn day_cycle_is_continuous(y in 1i32..3000, m in 1u8..=12, d in 1u8..=27) {
        let a = day_ganzhi_index(jdn(y, m, d));
        let b = day_ganzhi_index(jdn(y, m, d + 1));
        prop_assert_eq!((i16::from(a) + 1) % 60, i16::from(b));
    }

    /// HP-1:任意合法时刻的时支序 ∈ [0,12)且每 2 小时递增一支。
    #[test]
    fn hour_branch_in_range(hh in 0u8..24, mm in 0u8..60, ss in 0u8..60) {
        let local = lt(2000, 6, 1, hh, mm, ss);
        let fp = four_pillars(1, 0, local, CTX, ZiHourMode::Split).unwrap();
        prop_assert!(fp.hour.branch < 12);
        let expect = u8::try_from(((i64::from(hh)*3600 + i64::from(mm)*60 + i64::from(ss) + 3600) / 7200) % 12).unwrap();
        prop_assert_eq!(fp.hour.branch, expect);
    }

    /// 四柱输出的全部干支序恒在合法域(结构不变量)。
    #[test]
    fn all_indices_in_range(
        y in 1i32..3000, m in 1u8..=12, d in 1u8..=28,
        hh in 0u8..24, jie in 0u8..12, unified in proptest::bool::ANY,
    ) {
        let mode = if unified { ZiHourMode::Unified } else { ZiHourMode::Split };
        let ctx = MonthCtx { jie_seq: jie, jie_unix: -10, next_jie_unix: 10 };
        let fp = four_pillars(0, -5, lt(y, m, d, hh, 0, 0), ctx, mode).unwrap();
        for gz in [fp.year, fp.month, fp.day, fp.hour] {
            prop_assert!(gz.stem < 10 && gz.branch < 12);
        }
        prop_assert_eq!(fp.month.branch, (2 + jie) % 12);
    }
}
