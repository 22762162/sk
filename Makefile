# 三鉴 monorepo 常用命令（CLAUDE.md 常用命令表）
.PHONY: build test test-rust test-ref lint golden-smoke duipai redline rulebase-check install-hooks render-ai-docs governance-check v1-serve keys-check eval-smoke research-smoke prompt-symmetry

build:
	cargo build --manifest-path engine-paipan/Cargo.toml

# 参考实现在独立仓库(盲隔离,INV-09);本地默认取主仓同级目录
REF_DIR ?= ../sk-paipan-reference

test: test-rust test-ref

test-rust:
	cargo test --manifest-path engine-paipan/Cargo.toml

test-ref:
	@if [ -d "$(REF_DIR)" ]; then cd "$(REF_DIR)" && python3 -m pytest -q tests; \
	else echo "跳过参考实现测试:$(REF_DIR) 未就位(git clone https://github.com/22762162/sk-paipan-reference.git)"; fi

lint:
	cargo fmt --manifest-path engine-paipan/Cargo.toml --all -- --check
	cargo clippy --manifest-path engine-paipan/Cargo.toml --all-targets -- -D warnings

# 黄金集冒烟：改动 engine-paipan 计算路径后必跑（CLAUDE.md 规则 2）
golden-smoke:
	python3 golden-tests/runner/diff_runner.py --golden-only

# 双实现对拍：黄金集 + 1 万确定性随机时刻
duipai:
	python3 golden-tests/runner/diff_runner.py --random 10000 --seed 20260712

# 输出文案红线扫描（backend/ + web/,INV-04 私用底线）
redline:
	bash .claude/hooks/redline-scan.sh

rulebase-check:
	python3 rulebase/tools/validate.py

# 治理:CLAUDE.md / AGENTS.md 由 governance/ 事实源渲染生成（dev-plan V2.1 第 4 节）
render-ai-docs:
	python3 governance/tools/render_ai_docs.py

governance-check:
	python3 governance/tools/render_ai_docs.py --check

# 契约钉版校验:contracts/ 必须等于 sk-contracts@contracts.lock 所记 tag(需网络)
contracts-check:
	python3 governance/tools/check_contracts_lock.py

# 本地测试页:构建 release 引擎后起 FastAPI(http://127.0.0.1:8788);.env 中的密钥只进本机进程
v1-serve:
	cargo build --release --manifest-path engine-paipan/Cargo.toml
	set -a; [ -f .env ] && . ./.env; set +a; \
	uv run --with fastapi --with uvicorn --with httpx -- uvicorn backend.app:app --host 127.0.0.1 --port 8788

# 四实验臂评测 smoke(需 .env 密钥;每盘 4 臂约 17 次调用,受日熔断约束)
eval-smoke:
	set -a; [ -f .env ] && . ./.env; set +a; \
	uv run --with httpx python3 evals/runner/run_eval.py \
	  --dataset evals/datasets/smoke.jsonl --arms S1,P3,D3,D3J \
	  --out evals/reports/eval-smoke.json

# 研究模式拉丁方 smoke(需 .env 密钥;1 盘 = 9 次调用)
research-smoke:
	set -a; [ -f .env ] && . ./.env; set +a; \
	uv run --with httpx python3 evals/runner/run_research.py \
	  --birth 1990-06-15T08:30 --out evals/reports/research-smoke.json

# 提示词对称性校验(拉丁方前提;CI 阻断项)
prompt-symmetry:
	python3 governance/tools/check_prompt_symmetry.py

# 密钥就位检查:只报告有/无,绝不输出密钥内容(INV-07)
keys-check:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	uv run --with httpx python3 -c "import sys; sys.path.insert(0,'consult-engine'); import gateway; \
	print('\n'.join(f'{p}: ' + ('已配置' if gateway.key_present(p) else '未配置') for p in ('anthropic','openai','deepseek')))"

# 人类工程师本机执行一次，启用 git pre-commit 闸门
install-hooks:
	chmod +x infra/githooks/* .claude/hooks/*.sh
	git config core.hooksPath infra/githooks
	@echo "git hooks 已指向 infra/githooks/"
