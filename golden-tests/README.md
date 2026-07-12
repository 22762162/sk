# golden-tests（黄金测试集 + 对拍）

## 结构

```
golden-tests/
├── cases/        # 黄金用例（JSONL；# 开头为注释行）
├── sources/      # 三方权威历源比对数据（待采购入库，见下）
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
- 当前 `cases/year-pillar-smoke.jsonl` 中的 `lichun_unix` 均为**合成占位数值**（判界逻辑只依赖大小关系，与真实立春无关）；涉及真实节气时刻的用例必须等 `sources/` 权威数据就位后生成。

## 待办（行动清单第 5 项，需人工采购）

- [ ] 采购/获取三方权威历源比对数据（候选：中科院紫金山天文台《中国天文年历》、寿星万年历导出数据、HORIZONS/VSOP87 自算校验），入 `sources/`，附来源与许可说明。
- [ ] 基于权威数据生成万例黄金集（含附录 B 八类边界的系统性覆盖）。

## 运行

```bash
make golden-smoke   # 仅黄金集（秒级，pre-commit 闸门用）
make duipai         # 黄金集 + 1 万随机时刻对拍
python3 golden-tests/runner/diff_runner.py --random 100000 --seed <SEED>  # 夜间全量
```

对拍不一致 → 退出码 1 + `reports/` 差异报告 → 归档 discrepancy issue → Opus 仲裁（须附权威历源证据）。
