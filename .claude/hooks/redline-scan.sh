#!/usr/bin/env bash
# 输出文案红线扫描（INV-04 私用底线）：扫描可见文案目录，命中即失败。
# 词表：infra/compliance/redline-words.txt（一行一词，# 开头为注释）
# 豁免：infra/compliance/redline-allowlist.txt（一行一个 "路径:词"，用于评审过的例外）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORDS_FILE="$ROOT/infra/compliance/redline-words.txt"
ALLOW_FILE="$ROOT/infra/compliance/redline-allowlist.txt"
# 扫描范围：用户可见文案所在目录（源代码字符串与本地化文件）
SCAN_DIRS=("backend" "web")

if [[ ! -f "$WORDS_FILE" ]]; then
  echo "redline-scan: 词表缺失 $WORDS_FILE" >&2
  exit 1
fi

hits=0
while IFS= read -r word; do
  [[ -z "$word" || "$word" == \#* ]] && continue
  for dir in "${SCAN_DIRS[@]}"; do
    [[ -d "$ROOT/$dir" ]] || continue
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      # 豁免检查：允许清单中列出的 "相对路径:词" 跳过
      rel="${line%%:*}"
      rel="${rel#"$ROOT"/}"
      if [[ -f "$ALLOW_FILE" ]] && grep -qxF "$rel:$word" "$ALLOW_FILE"; then
        continue
      fi
      echo "红线词命中 [$word] $line"
      hits=$((hits + 1))
    done < <(grep -rn --binary-files=without-match -F "$word" "$ROOT/$dir" 2>/dev/null || true)
  done
done < "$WORDS_FILE"

if [[ "$hits" -gt 0 ]]; then
  echo "redline-scan: 共 $hits 处命中，禁止合入。请改用概率化措辞（倾向/提示/或有）。" >&2
  exit 1
fi
echo "redline-scan: 通过（扫描目录: ${SCAN_DIRS[*]}）"
