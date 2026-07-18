#!/bin/bash
# 三鉴 · 双击启动(服务 + 公网隧道),无需任何命令行知识。
# 首次使用前提:~/Projects/sk 已就位、.env 已配置(三把 API 密钥)。
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
cd "$HOME/Projects/sk" || { echo "找不到 ~/Projects/sk"; read -n1 -p "按任意键退出"; exit 1; }

echo "======================================"
echo "   三鉴 · 启动中"
echo "======================================"

if [ ! -f .env ]; then
  echo "⚠ 缺少 .env(三把 API 密钥)。排盘可用,AI 功能不可用。"
fi

# 引擎(未编译则编译一次)
if [ ! -x engine-paipan/target/release/paipan-cli ]; then
  echo "首次运行:编译排盘引擎(约半分钟)…"
  cargo build --release --manifest-path engine-paipan/Cargo.toml >/dev/null 2>&1
fi

# 服务
if ! /usr/sbin/lsof -ti :8788 >/dev/null 2>&1; then
  echo "启动本机服务…"
  set -a; [ -f .env ] && . ./.env; set +a
  nohup env SANJIAN_DAILY_CALL_CAP=500 uv run --with fastapi --with uvicorn --with httpx \
    -- uvicorn backend.app:app --host 127.0.0.1 --port 8788 >/tmp/sanjian_srv.log 2>&1 &
  for i in $(seq 1 20); do sleep 2; curl -s -o /dev/null http://127.0.0.1:8788/ && break; done
else
  echo "本机服务已在运行。"
fi

# 公网隧道(掉线会换新网址,属免费隧道特性)
if ! pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
  echo "开公网隧道…"
  : > /tmp/cf_tunnel.log
  nohup cloudflared tunnel --no-autoupdate --url http://localhost:8788 >/tmp/cf_tunnel.log 2>&1 &
  for i in $(seq 1 15); do sleep 2; grep -qE "trycloudflare\.com" /tmp/cf_tunnel.log && break; done
fi
URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/cf_tunnel.log | head -1)

echo ""
echo "✅ 就绪!"
echo "   本机地址: http://127.0.0.1:8788"
echo "   公网地址: ${URL:-(隧道还在连,稍后重开本脚本查看)}"
echo "   (公网地址每次隧道重启会变;别把它发给不信任的人——用的是你的密钥)"
echo ""
open "http://127.0.0.1:8788"
read -n1 -p "按任意键关闭本窗口(服务继续后台运行)"
