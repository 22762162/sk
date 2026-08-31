"""sanshu 三段封存 · Change Eval 执行器 v2(P19 整改版;INV-12:与候选/基线提示词永不同 PR)。

整改对照(docs/reviews/pr51-codex-cross-review.md + 六点清单):
①双臂同一冻结 as_of(Asia/Shanghai)与窗口/事件校验;②失败保留审计回执并入统计(重试/漏词);
③real 预检:冻结 lock+本人批准文件缺一不可,未过预检不构造任何供应商调用,输出恒 NOT-A-GATE;
④排他唯一 run 目录+写一次工件+输入/提示词/schema/代码/模型配置哈希入档;
⑤用例集 v2(中性结构材料/期限锁齐);⑥facts-only 基线提示词已分拆至独立 PR(p19b),本分支不携带。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))

import liuyao  # noqa: E402
import meihua  # noqa: E402
import sanshu_orchestrator as so  # noqa: E402
import sanshu_validator as sv  # noqa: E402

PROVIDERS = [("anthropic", "claude-sonnet-5"), ("gemini", "gemini-3.6-flash"),
             ("deepseek", "deepseek-chat")]
APPROVAL_FILE = "thresholds-approved.yaml"  # 本人手工提交;机器永不写入


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def shanghai_as_of() -> str:
    """冻结锚点:当前时刻的 Asia/Shanghai 日期(与编排器同口径;测试可冻结本模块 datetime)。"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date().isoformat()


def load_prompts(pdir: Path) -> dict:
    def body(name):
        text = (pdir / name).read_text(encoding="utf-8")
        return text.split("## system", 1)[1].strip() if "## system" in text else text
    return {"bazi": body("sanshu-bazi-v2.md"), "gua": body("sanshu-gua-v2.md"),
            "combined": body("sanshu-combined-v2.md")}


def build_cast(case: dict):
    if case["method"] == "liuyao":
        return liuyao.cast(case["lines"], case["day_ganzhi"], case["month_branch"])
    return meihua.cast_numbers(case["n1"], case["n2"], case["hour_branch"])


def redline_words() -> list[str]:
    try:
        return [w.strip() for w in (ROOT / "infra" / "compliance" / "redline-words.txt")
                .read_text(encoding="utf-8").splitlines()
                if w.strip() and not w.startswith("#")]
    except OSError:
        return []  # 隔离测试环境无红线表:计 0 并在报告指纹标注 loaded=0


def dry_caller_factory(cast_hash: str, method: str, deadline: str = "2026-09-30",
                       as_of: str | None = None):
    """干跑合成 caller。默认窗口 09-01..09-30(独立评审探针契约);
    执行器内部按各例 deadline/as_of 传入,产出合规窗口。"""
    w_start = as_of or "2026-09-01"
    w_end = deadline if deadline < "2026-09-30" else "2026-09-30"
    if w_end < w_start:
        w_end = w_start

    def caller(role, system, user):
        ev = {"statement": "本窗口内目标事项出现明确进展", "window": {"start": w_start, "end": w_end},
              "metric": {"indicator": "事项进展", "comparator": "发生", "threshold": None, "unit": None},
              "adjudication": "以本人当期记录为准判定发生与否"}
        base = {"status": "ok", "confidence": "medium",
                "yingqi": {"start": w_start, "end": w_end},
                "verifiable_events": [ev], "method_basis": "干跑合成依据,仅验管道"}
        if role == "bazi":
            return json.dumps({**base, "reading": "干跑合成八字段落,长度补齐" + "验" * 10},
                              ensure_ascii=False), "dry-b"
        if role == "gua":
            return json.dumps({**base, "reading": "干跑合成卦段落,长度补齐" + "验" * 10,
                               "method": method, "cast_hash": cast_hash},
                              ensure_ascii=False), "dry-g"
        return json.dumps({**base, "answer": "干跑合成综合回答,先给结论示例",
                           "reasoning": "干跑合成推理,两段合参示意" + "验" * 8,
                           "dissent_note": ""}, ensure_ascii=False), "dry-c"
    return caller


