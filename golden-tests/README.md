# golden-tests(L1 测试语料 + 对拍)

## 结构(DESIGN V3.0 第 5 节,七类语料)

```
golden-tests/
├── fixed/           # 固定黄金集(人工可复核;JSONL,# 开头为注释行)
├── boundary/        # 边界集(节气交接±1秒/±5分、真太阳时跨日、夏令时、早晚子时…)
├── stratified/      # 分层随机集配置(用例由 runner 按配额在线生成)
├── metamorphic/     # 不变式测试说明(实现挂在引擎测试套件)
├── regression/      # 缺陷回归集(每个差分事件裁决后永久入库)
├── oracle-sources/  # 外部 Oracle:权威历源数据(详见其 README 与谱系说明)
├── tools/           # 历源生成、交叉核对、用例生成脚本
├── runner/          # 对拍 runner(差分事件产出口)
└── reports/         # 对拍差异报告(gitignored,CI 以 artifact 上传)
```

规格条款测试(每条 spec 条款 ≥1 个测试 ID)的映射表随 contracts/paipan-spec.md 维护。

## 用例格式

每行一个 JSON:`{"case_id", "op", "input", "expected"}`。`expected` 为
`{"ok": true, "output": {...}}` 或 `{"ok": false}`(错误路径只断言失败,不比对错误文案)。
`case_id` 命名:`<模块>-<类别>-<序号>`(testing-standards)。

## 数据来源纪律

- 每个用例文件头部必须有 `# source:` 注释注明期望值来源。
- 合法来源:**spec 数学定义**(如干支取模公式)、**oracle-sources/ 权威历源数据**。
- **禁止**以模型记忆作为期望值来源。
- `fixed/year-pillar-smoke.jsonl` 的 `lichun_unix` 为合成占位数值(判界只依赖大小关系,流水线彩排用);`boundary/year-pillar-lichun.jsonl` 用 oracle-sources 真实立春时刻,由 `tools/gen_year_pillar_cases.py` 生成。

## 对拍

```bash
make golden-smoke   # 仅黄金集(秒级,pre-commit 闸门)
make duipai         # 黄金集 + 1 万确定性随机时刻
python3 golden-tests/runner/diff_runner.py --random 100000 --seed <SEED>   # 夜间全量
```

参考实现在独立仓库(盲隔离):本地默认取主仓**同级目录** `sk-paipan-reference/`,
CI 显式传 `--ref-dir`。对拍不一致 → 退出码 1 + `reports/` 差异报告 → 差分事件:
Fable 5 与 Codex 并行出独立证据报告,本人依规范 + 原始历源签署裁决(INV-08);
裁决后失败用例最小化入 `regression/`。

## 待办

- [x] 外部 Oracle 首批:JPL DE440s 自算 1900–2100 节气 + HKO 分钟级交叉核对(72 条最大偏差 30 秒)。
- [ ] 采购紫金山《中国天文年历》补第三方(历史年份分钟级;当前仅日期级抽查)。
- [ ] 历源谱系审计记录(确认各历源无共同数据谱系)——随下一批历源入库补齐。
- [ ] 四柱扩展后:分层随机配额生成、metamorphic 关系式、条款-测试映射表落地。
