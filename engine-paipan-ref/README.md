# engine-paipan-ref（L1 参考实现 · Python）

排盘引擎的独立参考实现，**仅用于与 `engine-paipan/`（Rust 主实现）差分对拍**，不对外提供服务。

## 独立性声明

- 正式流程中本目录由 **Codex 依据 `docs/paipan-spec.md` 盲写**（任务模板：`codex/tasks/ref-implementer.md`），实现期间禁止查看 `engine-paipan/`；Claude Code 会话亦禁止读取本目录实现代码（CLAUDE.md 第二节）。
- ⚠️ **当前内容为第一周端到端彩排的临时占位实现**（由同一会话产出，不满足异源独立性）。进入 P1 排盘引擎主战役前，须由 Codex 按盲实现流程整体重写替换，本段声明随之删除。

## 约束

仅 Python 标准库（测试用 pytest）；零第三方运行时依赖；确定性（无网络/时钟/无种子随机）；历法事实仅来自注入参数。

## 运行

```bash
cd engine-paipan-ref
python3 -m pytest -q tests          # 单元测试
echo '{"case_id":"x","op":"year_pillar","input":{"civil_year":1984,"t_unix":1,"lichun_unix":0}}' \
  | python3 -m paipan_ref.cli       # 对拍 CLI（spec 附录 A 协议）
```
