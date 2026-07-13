# golden-tests（黄金测试集 + 对拍）

## 结构

```
golden-tests/
├── cases/        # 黄金用例（JSONL；# 开头为注释行）
├── sources/      # 权威历源比对数据（节气时刻已入库，详见 sources/README.md）
├── tools/        # 历源生成、交叉核对与用例生成脚本
├── runner/       # 对拍 runner
└── reports/      # 对拍差异报告（gitignored，CI 以 artifact 上传）
```

## 用例格式

每行一个 JSON：`{"case_id", "op", "input", "expected"}`。`expected` 为
`{"ok": true, "output": {...}}` 或 `{"ok": false}`（错误路径只断言失败，不比对错误文案）。
`case_id` 命名：`<模块>-<类别>-<序号>`（testing-standards）。

## 数据来源纪律

- 每个用例文件头部必须有 `# source:` 注释注明期望值来源。
- 合法来源：**spec 数学定义**（如干支取模公式）、**权威历源数据文件**（`sources/` 下，采购后入库）。
- **禁止**以模型记忆作为期望值来源。
- `cases/year-pillar-smoke.jsonl` 中的 `lichun_unix` 为**合成占位数值**（判界逻辑只依赖大小关系，流水线彩排用）；`cases/year-pillar-lichun.jsonl` 使用 `sources/` 真实立春时刻，由 `tools/gen_year_pillar_cases.py` 生成。

## 待办（行动清单第 5 项）

- [x] 权威历源首批入库：JPL DE440s 自算 1900–2100 节气 + HKO 分钟级交叉核对（72 条最大偏差 30 秒），见 `sources/README.md`。
- [ ] 采购紫金山天文台《中国天文年历》补齐三方比对的第三方（历史年份目前仅日期级抽查）。
- [ ] 基于权威数据生成万例黄金集（含附录 B 八类边界的系统性覆盖）——待 spec v0.2 月柱/日柱/时柱规格就位后展开。

## 运行

```bash
make golden-smoke   # 仅黄金集（秒级，pre-commit 闸门用）
make duipai         # 黄金集 + 1 万随机时刻对拍
python3 golden-tests/runner/diff_runner.py --random 100000 --seed <SEED>  # 夜间全量
```

对拍不一致 → 退出码 1 + `reports/` 差异报告 → 归档 discrepancy issue → Opus 仲裁（须附权威历源证据）。
