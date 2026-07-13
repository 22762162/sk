#!/usr/bin/env python3
"""从 ai-invariants.yaml + overlay 渲染 CLAUDE.md 与 AGENTS.md(DESIGN V3.0 第 4 节)。

用法:
    python3 governance/tools/render_ai_docs.py            # 渲染并写盘
    python3 governance/tools/render_ai_docs.py --check    # 校验生成文件与事实源同步(CI 用)

依赖:PyYAML(本地:uv run --with pyyaml;CI:pip install pyyaml)。
渲染是确定性的:同样的输入永远产出同样的字节。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GOV = ROOT / "governance"

HEADER = (
    "<!-- 生成文件,勿手改。事实源:governance/ai-invariants.yaml + governance/{overlay} -->\n"
    "<!-- 重渲染:python3 governance/tools/render_ai_docs.py;CI 以 --check 校验同步 -->\n\n"
)

TITLES = {
    "CLAUDE.md": "# 三鉴项目宪法(CLAUDE.md · Claude Code / Fable 5 侧)",
    "AGENTS.md": "# 三鉴项目说明(AGENTS.md · Codex 侧)",
}

INTRO = {
    "CLAUDE.md": (
        "本文件是 Claude Code 每次会话自动加载的项目记忆,由治理事实源渲染生成。"
        "共同铁律与 AGENTS.md 语义一致(同源渲染);两侧 overlay 独立维护。"
    ),
    "AGENTS.md": (
        "本文件是 Codex 的项目说明,由治理事实源渲染生成。"
        "共同铁律与 CLAUDE.md 语义一致(同源渲染);两侧 overlay 独立维护。"
    ),
}


def render(overlay_name: str, doc_name: str) -> str:
    inv = yaml.safe_load((GOV / "ai-invariants.yaml").read_text(encoding="utf-8"))
    overlay = (GOV / overlay_name).read_text(encoding="utf-8")
    lines = [
        HEADER.replace("{overlay}", overlay_name),
        TITLES[doc_name] + "\n\n",
        INTRO[doc_name] + "\n\n",
        f"## 一、不可违反的共同铁律(ai-invariants v{inv['version']})\n\n",
    ]
    for i, item in enumerate(inv["invariants"], 1):
        text = " ".join(str(item["text"]).split())
        lines.append(f"{i}. **{item['title']}({item['id']})** {text}\n")
    lines.append("\n")
    lines.append(overlay.strip() + "\n")
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写盘,漂移时退出码 1")
    args = ap.parse_args()

    targets = {
        "CLAUDE.md": render("claude-overlay.md", "CLAUDE.md"),
        "AGENTS.md": render("codex-overlay.md", "AGENTS.md"),
    }
    drift = []
    for name, content in targets.items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                drift.append(name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"已渲染 {name}")
    if drift:
        print(f"生成文件与事实源不同步: {drift};请运行渲染脚本并提交", file=sys.stderr)
        return 1
    if args.check:
        print("governance-check 通过:CLAUDE.md / AGENTS.md 与事实源同步")
    return 0


if __name__ == "__main__":
    sys.exit(main())
