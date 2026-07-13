#!/usr/bin/env python3
"""高风险 PR 的 attestation 校验(DESIGN V3.0 §1.2)。

规则:相对 base 分支的 diff 若触碰 role-separation.yaml 的 high_risk_paths,
则同一 PR 必须新增/修改 governance/attestations/ 下至少一份 attestation。
本人签署由「合并动作本身」承载;交叉评审替代情况须写入 attestation notes。

用法(CI 在 PR 上执行;仅标准库):
    python3 governance/tools/check_attestation.py --base origin/main
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def high_risk_patterns() -> list[str]:
    pats = []
    in_section = False
    for line in (ROOT / "governance" / "role-separation.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("high_risk_paths:"):
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("- "):
                pats.append(stripped[2:].split("#")[0].strip())
            elif stripped and not stripped.startswith("#"):
                break
    return pats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()

    changed = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", f"{args.base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if not changed:
        print("attestation 校验:无改动")
        return 0

    pats = high_risk_patterns()
    hits = [
        f for f in changed
        if any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch(f, p.rstrip("*").rstrip("/") + "/*")
               for p in pats)
        and not f.startswith("governance/attestations/")
    ]
    attested = [f for f in changed if f.startswith("governance/attestations/")]

    if hits and not attested:
        print(
            "高风险路径改动缺少 attestation(governance/attestations/ 未随 PR 更新):\n  "
            + "\n  ".join(hits[:20]),
            file=sys.stderr,
        )
        return 1
    label = f"{len(hits)} 个高风险文件,attestation {len(attested)} 份" if hits else "无高风险改动"
    print(f"attestation 校验通过:{label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