def real_caller_factory(provider: str, model: str, budget: dict):
    import gateway  # noqa: PLC0415 仅通过 real 预检后才会被调用

    def caller(role, system, user):
        if budget["left"] <= 0:
            raise so.OrchestrationError("Change Eval 调用预算耗尽")
        budget["left"] -= 1
        text, run_id, _usage = gateway.call(provider, model, system=system, user=user,
                                            temperature=-1, max_tokens=2500,
                                            output_schema_version="sanshu-eval-v1")
        return text, run_id
    return caller


def run_facts_baseline(caller, provider: str, case: dict) -> dict:
    """消融基线臂:仅事实无术数,一次调用;窗口/事件校验与主链同一 as_of/deadline 口径(整改①)。"""
    as_of = shanghai_as_of()
    deadline = case["deadline"]
    prompt_file = ROOT / "evals" / "change" / "baseline_prompts" / "facts-only-v1.md"
    if prompt_file.exists():
        system = prompt_file.read_text(encoding="utf-8").split("## system", 1)[-1].strip()
    else:
        system = "BASELINE_PROMPT_PENDING_P19B(占位;real 模式在预检即因缺文件中止)"
    user = f"问题:{case['question']}\n期限:{deadline}(事件窗口不得超出此期限;本单锚点日期 {as_of})"
    if case.get("facts_summary"):
        user += f"\n【共同事实背景(合成)】{case['facts_summary']}"
    manifest = {"arm": "facts_baseline", "provider": provider, "as_of": as_of,
                "deadline": deadline, "calls": {}}
    obj = so._call_validated(
        caller, "combined", system, user,
        lambda o: sv.validate_combined(o, "high", "high") + so._windows_within(o, as_of, deadline),
        manifest)
    return {"provider": provider, "bazi": None, "gua": None, "combined": obj,
            "combined_status": obj.get("status"), "manifest": manifest}


def _unique_run_dir(reports: Path, stem: str) -> tuple[Path, str]:
    """排他唯一 run 目录:同秒并发/重跑绝不覆盖(整改④)。"""
    for k in range(1, 1000):
        rid = stem if k == 1 else f"{stem}-{k}"
        d = reports / "raw" / rid
        try:
            d.mkdir(parents=True, exist_ok=False)
            return d, rid
        except FileExistsError:
            continue
    raise RuntimeError("run 目录分配失败")


