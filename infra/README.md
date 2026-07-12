# infra（CI/CD · 合规 · 可观测 · 部署）

```
infra/
├── compliance/   # 大陆版红线词表 + 豁免清单（月度评审更新，改动走 PR）
├── githooks/     # git pre-commit 闸门（make install-hooks 启用）
└── …             # 可观测（Langfuse 类 trace）、部署配置（P1 后期）
```

## CI 四道闸（.github/workflows/ci.yml）

1. **rust**：rustfmt + clippy pedantic（-D warnings）+ 单元/属性测试
2. **duipai**：双实现对拍（黄金集 + 1 万随机时刻；夜间任务跑 10 万，见 nightly-duipai.yml）
3. **redline**：红线词扫描（app/ + backend/）
4. **rulebase**：规则条目 schema 校验

另有 **ref**（Python 参考实现测试）。任何一道闸失败即阻断合入。
