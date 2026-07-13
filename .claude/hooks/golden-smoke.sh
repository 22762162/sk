#!/usr/bin/env bash
# 黄金集冒烟：对双实现灌入黄金集用例并对拍（不含随机 fuzz，保持秒级完成）。
# 改动 engine-paipan 任何计算路径后必须通过本脚本（CLAUDE.md 规则 2）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT/golden-tests/runner/diff_runner.py" --golden-only
