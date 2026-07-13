# 三鉴 monorepo 常用命令（CLAUDE.md 常用命令表）
.PHONY: build test test-rust test-ref lint golden-smoke duipai redline rulebase-check install-hooks render-ai-docs governance-check

build:
	cargo build --manifest-path engine-paipan/Cargo.toml

test: test-rust test-ref

test-rust:
	cargo test --manifest-path engine-paipan/Cargo.toml

test-ref:
	cd engine-paipan-ref && python3 -m pytest -q tests

lint:
	cargo fmt --manifest-path engine-paipan/Cargo.toml --all -- --check
	cargo clippy --manifest-path engine-paipan/Cargo.toml --all-targets -- -D warnings

# 黄金集冒烟：改动 engine-paipan 计算路径后必跑（CLAUDE.md 规则 2）
golden-smoke:
	python3 golden-tests/runner/diff_runner.py --golden-only

# 双实现对拍：黄金集 + 1 万确定性随机时刻
duipai:
	python3 golden-tests/runner/diff_runner.py --random 10000 --seed 20260712

# 大陆版红线词扫描（app/ + backend/ 用户可见文案）
redline:
	bash .claude/hooks/redline-scan.sh

rulebase-check:
	python3 rulebase/tools/validate.py

# 治理:CLAUDE.md / AGENTS.md 由 governance/ 事实源渲染生成（dev-plan V2.1 第 4 节）
render-ai-docs:
	python3 governance/tools/render_ai_docs.py

governance-check:
	python3 governance/tools/render_ai_docs.py --check

# 人类工程师本机执行一次，启用 git pre-commit 闸门
install-hooks:
	chmod +x infra/githooks/* .claude/hooks/*.sh
	git config core.hooksPath infra/githooks
	@echo "git hooks 已指向 infra/githooks/"
