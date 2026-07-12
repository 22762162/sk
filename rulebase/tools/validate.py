#!/usr/bin/env python3
"""规则库校验器：校验 rulebase/entries/ 下全部条目（CI 阻断项）。

零第三方依赖：针对 rule.schema.json（draft v0）的约束手写校验，
schema 演进时本校验器与 schema 文件必须同 PR 更新。

除结构校验外强制三条纪律：
  1. strength ∈ [0, 1]；
  2. provenance.source_type == "licensed" 必须带 license_ref（版权白名单）；
  3. review.status == "confirmed" 必须带 reviewed_by——AI 草稿（draft_by_ai=true）
     未经顾问确认（即仍为 draft 状态）不算合规入库条目，只能停留在草稿区。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRIES_DIR = ROOT / "rulebase" / "entries"

ID_PATTERN = re.compile(r"^R-[a-z0-9]+(-[a-z0-9]+)*-[0-9]{4}$")
REQUIRED = ["id", "school", "condition", "claim", "strength", "provenance", "review"]
SOURCE_TYPES = {"classic_public_domain", "licensed", "consultant"}
REVIEW_STATUSES = {"draft", "confirmed"}


def validate_entry(entry: dict, where: str) -> list[str]:
    errors = []
    for field in REQUIRED:
        if field not in entry:
            errors.append(f"{where}: 缺少必填字段 {field}")
    if errors:
        return errors

    if not isinstance(entry["id"], str) or not ID_PATTERN.match(entry["id"]):
        errors.append(f"{where}: id 不符合模式 R-<school>-...-NNNN：{entry['id']!r}")
    for f in ("school", "condition", "claim"):
        if not isinstance(entry[f], str) or not entry[f].strip():
            errors.append(f"{where}: {f} 必须为非空字符串")
    s = entry["strength"]
    if not isinstance(s, (int, float)) or isinstance(s, bool) or not 0 <= s <= 1:
        errors.append(f"{where}: strength 必须是 [0,1] 内数值：{s!r}")

    prov = entry["provenance"]
    if not isinstance(prov, dict):
        errors.append(f"{where}: provenance 必须为对象")
    else:
        st = prov.get("source_type")
        if st not in SOURCE_TYPES:
            errors.append(f"{where}: provenance.source_type 非法：{st!r}")
        if not isinstance(prov.get("source"), str) or not prov.get("source", "").strip():
            errors.append(f"{where}: provenance.source 必须为非空字符串")
        if st == "licensed" and not prov.get("license_ref"):
            errors.append(f"{where}: 授权著作来源必须带 license_ref（版权白名单纪律）")

    review = entry["review"]
    if not isinstance(review, dict):
        errors.append(f"{where}: review 必须为对象")
    else:
        status = review.get("status")
        if status not in REVIEW_STATUSES:
            errors.append(f"{where}: review.status 非法：{status!r}")
        if status == "confirmed" and not review.get("reviewed_by"):
            errors.append(f"{where}: confirmed 条目必须记录 reviewed_by（顾问确认留痕）")
    return errors


def main() -> int:
    files = sorted(ENTRIES_DIR.glob("*.json"))
    all_errors = []
    n_entries = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            all_errors.append(f"{path.name}: JSON 解析失败：{exc}")
            continue
        entries = data if isinstance(data, list) else [data]
        for i, entry in enumerate(entries):
            n_entries += 1
            if not isinstance(entry, dict):
                all_errors.append(f"{path.name}[{i}]: 条目必须为对象")
                continue
            all_errors.extend(validate_entry(entry, f"{path.name}[{i}]"))

    if all_errors:
        print("\n".join(all_errors), file=sys.stderr)
        print(f"rulebase-check: 失败，{len(all_errors)} 处问题", file=sys.stderr)
        return 1
    print(f"rulebase-check: 通过（{len(files)} 个文件，{n_entries} 条条目）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
