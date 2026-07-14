#!/usr/bin/env python3
"""预注册冻结助手(人工执行,DESIGN §10 / INV-13)。

把 docs/prereg/ 下全部 *.md 的 sha256 写入 docs/prereg/prereg.lock。
只应在**预注册定稿、开跑前**执行一次;开跑后再改预注册须新开版本文件后重跑本脚本,并在 PR 说明留痕。
CI 用 check_prereg_lock.py 校验冻结不漂移;本脚本不在 CI 中运行(冻结是有意的人工动作)。

用法:
    python3 governance/tools/freeze_prereg.py            # 写入/更新 lock
    python3 governance/tools/freeze_prereg.py --check    # 只报告是否需要更新(不写盘)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG_DIR = ROOT / "docs" / "prereg"
LOCK = PREREG_DIR / "prereg.lock"


def build_frozen() -> dict:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(PREREG_DIR.glob("*.md"))
    }


def main() -> int:
    PREREG_DIR.mkdir(parents=True, exist_ok=True)
    frozen = build_frozen()
    payload = {
        "note": "预注册冻结哈希;开跑前登记,CI(check_prereg_lock.py)校验不漂移。改预注册须新开版本文件后重冻。",
        "frozen": frozen,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        current = LOCK.read_text(encoding="utf-8") if LOCK.exists() else ""
        if current == text:
            print(f"freeze-prereg: 已是最新({len(frozen)} 份)")
            return 0
        print("freeze-prereg: 需更新 prereg.lock(运行不带 --check 写盘)", file=sys.stderr)
        return 1
    LOCK.write_text(text, encoding="utf-8")
    print(f"已冻结 {len(frozen)} 份预注册 → {LOCK.relative_to(ROOT)}")
    for name, h in frozen.items():
        print(f"  {name}: {h[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
