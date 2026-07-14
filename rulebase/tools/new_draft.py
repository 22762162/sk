#!/usr/bin/env python3
"""录入辅助:生成规则草稿到 staging/(INV-03)。

AI 与顾问口述转写只能产出**草稿**:draft_by_ai=true、review.status=draft;
条目进入 approved/ 必须经 promote.py(本人/顾问签署)+ PR 合入。

用法(仅标准库):
    python3 rulebase/tools/new_draft.py \
        --school ziping --topic shishen \
        --condition "月令正官 AND 天干透伤官" \
        --claim "命局或有职场权威关系方面的张力,提示关注规则边界议题" \
        --strength 0.4 \
        --source-type classic_public_domain --source "《子平真诠》·论伤官"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RB = ROOT / "rulebase"


def next_id(school: str, topic: str) -> str:
    pat = re.compile(rf"^R-{school}-{topic}-(\d{{4}})$")
    top = 0
    for d in ("approved", "staging", "rejected"):
        for p in (RB / d).glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            entries = data if isinstance(data, list) else [data]
            for e in entries:
                m = pat.match(str(e.get("id", "")))
                if m:
                    top = max(top, int(m.group(1)))
    return f"R-{school}-{topic}-{top + 1:04d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--school", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--claim", required=True)
    ap.add_argument("--strength", type=float, required=True)
    ap.add_argument("--source-type", required=True,
                    choices=["classic_public_domain", "licensed", "consultant"])
    ap.add_argument("--source", required=True)
    ap.add_argument("--license-ref", default=None)
    args = ap.parse_args()

    entry = {
        "id": next_id(args.school, args.topic),
        "school": args.school,
        "condition": args.condition,
        "claim": args.claim,
        "strength": args.strength,
        "provenance": {"source_type": args.source_type, "source": args.source},
        "draft_by_ai": True,
        "review": {"status": "draft"},
    }
    if args.license_ref:
        entry["provenance"]["license_ref"] = args.license_ref

    sys.path.insert(0, str(RB / "tools"))
    from validate import validate_entry  # noqa: PLC0415
    errors = validate_entry(entry, "new_draft")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    out = RB / "staging" / f"{entry['id']}.json"
    out.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"草稿已写入 {out.relative_to(ROOT)}(draft_by_ai=true;晋升须 promote.py + PR)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
