"""L3 推理网关(最小实现,DESIGN V3.0 §0/§3.3)。

- 多供应商抽象:anthropic / openai / deepseek(密钥从环境读取,进程内使用,
  永不写日志、永不返回给调用方之外的通道;INV-07)。
- fail_closed:密钥缺失、供应商报错、超出日调用熔断 → 抛 GatewayError,不静默降级。
- 每次调用落 run manifest(INV-06;schema 见 contracts/schemas/run-manifest.schema.json),
  manifest 只存哈希与用量,不存密钥。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"
DAILY_CAP = int(os.environ.get("SANJIAN_DAILY_CALL_CAP", "50"))


class GatewayError(RuntimeError):
    """网关失败(fail_closed):调用方应向用户如实报错,不得降级伪装成功。"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _today_call_count() -> int:
    prefix = datetime.now(timezone.utc).strftime("run-%Y%m%d")
    return sum(1 for p in MANIFEST_DIR.glob(f"{prefix}*.json"))


PROVIDERS = {
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "url": "https://api.anthropic.com/v1/messages",
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "deepseek": {
        "env": "DEEPSEEK_API_KEY",
        "url": "https://api.deepseek.com/chat/completions",
    },
}


def key_present(provider: str) -> bool:
    """只报有无,不暴露内容(make keys-check 用)。"""
    v = os.environ.get(PROVIDERS[provider]["env"], "")
    return bool(v) and "粘贴" not in v


def call(provider: str, model_id: str, system: str, user: str,
         max_tokens: int = 1024, temperature: float = 0.0,
         output_schema_version: str = "v1") -> dict:
    """同步调用一次模型;返回 {text, token_usage, run_id};失败抛 GatewayError。"""
    if provider not in PROVIDERS:
        raise GatewayError(f"未知供应商:{provider}")
    if not key_present(provider):
        raise GatewayError(f"{provider} 密钥未配置(编辑仓库根目录 .env 后重启服务)")
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    if _today_call_count() >= DAILY_CAP:
        raise GatewayError(f"已达网关日调用熔断上限({DAILY_CAP});如需继续请调高 SANJIAN_DAILY_CALL_CAP")

    key = os.environ[PROVIDERS[provider]["env"]]
    url = PROVIDERS[provider]["url"]
    # 部分新推理模型不接受显式 temperature(仅支持默认);temperature<0 视为"不指定"。
    send_temp = temperature is not None and temperature >= 0
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": model_id, "max_tokens": max_tokens,
                   "system": system, "messages": [{"role": "user", "content": user}]}
    else:  # openai 兼容协议(openai / deepseek)
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
        payload = {"model": model_id, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
    if send_temp:
        payload["temperature"] = temperature

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=90)
    except httpx.HTTPError as exc:
        raise GatewayError(f"{provider} 网络错误:{exc.__class__.__name__}") from exc
    if resp.status_code != 200:
        raise GatewayError(f"{provider} 返回 {resp.status_code}:{resp.text[:200]}")
    data = resp.json()

    if provider == "anthropic":
        text = "".join(b.get("text", "") for b in data.get("content", []))
        usage = data.get("usage", {})
    else:
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

    now = datetime.now(timezone.utc)
    run_id = now.strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    manifest = {
        "run_id": run_id,
        "timestamp": now.isoformat(),
        "provider": provider,
        "model_id": model_id,
        "model_release": data.get("model"),
        "input_hash": _sha(user),
        "system_prompt_hash": _sha(system),
        "prompt_bundle_hash": None,
        "rulebase_commit": None,
        "retrieval_manifest": [],
        "sampling_parameters": {"temperature": temperature, "max_tokens": max_tokens},
        "output_schema_version": output_schema_version,
        "response_hash": _sha(text),
        "token_usage": usage,
        "cost": None,
    }
    (MANIFEST_DIR / f"{run_id}.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"text": text, "token_usage": usage, "run_id": run_id}
