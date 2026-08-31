"""出口服务入口:仅绑定 127.0.0.1:8793(RFC-0003;严禁 0.0.0.0)。

启动:python -m integrations.huohuo_bridge.serve
环境:HUOHUO_EXPORT_TOKEN / HUOHUO_EXPORT_SCOPES_JSON / HUOHUO_EXPORT_DATABASE_URL
任一缺失服务以关闭态运行(全部 503),便于健康探测但绝不回退。
"""

from __future__ import annotations

import uvicorn

from .config import BridgeConfig
from .service import create_app
from .source import SqlAlchemySource


def build() -> object:
    cfg = BridgeConfig.from_env()
    src = None
    if cfg and cfg.database_url:
        try:
            src = SqlAlchemySource(cfg.database_url)
        except Exception:  # noqa: BLE001 坏 DSN/缺驱动:固定关闭态,不打印 DSN
            src = None
    return create_app(cfg, src)


if __name__ == "__main__":
    uvicorn.run(build(), host="127.0.0.1", port=8793, log_level="warning")
