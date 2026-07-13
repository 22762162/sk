# 三鉴(SanJian)· 私人研究项目

研究「确定性排盘 + 多模型互证」技术架构:**开发态** Fable 5(Claude Code)× Codex 双模型,
**运行态** DeepSeek × GPT × Claude 三师会诊。工程设计见 `docs/DESIGN.md`(V2.1)。
本项目不上架、不收费、不向第三方提供服务;性质变更闸门见 DESIGN 第 9.3 节。

## 仓库结构(DESIGN V3.0 第 4 节,三仓之主仓)

```
sk/                            # 主仓库(Fable 5 via Claude Code 工作区)
├── CLAUDE.md / AGENTS.md      # 生成文件勿手改(事实源 governance/,make render-ai-docs)
├── governance/                # ai-invariants(铁律唯一事实源)、角色隔离、模型路由、渲染脚本
├── contracts/                 # 双实现唯一共享物:排盘规格 + I/O/claim/run-manifest schema
├── docs/{DESIGN,adr,specs,reviews,research-notes}
├── engine-paipan/             # L1 排盘引擎(Rust 主实现)
├── golden-tests/              # fixed/boundary/stratified/metamorphic/regression + oracle-sources
├── evals/                     # smoke/change/monthly/frozen-holdout/safety(运行态评测)
├── rulebase/                  # approved(只读)/staging/rejected/schemas/provenance
├── consult-engine/            # L3+L4 会诊编排 + 推理网关
├── prompts/                   # base/provider-adapters/manifests(起草纪律见 INV-10)
├── backend/ ├── web/          # FastAPI + 本地 Web(L5,研究观察窗口)
├── security/                  # 数据分级清单、密钥与成本护栏
├── codex/tasks/               # Codex 主仓任务模板(pr-reviewer)
└── infra/                     # CI/CD、合规词表、githooks

sk-paipan-reference/           # 独立仓库:Python 参考实现(Codex 盲写,只见 contracts 镜像)
```

## 快速开始

```bash
make build          # 构建 Rust 引擎
make test           # 全部单元测试(Rust;参考实现测试在其独立仓库)
make golden-smoke   # 黄金集冒烟(改动 L1 计算路径后必跑)
make duipai         # 双实现对拍(需同级目录克隆 sk-paipan-reference)
make redline        # 输出文案红线扫描(backend/、web/)
make governance-check  # CLAUDE.md/AGENTS.md 与治理事实源同步校验
make install-hooks  # 安装 git pre-commit 闸门(本机执行一次)
```

## 三条核心纪律(全文见 governance/ai-invariants.yaml)

1. **关键算法双实现对拍**:L1 由主仓 Rust 与独立仓 Python 互不可见地各自实现,唯一共享物是 contracts;分歧生成差分事件,AI 只出证据,**本人签署裁决**。
2. **多重佐证不等于证明**:双实现 + 多历源一致仅表示未发现差异;正确性还需来源独立性审计、规格条款全覆盖、性质测试。
3. **上下文即资产**:治理配置、提示词、评测集全部入 Git,同评审、同回滚;CLAUDE.md/AGENTS.md 由事实源渲染,禁止手改。