def _bump_from_manifest(st: dict, manifest: dict) -> None:
    attempts = [a for arr in (manifest.get("calls") or {}).values()
                for a in arr if isinstance(a, dict) and "attempt" in a]
    if any(a.get("attempt", 1) > 1 for a in attempts):
        st["retried"] += 1
    if any("独有词" in e for a in attempts for e in (a.get("errors") or [])):
        st["leak_blocked"] += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--prompts-dir", required=True)
    ap.add_argument("--mode", choices=("dry", "real"), default="dry")
    ap.add_argument("--arm", choices=("sanshu", "facts_baseline"), default="sanshu")
    ap.add_argument("--cap", type=int, default=90)
    ap.add_argument("--verify-lock", default="")
    args = ap.parse_args()

    reports = ROOT / "evals" / "change" / "reports"
    case_body = Path(args.cases).read_text(encoding="utf-8")
    cases = [json.loads(l) for l in case_body.splitlines() if l.strip()]
    ids = [c.get("id") for c in cases]

    # ── real 预检(整改③):未过预检不构造任何供应商 caller ──
    if args.mode == "real":
        problems = []
        if not args.verify_lock:
            problems.append("缺 --verify-lock(real 必须锁定冻结用例集)")
        else:
            lock = json.loads(Path(args.verify_lock).read_text(encoding="utf-8"))
            if sha(case_body) != lock.get("sha256"):
                problems.append("用例集与冻结哈希不符")
            if lock.get("n") != len(cases) or len(set(ids)) != len(ids):
                problems.append("用例数量/ID 唯一性与 lock 不符")
        if not (reports.parent / APPROVAL_FILE).exists():
            problems.append(f"缺本人批准文件 {APPROVAL_FILE}(门槛未获批,机器不得自行放行)")
        if args.arm == "facts_baseline" and not (
                ROOT / "evals" / "change" / "baseline_prompts" / "facts-only-v1.md").exists():
            problems.append("基线提示词未合入(p19b),基线臂不可 real")
        if problems:
            print("NOT-A-GATE · real 预检未通过,未发起任何调用:")
            for p in problems:
                print(" -", p)
            return 3
    elif args.verify_lock:
        lock = json.loads(Path(args.verify_lock).read_text(encoding="utf-8"))
        if sha(case_body) != lock.get("sha256"):
            print(f"用例集与冻结哈希不符,拒跑(expected {lock['sha256'][:12]}…)")
            return 2

    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{args.arm}"
    raw_dir, run_id = _unique_run_dir(reports, stem)
    try:
        prompts = load_prompts(Path(args.prompts_dir))
    except FileNotFoundError:
        if args.mode != "dry":
            raise
        prompts = dict.fromkeys(("bazi", "gua", "combined"), "DRY_PIPELINE_PLACEHOLDER_SYSTEM")
    budget = {"left": args.cap}
    rl_words = redline_words()
    stats: dict = {}
    dims: dict = {}
    attempted = 0
    for provider, model in PROVIDERS:
        st = stats.setdefault(provider, {"n": 0, "valid_first": 0, "retried": 0, "failed": 0,
                                         "abstain": 0, "leak_blocked": 0, "leak_retained": 0,
                                         "redline": 0})
        for case in cases:
            attempted += 1
            st["n"] += 1
            dim = dims.setdefault((provider, case.get("method", "-"), case.get("scene", "-")),
                                  {"n": 0, "ok": 0, "abstain": 0, "failed": 0})
            dim["n"] += 1
            as_of = shanghai_as_of()
            try:
                cast = build_cast(case) if args.arm == "sanshu" else None
                caller = (dry_caller_factory(so.seal(cast) if cast else "-",
                                             case.get("method", "-"),
                                             deadline=case["deadline"], as_of=as_of)
                          if args.mode == "dry"
                          else real_caller_factory(provider, model, budget))
                if args.arm == "facts_baseline":
                    r = run_facts_baseline(caller, provider, case)
                else:
                    r = so.run_provider_chain(
                        caller, provider, prompts, case["question"], case["deadline"],
                        case["bazi_material"], cast, case["method"],
                        facts_summary=case.get("facts_summary", ""),
                        facts_meta={"known_at": "2026-08-30", "confirmed_at": "2026-08-31"})
            except so.OrchestrationError as exc:  # 整改②:失败保留审计回执并入统计
                st["failed"] += 1
                dim["failed"] += 1
                _bump_from_manifest(st, getattr(exc, "manifest", {}) or {})
                (raw_dir / f"failed-{provider}-{case['id']}.json").write_text(
                    json.dumps({"error": str(exc), "manifest": getattr(exc, "manifest", {})},
                               ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            _bump_from_manifest(st, r.get("manifest") or {})
            if not any(a.get("attempt", 1) > 1
                       for arr in (r.get("manifest", {}).get("calls") or {}).values()
                       for a in arr if isinstance(a, dict)):
                st["valid_first"] += 1
            ok_any = False
            for name, sec in (("bazi", r["bazi"]), ("gua", r["gua"]), ("combined", r["combined"])):
                if isinstance(sec, dict) and sec.get("status") == "abstain":
                    st["abstain"] += 1
                    dim["abstain"] += 1
                if isinstance(sec, dict):
                    ok_any = ok_any or sec.get("status") == "ok"
                    blob = json.dumps(sec, ensure_ascii=False)
                    st["redline"] += sum(1 for w in rl_words if w in blob)
                    banned = (sv.GUA_ONLY_TERMS if name == "bazi"
                              else (sv.BAZI_ONLY_TERMS if name == "gua" else ()))
                    st["leak_retained"] += len(sv.scan_banned(sec, banned))
            if ok_any:
                dim["ok"] += 1
            (raw_dir / f"{provider}-{case['id']}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.mode == "dry":
            break  # 干跑验管道,一家即可(覆盖闸仅对 real 生效)
    coverage_full = attempted == len(PROVIDERS) * len(cases)
    rates = {p: (s["valid_first"] / s["n"] if s["n"] else 0) for p, s in stats.items()}
    spread = (max(rates.values()) - min(rates.values())) if len(rates) > 1 else 0.0
    lines = [f"# Change Eval 聚合 · arm={args.arm} · mode={args.mode} · {run_id}", "",
             "| provider | n | valid_first | retried | failed | abstain | leak_blocked | leak_retained | redline |",
             "|---|---|---|---|---|---|---|---|---|"]
    for p, s in stats.items():
        lines.append(f"| {p} | {s['n']} | {s['valid_first']} ({rates[p]:.0%}) | {s['retried']} "
                     f"| {s['failed']} | {s['abstain']} | {s['leak_blocked']} "
                     f"| {s['leak_retained']} | {s['redline']} |")
    lines += ["", "## 分层维度(provider×method×scene)",
              "| provider | method | scene | n | ok | abstain | failed |",
              "|---|---|---|---|---|---|---|"]
    for (p, m, sc), d in sorted(dims.items()):
        lines.append(f"| {p} | {m} | {sc} | {d['n']} | {d['ok']} | {d['abstain']} | {d['failed']} |")
    gates = {"valid_rate>=0.80": all(v >= 0.80 for v in rates.values()),
             "redline==0": all(s["redline"] == 0 for s in stats.values()),
             "leak_after_validator==0": all(s["leak_retained"] == 0 for s in stats.values()),
             "provider_spread<=0.20": spread <= 0.20,
             "coverage_full_3x_all_cases": coverage_full}
    schema_path = ROOT / "consult-engine" / "schemas" / "sanshu-sealed-v1.json"
    hashes = {"cases_sha256": sha(case_body),
              "lock_sha256": (sha(Path(args.verify_lock).read_text(encoding="utf-8"))
                              if args.verify_lock else None),
              "prompts": {k: sha(v) for k, v in prompts.items()},
              "runner_code": sha(Path(__file__).read_text(encoding="utf-8")),
              "schema": sha(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None,
              "providers": PROVIDERS, "redline_words_loaded": len(rl_words)}
    lines += ["", f"对称性极差:{spread:.2f}",
              "门槛判定(草案,未经独立评审与本人确认不生效):" + json.dumps(gates, ensure_ascii=False),
              "结论:" + ("DRY-PIPELINE-ONLY(非门槛判定,不得用于放行)" if args.mode == "dry"
                       else ("PASS(草案门槛;须独立评审与本人确认后方有效)" if all(gates.values())
                             else "FAIL")),
              "", "输入指纹:" + json.dumps(hashes, ensure_ascii=False),
              "说明:abstain 只披露不设门槛;弃答/失败均入分母披露;逐例原文在 raw/<run_id>/ 不传阅。"]
    with (reports / f"{run_id}-manifest.json").open("x", encoding="utf-8") as mf:  # raw/ 外,写一次
        mf.write(json.dumps({"run_id": run_id, "arm": args.arm, "mode": args.mode, "gates": gates,
                             "hashes": hashes, "stats": stats}, ensure_ascii=False, indent=1))
    out = reports / f"{run_id}-summary.md"
    with out.open("x", encoding="utf-8") as f:  # 写一次,绝不覆盖
        f.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n聚合报告:{out}")
    if args.mode == "dry":
        return 0
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
