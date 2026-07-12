"""对拍 CLI：stdin JSONL → stdout JSONL（spec 附录 A）。

单行错误 → 该行 ok:false，继续处理后续行，进程不崩溃。
"""

import json
import sys

from .year_pillar import year_pillar


def handle(line: str) -> dict:
    try:
        case = json.loads(line)
    except json.JSONDecodeError as exc:
        return {"case_id": None, "ok": False, "error": f"bad case line: {exc}"}
    case_id = case.get("case_id")
    op = case.get("op")
    if op != "year_pillar":
        return {"case_id": case_id, "ok": False, "error": f"unknown op: {op}"}
    try:
        inp = case["input"]
        out = year_pillar(int(inp["civil_year"]), int(inp["t_unix"]), int(inp["lichun_unix"]))
    except (KeyError, TypeError, ValueError) as exc:
        return {"case_id": case_id, "ok": False, "error": f"bad input: {exc!r}"}
    return {"case_id": case_id, "ok": True, "output": out}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        print(json.dumps(handle(line), ensure_ascii=False))


if __name__ == "__main__":
    main()
