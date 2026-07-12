#!/usr/bin/env bash
# Claude Code PreToolUse(Bash) 钩子：拦截 git commit，强制执行提交闸门。
# 闸门内容：① 红线词扫描（始终）② 黄金集冒烟（当暂存区触碰 engine-paipan/ 时）。
# 退出码 2 = 阻断本次工具调用，stderr 会回传给 Claude。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 从 stdin 的钩子 JSON 中取出即将执行的 Bash 命令；非 git commit 直接放行
CMD="$(python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    pass
' 2>/dev/null || true)"

case "$CMD" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

if ! bash "$ROOT/.claude/hooks/redline-scan.sh" >&2; then
  echo "提交被闸门阻断：红线词扫描未通过。" >&2
  exit 2
fi

if git -C "$ROOT" diff --cached --name-only 2>/dev/null | grep -q '^engine-paipan/'; then
  if ! bash "$ROOT/.claude/hooks/golden-smoke.sh" >&2; then
    echo "提交被闸门阻断：暂存区改动了 engine-paipan/，但黄金集冒烟未通过（CLAUDE.md 规则 2）。" >&2
    exit 2
  fi
fi

exit 0
