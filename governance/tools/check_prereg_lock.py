#!/usr/bin/env python3
"""预注册冻结校验(DESIGN §10,INV-13)。

预注册文件在开跑前须冻结:其 sha256 登记于 docs/prereg/prereg.lock。
本校验强制:
  1. docs/prereg/ 下每个 *.md 都在 lock 中登记;
  2. 登记哈希与当前文件内容逐字节一致(冻结后就地改写 = CI 阻断);
  3. lock 中不得残留已删除文件的条目。
如需正当修订:新开一个预注册版本文件(barnum-v2…),用 freeze_prereg.py 重新登记,走 PR 评审。

用法(CI 阻断项,仅标准库):
    python3 governance/tools/check_prereg_lock.py
退出码:0 全部冻结一致;1 缺登记 / 哈希漂移 / 残留条目。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG_DIR = ROOT / "docs" / "prereg"
LOCK = PREREG_DIR / "prereg.lock"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lock() -> dict:
    if not LOCK.exists():
        return {}
    return json.loads(LOCK.read_text(encoding="utf-8")).get("frozen", {})


def main() -> int:
    if not PREREG_DIR.exists():
        print("prereg-lock: 通过(docs/prereg/ 尚未建立)")
        return 0
    frozen = load_lock()
    docs = sorted(p.name for p in PREREG_DIR.glob("*.md"))
    errors = []

    for name in docs:
        if name not in frozen:
            errors.append(f"{name}: 未登记于 prereg.lock(预注册须先冻结,INV-13)")
            continue
        actual = sha256_of(PREREG_DIR / name)
        if actual != frozen[name]:
            errors.append(f"{name}: 哈希漂移(冻结后被就地改写);登记 {frozen[name][:12]}… 实际 {actual[:12]}…")

    for name in frozen:
        if name not in docs:
            errors.append(f"{name}: lock 有登记但文件缺失(删除预注册须同步移除登记)")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        print("prereg-lock: 失败", file=sys.stderr)
        return 1
    print(f"prereg-lock: 通过({len(docs)} 份预注册冻结一致)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
