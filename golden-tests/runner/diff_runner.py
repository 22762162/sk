#!/usr/bin/env python3
"""双实现对拍 runner：黄金集 + 确定性随机时刻。

用法：
  python3 golden-tests/runner/diff_runner.py --golden-only             # 冒烟（pre-commit 闸门）
  python3 golden-tests/runner/diff_runner.py --random 10000 --seed 42  # 全量对拍
  python3 golden-tests/runner/diff_runner.py --rust-cmd <bin路径> ...   # CI 用预编译产物

协议见 docs/paipan-spec.md 附录 A。判定规则：
  * 双实现输出逐字段严格相等（错误用例只比对 ok 标志，错误文案允许不同）；
  * 有 expected 的黄金用例，双实现还须各自与期望一致。
任何不一致 → 退出码 1，细节写入 golden-tests/reports/（归档为 discrepancy issue 交 Opus 仲裁）。
"""

import argparse
import json
import random
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "golden-tests" / "cases"
REPORTS_DIR = ROOT / "golden-tests" / "reports"

DEFAULT_RUST_CMD = (
    f"cargo run --quiet --manifest-path {ROOT / 'engine-paipan' / 'Cargo.toml'} --bin paipan-cli"
)
DEFAULT_REF_CMD = f"{sys.executable} -m paipan_ref.cli"


def load_golden_cases() -> list[dict]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.jsonl")):
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            case["_where"] = f"{path.name}:{lineno}"
            cases.append(case)
    return cases


def gen_random_cases(n: int, seed: int) -> list[dict]:
    """确定性随机用例：判界 ±1 秒、节气交接 ±5 分钟、宽域偏移、Y<4、负时间戳（spec 附录 B）。"""
    rng = random.Random(seed)
    cases = []
    for i in range(n):
        civil_year = rng.randint(1, 2999)
        lichun = rng.randint(-4_000_000_000, 4_000_000_000)
        kind = rng.random()
        if kind < 0.3:
            dt = rng.choice([-1, 0, 1])
        elif kind < 0.6:
            dt = rng.randint(-300, 300)
        else:
            dt = rng.randint(-2_000_000_000, 2_000_000_000)
        cases.append({
            "case_id": f"rnd-{seed}-{i:06d}",
            "op": "year_pillar",
            "input": {"civil_year": civil_year, "t_unix": lichun + dt, "lichun_unix": lichun},
        })
    return cases


def run_impl(cmd: list[str], cwd: Path, cases: list[dict]) -> dict[str, dict]:
    payload = "\n".join(
        json.dumps({k: c[k] for k in ("case_id", "op", "input")}, ensure_ascii=False)
        for c in cases
    ) + "\n"
    proc = subprocess.run(
        cmd, cwd=cwd, input=payload, capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"实现进程退出码 {proc.returncode}：{' '.join(cmd)}\nstderr:\n{proc.stderr[-2000:]}"
        )
    outputs = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            obj = json.loads(line)
            outputs[obj.get("case_id")] = obj
    return outputs


def compare_case(case: dict, rust_out: dict | None, ref_out: dict | None) -> dict | None:
    """一致返回 None，否则返回差异记录（含双方原始输出，供仲裁看推导链）。"""
    problems = []
    if rust_out is None or ref_out is None:
        problems.append({"kind": "missing_output", "rust": rust_out, "ref": ref_out})
    else:
        if rust_out.get("ok") != ref_out.get("ok"):
            problems.append({"kind": "ok_flag_mismatch", "rust": rust_out, "ref": ref_out})
        elif rust_out.get("ok") and rust_out.get("output") != ref_out.get("output"):
            problems.append({
                "kind": "output_mismatch",
                "rust": rust_out["output"],
                "ref": ref_out["output"],
            })
        expected = case.get("expected")
        if expected is not None:
            for name, out in (("rust", rust_out), ("ref", ref_out)):
                if out.get("ok") != expected.get("ok"):
                    problems.append({
                        "kind": f"{name}_vs_expected_ok", "got": out, "expected": expected,
                    })
                elif expected.get("ok") and out.get("output") != expected.get("output"):
                    problems.append({
                        "kind": f"{name}_vs_expected_output",
                        "got": out.get("output"),
                        "expected": expected.get("output"),
                    })
    if problems:
        return {
            "where": case.get("_where", "random"),
            "case": {k: v for k, v in case.items() if not k.startswith("_")},
            "problems": problems,
        }
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--golden-only", action="store_true", help="仅跑黄金集（冒烟）")
    ap.add_argument("--random", type=int, default=0, metavar="N", help="随机用例数")
    ap.add_argument("--seed", type=int, default=20260712, help="随机种子（写入报告，保证可复现）")
    ap.add_argument("--rust-cmd", default=DEFAULT_RUST_CMD, help="Rust 主实现 CLI 命令")
    ap.add_argument("--ref-cmd", default=DEFAULT_REF_CMD, help="Python 参考实现 CLI 命令")
    args = ap.parse_args()

    cases = load_golden_cases()
    n_golden = len(cases)
    if not args.golden_only and args.random > 0:
        cases += gen_random_cases(args.random, args.seed)
    if not cases:
        print("没有可用用例（golden-tests/cases/ 为空？）", file=sys.stderr)
        return 1

    print(f"对拍开始：黄金集 {n_golden} 例 + 随机 {len(cases) - n_golden} 例（seed={args.seed}）")
    rust_outputs = run_impl(shlex.split(args.rust_cmd), ROOT, cases)
    ref_outputs = run_impl(shlex.split(args.ref_cmd), ROOT / "engine-paipan-ref", cases)

    discrepancies = []
    for case in cases:
        d = compare_case(case, rust_outputs.get(case["case_id"]), ref_outputs.get(case["case_id"]))
        if d:
            discrepancies.append(d)

    if discrepancies:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / time.strftime(f"discrepancy-%Y%m%d-%H%M%S-seed{args.seed}.json")
        report_path.write_text(
            json.dumps(
                {
                    "seed": args.seed,
                    "total": len(cases),
                    "golden": n_golden,
                    "mismatch": len(discrepancies),
                    "details": discrepancies[:200],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"对拍失败：{len(discrepancies)}/{len(cases)} 例不一致；报告 → {report_path}\n"
            "处置：归档 discrepancy issue → Opus 仲裁（附双方推导链 + 权威历源证据）",
            file=sys.stderr,
        )
        return 1

    print(f"对拍通过：{len(cases)} 例全部一致（黄金集 {n_golden} 例含期望值比对）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
