# CHANGELOG

## v0.2.0(2026-07-14)

- 首个独立发版(自主仓 sk/contracts 迁出,DESIGN V3.0 四仓结构)。
- `paipan-spec.md` v0.2:年柱(v0.1 已评审)+ 四柱条款(LT-1、MP-1/2、DP-1/2/3/4、HP-1/2、
  four_pillars op)、附录 B 边界枚举、附录 C 条款-测试映射。
- schemas:paipan I/O(year_pillar + four_pillars);claim 升级为 V3.0 §3.4
  (computed_fact 仅 L1 注入、证据逐条绑定、结构化 confidence);run-manifest;
  新增 consultation-manifest(实验臂 S1/P3/D3/D3J、拉丁方分配、judge 盲评、随机化种子)。

## v0.3.0(2026-07-14)

- `paipan-spec.md` v0.3:新增 4.5 `four_pillars_uncertainty` op(AMB-1…5 边界距离与
  不确定性判定;独立 op,`four_pillars` 保持 v0.2 位级兼容)、调用方候选盘协议、
  第 5 章分级承诺(天文范围/容差/ΔT/tzdb 分层承诺);附录 C 增补 AMB 映射。
- `schemas/paipan.schema.json`:op 枚举扩充;新增 uncertainty 输入/输出 $defs。
- 依据:主仓 docs/specs/rfc-0001-contracts-v0.3.md(本人指示起草,DESIGN V3.0 §5.2)。
