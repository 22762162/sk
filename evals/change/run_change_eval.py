"""sanshu 三段封存 · Change Eval 执行器 v3(P19 全范围整改;INV-12:与候选/基线提示词永不同 PR)。

v3 增改(pr51 审查六条+7 探针):
1 红线词表 fail-closed:redline_words() 缺失/空表即抛错;real 预检拒绝,dry 显式降级并标注;
2 批准文件=可校验协议:JSON 内容含 approved_by/thresholds/budget/bindings(代码/提示词/schema/
  用例/编排器/校验器版本哈希逐一绑定),空文件/缺键/哈希不符一律拒;阈值取自批准内容,不再硬编码;
3 as_of 运行级冻结一次,显式传入 dry-caller/基线/编排器(编排器 as_of 参数,P18 增量);
4 弃答按段分列(bazi/gua/combined),coverage 按"完成或留回执"计且预算耗尽即失效;
  real 结论不出现 PASS 字样,恒标 NOT-A-GATE(整体放行须本人复核);
5 用例集版本化:v100.1(历史保留)/v100.2(三个月内标签修正),生成器拒绝覆写既有版本;
6 运行配置(全部哈希/版本/模型)起跑前冻结入 run_config,manifest 由冻结件生成;real 记录用量。
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
APPROVAL_FILE = "thresholds-approved.yaml"  # 本人手工提交的 JSON 协议;机器永不写入
_DRAFT_THRESHOLDS = {"valid_rate_min": 0.80, "spread_max": 0.20,
                     "redline_max": 0, "leak_max": 0}  # 仅 dry 展示用草案


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def shanghai_today() -> str:
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
    """红线词表:缺失或空表**抛错**(fail-closed,7 探针);调用方决定各模式的处置。"""
    path = ROOT / "infra" / "compliance" / "redline-words.txt"
    words = [w.strip() for w in path.read_text(encoding="utf-8").splitlines()
             if w.strip() and not w.startswith("#")]  # 缺文件 → OSError 直接上抛
    if not words:
        raise RuntimeError("红线词表为空:安全策略缺失,拒绝继续")
    return words


def dry_caller_factory(cast_hash: str, method: str, deadline: str = "2026-09-30",
                       as_of: str | None = None):
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
            budget["exhausted"] = True
            raise so.OrchestrationError("Change Eval 调用预算耗尽")
        budget["left"] -= 1
        text, run_id, usage = gateway.call(provider, model, system=system, user=user,
                                           temperature=-1, max_tokens=2500,
                                           output_schema_version="sanshu-eval-v1")
        if isinstance(usage, dict):  # 实际用量入账(第 6 条)
            budget["usage_in"] += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            budget["usage_out"] += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        return text, run_id
    return caller


def run_facts_baseline(caller, provider: str, case: dict, as_of: str | None = None) -> dict:
    """消融基线臂:窗口/事件校验与主链同一 as_of/deadline;as_of 由执行器冻结传入
    (独立直调时才就地推导,供评审探针)。"""
    as_of = as_of or shanghai_today()
    deadline = case["deadline"]
    prompt_file = ROOT / "evals" / "change" / "baseline_prompts" / "facts-only-v1.md"
    if prompt_file.exists():
        system = prompt_file.read_text(encoding="utf-8").split("## system", 1)[-1].strip()
    else:
        system = "BASELINE_PROMPT_PENDING_P19B(占位;real 预检因缺文件中止)"
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


def _load_approval(reports_parent: Path, computed: dict) -> tuple[dict | None, list[str]]:
    """批准协议校验(第 2 条):内容、必备键、逐项版本绑定;任何不符即列问题。"""
    path = reports_parent / APPROVAL_FILE
    if not path.exists():
        return None, [f"缺本人批准文件 {APPROVAL_FILE}(门槛未获批,机器不得自行放行)"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict)
    except Exception:  # noqa: BLE001 空文件/非 JSON:占位不是签署协议
        return None, ["批准文件内容为空或非法(空文件占位不构成签署协议)"]
    problems = []
    if not str(doc.get("approved_by", "")).strip():
        problems.append("批准文件缺 approved_by")
    th = doc.get("thresholds")
    if not (isinstance(th, dict)
            and isinstance(th.get("valid_rate_min"), (int, float)) and 0 <= th["valid_rate_min"] <= 1
            and isinstance(th.get("spread_max"), (int, float))
            and th.get("redline_max") == 0 and th.get("leak_max") == 0):
        problems.append("批准文件 thresholds 缺失或不合规(redline_max/leak_max 必须为 0)")
    bud = doc.get("budget")
    if not (isinstance(bud, dict) and isinstance(bud.get("cap"), int) and bud["cap"] > 0):
        problems.append("批准文件 budget.cap 缺失或非法")
    binds = doc.get("bindings")
    if not isinstance(binds, dict):
        problems.append("批准文件缺 bindings(版本绑定)")
    else:
        for key, want in computed.items():
            if binds.get(key) != want:
                problems.append(f"bindings.{key} 与当前工件不符(批准与实物脱钩)")
    return (doc if not problems else None), problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--prompts-dir", required=True)
    ap.add_argument("--mode", choices=("dry", "real"), default="dry")
    ap.add_argument("--arm", choices=("sanshu", "facts_baseline"), default="sanshu")
    ap.add_argument("--cap", type=int, default=90)
    ap.add_argument("--verify-lock", default="")
    ap.add_argument("--as-of", default="", help="冻结锚点日期;缺省=启动时刻沪日,整场共用")
    args = ap.parse_args()

    reports = ROOT / "evals" / "change" / "reports"
    case_body = Path(args.cases).read_text(encoding="utf-8")
    cases = [json.loads(l) for l in case_body.splitlines() if l.strip()]
    ids = [c.get("id") for c in cases]
    frozen_as_of = args.as_of or shanghai_today()  # 第 3 条:运行级冻结一次,整场共用

    # ── 起跑前冻结运行配置(第 6 条) ──
    try:
        prompts = load_prompts(Path(args.prompts_dir))
        prompts_source = "candidates"
    except FileNotFoundError:
        if args.mode != "dry":
            print("NOT-A-GATE · real 预检未通过:候选提示词缺失")
            return 3
        prompts = dict.fromkeys(("bazi", "gua", "combined"), "DRY_PIPELINE_PLACEHOLDER_SYSTEM")
        prompts_source = "dry_placeholder"
    baseline_prompt = ROOT / "evals" / "change" / "baseline_prompts" / "facts-only-v1.md"
    schema_path = ROOT / "consult-engine" / "schemas" / "sanshu-sealed-v1.json"
    rl_status = "loaded"
    try:
        rl_words = redline_words()
    except (OSError, RuntimeError):
        rl_words, rl_status = [], "missing_fail_open_dry_only"
    run_config = {
        "as_of": frozen_as_of, "arm": args.arm, "mode": args.mode,
        "cases_sha256": sha(case_body),
        "lock_sha256": (sha(Path(args.verify_lock).read_text(encoding="utf-8"))
                        if args.verify_lock else None),
        "prompts": {k: sha(v) for k, v in prompts.items()}, "prompts_source": prompts_source,
        "baseline_prompt_sha256": (sha(baseline_prompt.read_text(encoding="utf-8"))
                                   if baseline_prompt.exists() else None),
        "schema": sha(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None,
        "runner_code": sha(Path(__file__).read_text(encoding="utf-8")),
        "orchestrator_version": so.ORCH_VERSION,
        "validator": {"schema": sv.SCHEMA_VERSION, "banlists": sv.BANLISTS_VERSION},
        "providers": PROVIDERS, "redline_words": {"status": rl_status, "count": len(rl_words)},
    }

    thresholds = dict(_DRAFT_THRESHOLDS)
    if args.mode == "real":
        problems = []
        if rl_status != "loaded":
            problems.append("红线词表缺失或为空:real 零调用拒绝(fail-closed,第 1 条)")
        if not args.verify_lock:
            problems.append("缺 --verify-lock(real 必须锁定冻结用例集)")
        else:
            lock = json.loads(Path(args.verify_lock).read_text(encoding="utf-8"))
            if sha(case_body) != lock.get("sha256"):
                problems.append("用例集与冻结哈希不符")
            if lock.get("n") != len(cases) or len(set(ids)) != len(ids):
                problems.append("用例数量/ID 唯一性与 lock 不符")
        approval, ap_problems = _load_approval(reports.parent, {
            "cases_sha256": run_config["cases_sha256"],
            "lock_sha256": run_config["lock_sha256"],
            "prompts": run_config["prompts"],
            "schema": run_config["schema"],
            "runner_code": run_config["runner_code"],
            "baseline_prompt_sha256": run_config["baseline_prompt_sha256"],
            "orchestrator_version": run_config["orchestrator_version"],
            "validator": run_config["validator"],
        })
        problems += ap_problems
        if args.arm == "facts_baseline" and not baseline_prompt.exists():
            problems.append("基线提示词未合入(p19b),基线臂不可 real")
        if problems:
            print("NOT-A-GATE · real 预检未通过,未发起任何调用:")
            for p in problems:
                print(" -", p)
            return 3
        thresholds = approval["thresholds"]  # 阈值取自批准内容(第 2 条)
        args.cap = min(args.cap, approval["budget"]["cap"])
    elif args.verify_lock:
        lock = json.loads(Path(args.verify_lock).read_text(encoding="utf-8"))
        if sha(case_body) != lock.get("sha256"):
            print(f"用例集与冻结哈希不符,拒跑(expected {lock['sha256'][:12]}…)")
            return 2

    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{args.arm}"
    raw_dir, run_id = _unique_run_dir(reports, stem)
    budget = {"left": args.cap, "exhausted": False, "usage_in": 0, "usage_out": 0}
    stats: dict = {}
    dims: dict = {}
    completed_or_receipt = 0
    for provider, model in PROVIDERS:
        st = stats.setdefault(provider, {"n": 0, "valid_first": 0, "retried": 0, "failed": 0,
                                         "abstain_bazi": 0, "abstain_gua": 0, "abstain_combined": 0,
                                         "leak_blocked": 0, "leak_retained": 0, "redline": 0})
        for case in cases:
            st["n"] += 1
            dim = dims.setdefault((provider, case.get("method", "-"), case.get("scene", "-")),
                                  {"n": 0, "ok": 0, "abstain": 0, "failed": 0})
            dim["n"] += 1
            try:
                cast = build_cast(case) if args.arm == "sanshu" else None
                caller = (dry_caller_factory(so.seal(cast) if cast else "-",
                                             case.get("method", "-"),
                                             deadline=case["deadline"], as_of=frozen_as_of)
                          if args.mode == "dry"
                          else real_caller_factory(provider, model, budget))
                if args.arm == "facts_baseline":
                    r = run_facts_baseline(caller, provider, case, as_of=frozen_as_of)
                else:
                    r = so.run_provider_chain(
                        caller, provider, prompts, case["question"], case["deadline"],
                        case["bazi_material"], cast, case["method"],
                        facts_summary=case.get("facts_summary", ""),
                        facts_meta={"known_at": "2026-08-30", "confirmed_at": "2026-08-31"},
                        as_of=frozen_as_of)
            except so.OrchestrationError as exc:
                st["failed"] += 1
                dim["failed"] += 1
                _bump_from_manifest(st, getattr(exc, "manifest", {}) or {})
                (raw_dir / f"failed-{provider}-{case['id']}.json").write_text(
                    json.dumps({"error": str(exc), "manifest": getattr(exc, "manifest", {})},
                               ensure_ascii=False, indent=1), encoding="utf-8")
                completed_or_receipt += 1
                continue
            _bump_from_manifest(st, r.get("manifest") or {})
            if not any(a.get("attempt", 1) > 1
                       for arr in (r.get("manifest", {}).get("calls") or {}).values()
                       for a in arr if isinstance(a, dict)):
                st["valid_first"] += 1
            ok_any = False
            for name, sec in (("bazi", r["bazi"]), ("gua", r["gua"]), ("combined", r["combined"])):
                if isinstance(sec, dict) and sec.get("status") == "abstain":
                    st[f"abstain_{name}"] += 1
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
            completed_or_receipt += 1
        if args.mode == "dry":
            break
    coverage_full = (completed_or_receipt == len(PROVIDERS) * len(cases)
                     and not budget["exhausted"])  # 第 4 条:预算耗尽=覆盖失效
    rates = {p: (s["valid_first"] / s["n"] if s["n"] else 0) for p, s in stats.items()}
    spread = (max(rates.values()) - min(rates.values())) if len(rates) > 1 else 0.0
    lines = [f"# Change Eval 聚合 · arm={args.arm} · mode={args.mode} · {run_id}",
             f"冻结 as_of:{frozen_as_of}(整场共用)", "",
             "| provider | n | valid_first | retried | failed | abstain(b/g/c) | leak_blocked | leak_retained | redline |",
             "|---|---|---|---|---|---|---|---|---|"]  # 列位契约:leak_blocked 固定第 6 列(独立探针)
    for p, s in stats.items():
        lines.append(f"| {p} | {s['n']} | {s['valid_first']} ({rates[p]:.0%}) | {s['retried']} "
                     f"| {s['failed']} | {s['abstain_bazi']}/{s['abstain_gua']}/{s['abstain_combined']} "
                     f"| {s['leak_blocked']} | {s['leak_retained']} | {s['redline']} |")
    lines += ["", "## 分层维度(provider×method×scene)",
              "| provider | method | scene | n | ok | abstain(段计) | failed |",
              "|---|---|---|---|---|---|---|"]
    for (p, m, sc), d in sorted(dims.items()):
        lines.append(f"| {p} | {m} | {sc} | {d['n']} | {d['ok']} | {d['abstain']} | {d['failed']} |")
    gates = {"valid_rate>=min": all(v >= thresholds["valid_rate_min"] for v in rates.values()),
             "redline<=max": all(s["redline"] <= thresholds["redline_max"] for s in stats.values()),
             "leak<=max": all(s["leak_retained"] <= thresholds["leak_max"] for s in stats.values()),
             "provider_spread<=max": spread <= thresholds["spread_max"],
             "coverage_full_and_budget_ok": coverage_full}
    lines += ["", f"对称性极差:{spread:.2f} · 预算余量:{budget['left']} · "
              f"用量(tok) in={budget['usage_in']} out={budget['usage_out']}",
              ("门槛判定(阈值来自批准协议):" if args.mode == "real"
               else "门槛判定(草案阈值,未经独立评审与本人确认不生效):")
              + json.dumps(gates, ensure_ascii=False),
              "结论:" + ("DRY-PIPELINE-ONLY(非门槛判定,不得用于放行)" if args.mode == "dry"
                       else ("阈值判定:达标 · NOT-A-GATE:整体放行仍须本人复核" if all(gates.values())
                             else "阈值判定:未达标")),
              "", "运行配置指纹(起跑前冻结):" + json.dumps(run_config, ensure_ascii=False),
              "说明:弃答按段分列且只披露不设门槛;弃答/失败均入分母;逐例原文在 raw/<run_id>/ 不传阅。"]
    with (reports / f"{run_id}-manifest.json").open("x", encoding="utf-8") as mf:
        mf.write(json.dumps({"run_id": run_id, "run_config": run_config, "thresholds": thresholds,
                             "gates": gates, "stats": stats,
                             "budget": budget}, ensure_ascii=False, indent=1))
    out = reports / f"{run_id}-summary.md"
    with out.open("x", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n聚合报告:{out}")
    if args.mode == "dry":
        return 0
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
