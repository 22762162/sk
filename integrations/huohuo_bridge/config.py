"""出口服务配置(RFC-0003 + 交叉审查 R1):严格类型与格式校验,任一不合规即整体关闭。

不复用不明旧 token、不接受宽松类型(字符串误当 group 列表、None 被 str 化等)。
create_app 直接注入的配置同样过本套校验(validate)。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

MIN_TOKEN_LEN = 32
MAX_TOKEN_LEN = 256
MAX_SCOPES = 100
MAX_GROUPS = 100
SCHEMA_VERSION = "huohuo-readonly-v1"

_SCOPE_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}")  # fullmatch 使用,防末尾换行
_TOKEN_RE = re.compile(r"[\x21-\x7e]{32,256}")        # ASCII 可打印,无空格


def _valid_token(token: object) -> bool:
    return isinstance(token, str) and _TOKEN_RE.fullmatch(token) is not None


@dataclass(frozen=True)
class ScopeCfg:
    label: str
    project_id: str
    group_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BridgeConfig:
    token: str
    scopes: dict[str, ScopeCfg]
    database_url: str | None = None


def _valid_scope(sid: object, v: object) -> ScopeCfg | None:
    if not isinstance(sid, str) or not _SCOPE_ID_RE.fullmatch(sid):
        return None
    if not isinstance(v, dict):
        return None
    label = v.get("label", sid)
    pid = v.get("project_id")
    gids = v.get("group_ids", [])
    if not isinstance(label, str) or not (1 <= len(label) <= 80):
        return None
    if not isinstance(pid, str) or not pid.strip():
        return None  # project_id 必须原生非空字符串,拒绝 None/数字被 str 化
    if not isinstance(gids, list) or len(gids) > MAX_GROUPS:
        return None  # 字符串会被迭代成单字符,必须是 list
    out: list[str] = []
    for g in gids:
        if not isinstance(g, str) or not g.strip():
            return None
        out.append(g)
    if len(set(out)) != len(out):
        return None  # 重复组不接受
    return ScopeCfg(label=label, project_id=pid, group_ids=tuple(out))


def validate(token: object, scopes_raw: object, database_url: object = None) -> BridgeConfig | None:
    """统一校验入口:env 与直接注入共用;任一不合规返回 None(服务关闭)。"""
    if not _valid_token(token):
        return None
    if not isinstance(scopes_raw, dict) or not scopes_raw or len(scopes_raw) > MAX_SCOPES:
        return None
    scopes: dict[str, ScopeCfg] = {}
    for sid, v in scopes_raw.items():
        cfg = _valid_scope(sid, v)
        if cfg is None:
            return None
        scopes[sid] = cfg
    url = database_url if (isinstance(database_url, str) and database_url.strip()) else None
    return BridgeConfig(token=token, scopes=scopes, database_url=url)


def validate_config(cfg: object) -> BridgeConfig | None:
    """对已构造的 BridgeConfig 再走一遍严格校验(防直接注入绕过)。

    R2-1:成员类型逐一验证——group_ids 必须是 str 元组(字符串在此会被拒,不 list() 洗白);
    scopes 非 dict、成员非 ScopeCfg、任何异常一律按不合规关闭,不抛出。
    """
    try:
        if not isinstance(cfg, BridgeConfig) or not isinstance(cfg.scopes, dict):
            return None
        raw: dict = {}
        for sid, s in cfg.scopes.items():
            if not isinstance(s, ScopeCfg) or not isinstance(s.group_ids, tuple):
                return None
            if not all(isinstance(g, str) for g in s.group_ids):
                return None
            raw[sid] = {"label": s.label, "project_id": s.project_id,
                        "group_ids": list(s.group_ids)}
        return validate(cfg.token, raw, cfg.database_url)
    except Exception:  # noqa: BLE001
        return None


def from_env() -> BridgeConfig | None:
    """环境值仅运行态读取,不打印。"""
    token = os.environ.get("HUOHUO_EXPORT_TOKEN", "")
    raw = os.environ.get("HUOHUO_EXPORT_SCOPES_JSON", "")
    url = os.environ.get("HUOHUO_EXPORT_DATABASE_URL") or None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return validate(token, parsed, url)


# 兼容旧引用
BridgeConfig.from_env = staticmethod(from_env)  # type: ignore[attr-defined]
