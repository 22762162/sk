#!/usr/bin/env python3
"""晋升:staging → approved(**仅供本人/顾问运行**,INV-03/RS-3)。

本工具由人类评审者执行:确认条目内容后签署 reviewed_by/reviewed_at,
移动到 approved/ 并生成 provenance/ 来源链记录;最终以 PR 合入(分支保护把关)。
AI 不得替评审者运行本工具做真实条目的晋升。

用法(仅标准库):
    python3 rulebase/tools/promote.py --id R-ziping-shishen-0001 \
        --reviewed-by 本人 --reviewed-at 2026-07-14
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RB = ROOT / "rulebase"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--reviewed-by", required=True)
    ap.add_argument("--reviewed-at", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    src = RB / "staging" / f"{args.id}.json"
    if not src.exists():
        print(f"staging 中无 {args.id}", file=sys.stderr)
        return 1
    entry = json.loads(src.read_text(encoding="utf-8"))
    entry["review"] = {"status": "confirmed", "reviewed_by": args.reviewed_by,
                       "reviewed_at": args.reviewed_at}

    sys.path.insert(0, str(RB / "tools"))
    from validate import validate_entry  # noqa: PLC0415
    errors = validate_entry(entry, args.id)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    dst = RB / "approved" / f"{args.id}.json"
    dst.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prov = RB / "provenance" / f"{args.id}.yaml"
    prov.write_text(
        f"""# 来源链记录(DESIGN V3.0 §6;随条目同 PR 合入,不可省略)
rule_id: {entry['id']}
source_id: {entry['provenance']['source']}
source_edition: 待补(版本/底本)
source_locator: 待补(卷·篇·节)
license: {entry['provenance']['source_type']}
extractor_model: {'AI 录入辅助(draft_by_ai)' if entry.get('draft_by_ai') else '人工'}
extractor_prompt_hash: null
reviewer: {args.reviewed_by}
review_decision: confirmed
approval_signature: {args.reviewed_by} @ {args.reviewed_at}
""", encoding="utf-8")
    src.unlink()
    print(f"已晋升 → {dst.relative_to(ROOT)};来源链 → {prov.relative_to(ROOT)}\n"
          "请补全 provenance 的 edition/locator 字段后走 PR 合入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
