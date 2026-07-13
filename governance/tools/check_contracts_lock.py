#!/usr/bin/env python3
"""契约钉版校验(DESIGN V3.0 §4):contracts/ 必须是 sk-contracts 在 lock 所记 tag 的精确副本。

用法(CI 与本地一致,仅标准库;需网络克隆契约仓):
    python3 governance/tools/check_contracts_lock.py
退出码:0 一致;1 漂移或 lock 缺失。
"""

from __future__ import annotations

import filecmp
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "contracts.lock"
VENDORED = ROOT / "contracts"


def parse_lock() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data


def tree_diff(a: Path, b: Path) -> list[str]:
    cmp = filecmp.dircmp(a, b, ignore=[".git"])
    problems = [f"仅在副本: {n}" for n in cmp.left_only]
    problems += [f"仅在上游: {n}" for n in cmp.right_only]
    problems += [f"内容不同: {n}" for n in cmp.diff_files]
    for sub in cmp.subdirs.values():
        problems += tree_diff(Path(sub.left), Path(sub.right))
    return problems


def main() -> int:
    if not LOCK.exists():
        print("contracts.lock 缺失", file=sys.stderr)
        return 1
    lock = parse_lock()
    repo, tag = lock["repo"], lock["contract_version"]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", "--branch", tag, repo, tmp],
            check=True,
        )
        head = subprocess.run(
            ["git", "-C", tmp, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if head != lock["contract_commit"]:
            print(f"tag {tag} 的 commit 与 lock 不符: {head}", file=sys.stderr)
            return 1
        problems = tree_diff(VENDORED, Path(tmp))
        if problems:
            print("contracts/ 与上游 tag 内容漂移:", file=sys.stderr)
            print("\n".join(problems), file=sys.stderr)
            return 1
    print(f"contracts-lock 校验通过:contracts/ == sk-contracts@{tag}({head[:9]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
