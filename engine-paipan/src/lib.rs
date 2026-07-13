//! 三鉴排盘引擎（L1）——零 AI 依赖的确定性计算库。
//!
//! 铁律（CLAUDE.md 规则 1）：本 crate 禁止 LLM 调用、网络请求与一切
//! 非确定性逻辑（系统时钟、随机数、环境变量分支）。历法事实——节气
//! 时刻、时区规则、夏令时——一律由调用方以参数或数据文件注入，代码
//! 中不得出现任何历法常量。
//!
//! 双实现契约：`contracts/paipan-spec.md`（与 `engine-paipan-ref` 互不可见）。

pub mod ganzhi;
pub mod year_pillar;
