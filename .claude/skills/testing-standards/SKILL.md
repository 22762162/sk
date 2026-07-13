---
name: testing-standards
description: 三鉴测试规范。编写或评审任何测试代码时使用，统一测试分层、命名、数据来源与对拍协议。
---

# 三鉴测试规范

## 测试分层

| 层 | 工具 | 要求 |
| --- | --- | --- |
| 单元测试 | Rust `#[test]` / pytest | 每个公共函数至少一个；判界函数必须含边界三连测（界前 1 秒、恰好、界后 1 秒） |
| 属性测试 | proptest（Rust 核心历算函数强制） | 周期性（60/10/12 循环）、单调性、逆运算往返 |
| 黄金集 | golden-tests/cases/*.jsonl | 期望值只能来自权威历源数据或 spec 数学定义 |
| 对拍 | golden-tests/runner/diff_runner.py | 双实现灌同一输入集，任何不一致即缺陷信号 |

## 数据来源纪律

- 期望值禁止来自模型记忆（"我记得 1988 年 2 月 4 日是……"→ 禁止）。
- 黄金集数据文件必须在文件头注明来源（`# source:`）；`placeholder` 来源的数据仅用于流水线演练，不得用于断言正确性宣传。
- 命盘数据一律合成，禁止真实用户数据。

## 对拍 I/O 协议（JSONL）

- 输入行：`{"case_id": str, "op": str, "input": {...}}`
- 输出行：`{"case_id": str, "ok": bool, "output": {...}}`（失败时 `"ok": false, "error": str`）
- 两实现的 CLI 均为 stdin→stdout 的 JSONL 流；比较时逐字段严格相等。
- 随机对拍必须**确定性**：种子显式传入并记录在报告中，禁止无种子随机。

## 命名

- Rust 测试：`边界类别_场景_期望`（如 `lichun_boundary_before_falls_to_previous_year`）。
- 黄金集 case_id：`<模块>-<类别>-<序号>`（如 `yp-anchor-0001`）。
