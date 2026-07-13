//! 年柱单元与属性测试。
//!
//! 期望值仅来自 contracts/paipan-spec.md 的数学定义（YP-1/YP-2/YP-3），
//! 不使用任何凭记忆的历法事实；测试中的"立春时刻"均为合成占位数值，
//! 判界逻辑只依赖大小关系。

use engine_paipan::year_pillar::{resolve_bazi_year, year_ganzhi, year_pillar};
use proptest::prelude::*;

/// 锚点 YP-3：1984 = 甲子。
#[test]
fn anchor_1984_is_jiazi() {
    let gz = year_ganzhi(1984);
    assert_eq!((gz.stem, gz.branch), (0, 0));
    assert_eq!(gz.name(), "甲子");
}

/// 判界三连测（testing-standards：界前 1 秒 / 恰好 / 界后 1 秒）。
#[test]
fn lichun_boundary_before_falls_to_previous_year() {
    let lichun = 1_000_000;
    assert_eq!(resolve_bazi_year(2000, lichun - 1, lichun), 1999);
}

#[test]
fn lichun_boundary_exact_belongs_to_current_year() {
    let lichun = 1_000_000;
    assert_eq!(resolve_bazi_year(2000, lichun, lichun), 2000);
}

#[test]
fn lichun_boundary_after_belongs_to_current_year() {
    let lichun = 1_000_000;
    assert_eq!(resolve_bazi_year(2000, lichun + 1, lichun), 2000);
}

/// 负 Unix 时间戳的判界行为与正值一致（spec 附录 B）。
#[test]
fn negative_timestamps_resolve_consistently() {
    let lichun = -628_000_000;
    assert_eq!(resolve_bazi_year(1950, lichun - 1, lichun), 1949);
    assert_eq!(resolve_bazi_year(1950, lichun, lichun), 1950);
}

/// 组合函数：立春前一秒 → 上一年的干支。
#[test]
fn year_pillar_composes_resolution_and_ganzhi() {
    let lichun = 949_000_000;
    let before = year_pillar(2000, lichun - 1, lichun);
    let at = year_pillar(2000, lichun, lichun);
    assert_eq!(before.bazi_year, 1999);
    assert_eq!(at.bazi_year, 2000);
    assert_eq!(before.ganzhi, year_ganzhi(1999));
    assert_eq!(at.ganzhi, year_ganzhi(2000));
}

proptest! {
    // 六十年周期回环（spec 附录 B）
    #[test]
    fn sixty_year_cycle(y in -10_000i32..10_000) {
        prop_assert_eq!(year_ganzhi(y), year_ganzhi(y + 60));
    }

    // 天干十年、地支十二年各自循环
    #[test]
    fn stem_and_branch_periods(y in -10_000i32..10_000) {
        prop_assert_eq!(year_ganzhi(y).stem, year_ganzhi(y + 10).stem);
        prop_assert_eq!(year_ganzhi(y).branch, year_ganzhi(y + 12).branch);
    }

    // 相邻年：天干、地支各前进一位
    #[test]
    fn consecutive_years_advance_by_one(y in -10_000i32..10_000) {
        let a = year_ganzhi(y);
        let b = year_ganzhi(y + 1);
        prop_assert_eq!(u16::from(b.stem), (u16::from(a.stem) + 1) % 10);
        prop_assert_eq!(u16::from(b.branch), (u16::from(a.branch) + 1) % 12);
    }

    // 序号恒在合法范围，含 Y < 4（欧几里得取模非负性，spec 附录 B）
    #[test]
    fn indices_always_in_range(y in -10_000i32..10_000) {
        let gz = year_ganzhi(y);
        prop_assert!(gz.stem < 10 && gz.branch < 12);
    }

    // 判界与 YP-1 定义逐点一致
    #[test]
    fn boundary_resolution_matches_spec(
        civil in 1i32..3000,
        lichun in -4_000_000_000i64..4_000_000_000,
        dt in -2_000_000_000i64..2_000_000_000,
    ) {
        let t = lichun + dt;
        let expect = if t < lichun { civil - 1 } else { civil };
        prop_assert_eq!(resolve_bazi_year(civil, t, lichun), expect);
    }
}
