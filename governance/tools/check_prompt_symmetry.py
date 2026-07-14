#!/usr/bin/env python3
"""提示词对称性校验(DESIGN §2.2/§2.3:拉丁方前提)。

辩手骨架必须**模型无关、流派无关**:三个流派模块只提供流派语汇,
辩手/质证提示词的骨架结构对各流派必须一致,否则拉丁方比较失效。
本校验强制:辩手/质证提示词含唯一的 {{SCHOOL_MODULE}} 占位符(流派内容全部外置),
不得在骨架里出现任一具体流派名(子平/旺衰/调候/格局/调候用神…)。

用法(CI 阻断项,仅标准库):
    python3 governance/tools/check_prompt_symmetry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKELETONS = [
    ROOT / "prompts" / "base" / "debaters" / "debater.md",
    ROOT / "prompts" / "base" / "debaters" / "cross_exam.md",
]
SCHOOL_LEAK_TERMS = ["子平格局", "旺衰扶抑", "调候派", "五虎", "穷通宝鉴"]


def main() -> int:
    errors = []
    for path in SKELETONS:
        if not path.exists():
            errors.append(f"{path.name}: 缺失")
            continue
        text = path.read_text(encoding="utf-8")
        body = text.split("## system", 1)[-1]
        if body.count("{{SCHOOL_MODULE}}") != 1:
            errors.append(f"{path.name}: 骨架须恰含 1 个 {{SCHOOL_MODULE}} 占位符(流派内容一律外置)")
        for term in SCHOOL_LEAK_TERMS:
            if term in body:
                errors.append(f"{path.name}: 骨架泄漏具体流派词「{term}」(破坏拉丁方对称性)")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print("prompt-symmetry: 失败", file=sys.stderr)
        return 1
    print(f"prompt-symmetry: 通过({len(SKELETONS)} 个辩手骨架流派无关、含唯一占位符)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
