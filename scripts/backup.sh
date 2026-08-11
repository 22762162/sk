#!/bin/bash
# 三鉴数据备份:档案/预测库/会诊记录/manifests/.env → ~/Documents/三鉴备份(保留最近14份)
set -e
SRC="$HOME/Projects/sk"
DST="$HOME/Documents/三鉴备份"
mkdir -p "$DST"
DAY=$(date +%Y%m%d)
tar czf "$DST/sanjian-$DAY.tar.gz" -C "$SRC" \
  $(cd "$SRC"; ls -d consult-engine/dossier consult-engine/appdata consult-engine/records consult-engine/manifests .env 2>/dev/null)
ls -t "$DST"/sanjian-*.tar.gz 2>/dev/null | tail -n +15 | xargs rm -f 2>/dev/null
echo "$(date '+%F %T') 备份完成 $DST/sanjian-$DAY.tar.gz"
