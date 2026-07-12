# 三鉴（SanJian）Monorepo

多 AI 互证的八字命理 APP。产品主张三个异构模型互相质证、分歧透明；工程过程采用同构的三角开发体系（Claude Code 主力 × Codex 盲实现/评审 × Opus 仲裁），详见 `docs/dev-plan.md`。

## 仓库结构（围绕五层架构）

```
sanjian/
├── CLAUDE.md                  # Claude Code 项目宪法（每次会话自动加载）
├── AGENTS.md                  # Codex 项目说明（语义同步、独立维护）
├── .claude/
│   ├── agents/                # 五个项目级子代理定义
│   ├── skills/                # 项目级技能（排盘领域知识、测试规范）
│   └── hooks/                 # 红线话术扫描、黄金集冒烟测试闸门
├── codex/tasks/               # Codex 两个固定任务模板（盲实现、PR 评审）
├── docs/
│   ├── paipan-spec.md         # 排盘算法数学规格（双实现唯一共享契约）
│   └── specs/                 # RFC 流程（跨层破坏性变更）
├── engine-paipan/             # L1 排盘引擎（Rust，Claude Code 主实现）
├── engine-paipan-ref/         # L1 参考实现（Python，Codex 盲实现，仅用于对拍）
├── golden-tests/              # 黄金测试集 + 对拍 runner + 三方历源比对数据
├── rulebase/                  # L2 流派规则库（schema/校验器；条目仅顾问可改）
├── consult-engine/            # L3+L4 会诊编排（Python/LangGraph + 推理网关）
├── prompts/                   # 辩手/仲裁提示词，版本化管理（仅 Opus 会话可改）
├── backend/                   # FastAPI 应用层
├── app/                       # Flutter 客户端
└── infra/                     # CI/CD、合规词表、可观测、部署
```

## 快速开始

```bash
make build          # 构建 Rust 引擎
make test           # 全部单元测试（Rust + Python 参考实现）
make golden-smoke   # 黄金集冒烟（改动 L1 计算路径后必跑）
make duipai         # 双实现对拍：黄金集 + 确定性随机时刻
make redline        # 大陆版红线词扫描（app/、backend/ 用户可见文案）
make install-hooks  # 安装 git pre-commit 闸门（人类工程师本机执行一次）
```

## 三条开发铁律

1. **关键算法必须双实现对拍**：L1 计算路径由 Claude Code（Rust）与 Codex（Python）互不可见地各自实现，CI 对拍，分歧交 Opus 仲裁（须权威历源证据佐证）。
2. **AI 写代码，人守闸门**：所有 AI 产出经 PR 合入；排盘引擎与合规代码必须人类批准；规则库条目永不由 AI 代写。
3. **上下文即资产**：CLAUDE.md / AGENTS.md / 子代理 / Skills / 提示词全部入 Git，同评审、同回滚。
