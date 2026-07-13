//! 干支（六十甲子）编号与命名。规格条款：paipan-spec 第 2 节。

/// 十天干，序号 0–9（spec 2.1）。
pub const STEMS: [&str; 10] = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"];

/// 十二地支，序号 0–11（spec 2.2）。
pub const BRANCHES: [&str; 12] = [
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
];

/// 一组干支（六十甲子之一）。
///
/// 不变量：`stem < 10`，`branch < 12`。本 crate 的构造路径
/// （如 [`crate::year_pillar::year_ganzhi`]）保证该不变量。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GanZhi {
    /// 天干序号，0 = 甲 … 9 = 癸。
    pub stem: u8,
    /// 地支序号，0 = 子 … 11 = 亥。
    pub branch: u8,
}

impl GanZhi {
    /// 天干名。
    ///
    /// # Panics
    /// 当 `stem > 9`（违反类型不变量）时 panic。
    #[must_use]
    pub fn stem_name(self) -> &'static str {
        STEMS[usize::from(self.stem)]
    }

    /// 地支名。
    ///
    /// # Panics
    /// 当 `branch > 11`（违反类型不变量）时 panic。
    #[must_use]
    pub fn branch_name(self) -> &'static str {
        BRANCHES[usize::from(self.branch)]
    }

    /// 干支名：天干名与地支名直接拼接（spec 2.3）。
    ///
    /// # Panics
    /// 违反类型不变量时 panic（同 [`Self::stem_name`] / [`Self::branch_name`]）。
    #[must_use]
    pub fn name(self) -> String {
        format!("{}{}", self.stem_name(), self.branch_name())
    }
}
