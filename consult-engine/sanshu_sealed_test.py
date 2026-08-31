"""三段封存编排/校验测试(RFC-0004;含 Codex 合成探针回归)。纯合成,零真实调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sanshu_orchestrator as so  # noqa: E402
import sanshu_validator as sv  # noqa: E402

def OK_EVENT():
    """工厂:每次全新深层结构,防跨用例共享污染。"""
    return {"statement": "本月签约数达到目标值以上",
            "window": {"start": "2026-09-01", "end": "2026-09-30"},
            "metric": {"indicator": "签约数", "comparator": ">=", "threshold": 3, "unit": "单"},
            "adjudication": "以合同系统当月记录为准判定"}


def ok_bazi():
    return {"status": "ok", "reading": "流月对事业有推进之象,宜主动出击" + "细" * 10,
            "confidence": "medium", "yingqi": {"start": "2026-09-01", "end": "2026-09-30"},
            "verifiable_events": [OK_EVENT()], "method_basis": "取月令与事业宫互动为据"}


def ok_gua(method="liuyao", cast_hash=""):
    return {"status": "ok", "reading": "世爻得日辰生扶,本卦水火既济动而向需,事可成但防反复" + "细" * 5,
            "confidence": "high", "yingqi": {"start": "2026-09-05", "end": "2026-09-20"},
            "verifiable_events": [OK_EVENT()], "method_basis": "取世爻旺衰与动变为据",
            "method": method, "cast_hash": cast_hash}


def ok_combined():
    return {"status": "ok", "answer": "本月推进此事总体可成,九月中旬前后落定概率较大",
            "reading": None, "reasoning": "两法同指九月且卦象更具体,采信卦象窗口并以八字定强度" + "证" * 5,
            "confidence": "high", "yingqi": {"start": "2026-09-05", "end": "2026-09-20"},
            "verifiable_events": [OK_EVENT()], "method_basis": "两法窗口交集",
            "dissent_note": ""}


def _combined_valid():
    c = ok_combined()
    c.pop("reading")
    return c


# ── Codex 探针回归 ──

def test_probe_fake_calendar_date_rejected():
    b = ok_bazi()
    b["yingqi"] = {"start": "2026-99-99", "end": "2026-99-99"}
    assert any("真实历法" in e for e in sv.validate_bazi(b))


def test_probe_nan_threshold_rejected():
    b = ok_bazi()
    b["verifiable_events"][0]["metric"]["threshold"] = float("nan")
    assert any("有限数值" in e for e in sv.validate_bazi(b))
    b["verifiable_events"][0]["metric"]["threshold"] = float("inf")
    assert any("有限数值" in e for e in sv.validate_bazi(b))


def test_probe_abstain_cannot_carry_conclusion():
    c = {"status": "abstain", "reason": "卦象与八字指向相反且无充分依据",
         "answer": "偷偷夹带的结论内容", "reasoning": "夹带推理" * 5}
    errs = sv.validate_combined(c, "low", "low")
    assert any("不得携带判断字段" in e for e in errs)


def test_probe_unhashable_confidence_controlled():
    b = ok_bazi()
    b["confidence"] = []
    errs = sv.validate_bazi(b)  # 不抛 TypeError
    assert any("confidence" in e for e in errs)
    c = _combined_valid()
    c["confidence"] = {}
    errs = sv.validate_combined(c, "high", "high")
    assert any("confidence" in e for e in errs)


def test_handover_gua_abstain_metadata_layering():
    """交接保留项1:gua 合法弃答须带 method/cast_hash(元数据层),不得被弃答白名单拒。"""
    ok = {"status": "abstain", "reason": "动爻信息不足以取定用神",
          "method": "liuyao", "cast_hash": "h1"}
    assert not sv.validate_gua(ok, "liuyao", "h1")
    missing = {"status": "abstain", "reason": "动爻信息不足以取定用神"}
    errs = sv.validate_gua(missing, "liuyao", "h1")
    assert any("method" in e or "cast_hash" in e for e in errs)  # 缺元数据仍拒
    smuggle = {**ok, "reading": "夹带判断" + "字" * 20}
    assert any("不得携带判断字段" in e for e in sv.validate_gua(smuggle, "liuyao", "h1"))


def test_handover_comparator_threshold_dependency():
    """交接保留项2:>=/<=/== 必配有限阈值;发生/未发生不得带阈值。"""
    b = ok_bazi()
    b["verifiable_events"][0]["metric"] = {"indicator": "签约数", "comparator": ">=",
                                           "threshold": None, "unit": "单"}
    assert any("必须配有限数值" in e for e in sv.validate_bazi(b))
    b2 = ok_bazi()
    b2["verifiable_events"][0]["metric"] = {"indicator": "签约事件", "comparator": "发生",
                                            "threshold": 1, "unit": None}
    assert any("不得携带 threshold" in e for e in sv.validate_bazi(b2))
    b3 = ok_bazi()
    b3["verifiable_events"][0]["metric"] = {"indicator": "签约事件", "comparator": "发生",
                                            "threshold": None, "unit": None}
    assert not sv.validate_bazi(b3)


def test_handover_pollution_heuristic_known_false_positive():
    """交接保留项4:干支密度≥2 为候选启发式——两个合法时间条件会被误伤,留档为已知局限。"""
    legit = "甲辰年签的合同乙巳年到期,本月能否顺利续约"
    hits = so.check_pollution(legit)
    assert any("干支复合词" in h for h in hits)  # 已知误伤:阈值/豁免留成品验收调整


# ── 校验器核心 ──

def test_cross_section_banwords():
    b = ok_bazi()
    b["reading"] = "此月得力,世爻旺相直指变卦向好" + "细" * 8
    assert any("卦象独有词" in e for e in sv.validate_bazi(b))
    g = ok_gua(cast_hash="h1")
    g["reading"] = "大运正官透出,流月扶身,事可成" + "细" * 8
    assert any("八字独有词" in e for e in sv.validate_gua(g, "liuyao", "h1"))
    # 共享词不误杀:干支月建日辰在 gua 段合法
    g2 = ok_gua(cast_hash="h1")
    g2["reading"] = "申月甲子日,世爻得日辰拱扶,本卦既济稳中有进" + "细" * 6
    assert not [e for e in sv.validate_gua(g2, "liuyao", "h1") if "独有词" in e]


def test_combined_confidence_cap():
    c = _combined_valid()
    c["confidence"] = "high"
    assert any("不得高于" in e for e in sv.validate_combined(c, "low", "medium"))
    assert not sv.validate_combined(_combined_valid(), "low", "high")


def test_method_and_cast_hash_echo():
    g = ok_gua(method="liuyao", cast_hash="expected")
    assert not sv.validate_gua(g, "liuyao", "expected")
    assert any("cast_hash" in e for e in sv.validate_gua(g, "liuyao", "other"))
    assert any("method" in e for e in sv.validate_gua(g, "meihua", "expected"))


# ── 编排器 ──

CAST = {"ben": {"name": "水火既济"}, "bian": {"name": "水天需"}, "hu": "火水未济",
        "yao": [], "rules_version": "liuyao-rules-v1"}
PROMPTS = {"bazi": "占位system-八字", "gua": "占位system-卦", "combined": "占位system-综合"}


def make_caller(script: dict, log: list):
    def caller(role, system, user):
        log.append({"role": role, "system": system, "user": user})
        return json.dumps(script[role], ensure_ascii=False), f"run-{role}-{len(log)}"
    return caller


def test_orchestrator_happy_path_and_isolation():
    log: list = []
    ch = so.seal(CAST)
    caller = make_caller({"bazi": ok_bazi(), "gua": ok_gua(cast_hash=ch),
                          "combined": _combined_valid()}, log)
    r = so.run_provider_chain(caller, "anthropic", PROMPTS, "本月能否谈成新合作", "2026-09-30",
                              "乾造:某年某月(合成占位材料)", CAST, "liuyao",
                              facts_summary="上月完成率八成(合成)", facts_meta={"known_at": "2026-08-30"})
    assert r["combined_status"] == "ok" and r["bazi_seal"] and r["gua_seal"]
    # 物理隔离:bazi 调用不含卦快照;gua 调用不含八字材料;combined 只见封存段
    bazi_call = next(c for c in log if c["role"] == "bazi")
    gua_call = next(c for c in log if c["role"] == "gua")
    comb_call = next(c for c in log if c["role"] == "combined")
    assert "卦快照" not in bazi_call["user"] and "既济" not in bazi_call["user"]
    assert "八字材料" not in gua_call["user"] and "乾造" not in gua_call["user"]
    assert "八字材料" not in comb_call["user"] and "卦快照" not in comb_call["user"]
    assert r["bazi_seal"] in comb_call["user"] and r["gua_seal"] in comb_call["user"]
    # 共同事实背景三段同发且留痕(不称纯术数)
    assert all("共同事实背景" in c["user"] for c in log)
    assert r["manifest"]["with_shared_facts_background"] is True
    assert r["manifest"]["facts_exposure"]["gua"] == "shared_summary"
    # 事件由编排器补发 event_id
    assert all(e["event_id"].startswith("ev-") for e in r["bazi"]["verifiable_events"])
    # 四时间戳要素
    assert r["manifest"]["facts_meta"]["frozen_at"] and r["manifest"]["first_call_at"]


def test_orchestrator_pollution_refused():
    caller = make_caller({}, [])
    try:
        so.run_provider_chain(caller, "x", PROMPTS, "我八字甲子乙丑,问本卦吉凶", "2026-09-30",
                              "材料", CAST, "liuyao")
        raise AssertionError("应拒绝")
    except so.OrchestrationError as e:
        assert "夹带" in str(e)


def test_orchestrator_absent_gua_stops_combined():
    log: list = []
    caller = make_caller({"bazi": ok_bazi()}, log)
    r = so.run_provider_chain(caller, "x", PROMPTS, "问事", "2026-09-30", "材料", None, None)
    assert r["gua"] is None and r["combined_status"] == "not_run_missing_material"
    assert [c["role"] for c in log] == ["bazi"]  # 缺席由编排器判定,不发起 gua/combined


def test_orchestrator_abstain_counts_present_but_stops_combined():
    log: list = []
    ch = so.seal(CAST)
    caller = make_caller({"bazi": ok_bazi(),
                          "gua": {"status": "abstain", "reason": "动爻信息不足以取定",
                                  "method": "liuyao", "cast_hash": ch}}, log)
    r = so.run_provider_chain(caller, "x", PROMPTS, "问事", "2026-09-30", "材料", CAST, "liuyao")
    assert r["gua"]["status"] == "abstain"
    assert r["combined_status"] == "not_run_section_abstained"


def test_orchestrator_claiming_other_hexagram_rejected_with_retry():
    ch = so.seal(CAST)
    bad = ok_gua(cast_hash=ch)
    bad["reading"] = "实为乾为天之象,大吉" + "细" * 10
    calls = {"n": 0}

    def caller(role, system, user):
        if role == "gua":
            calls["n"] += 1
            return json.dumps(bad, ensure_ascii=False), f"run-{calls['n']}"
        return json.dumps(ok_bazi(), ensure_ascii=False), "run-b"
    try:
        so.run_provider_chain(caller, "x", PROMPTS, "问事", "2026-09-30", "材料", CAST, "liuyao")
        raise AssertionError("应失败")
    except so.OrchestrationError:
        assert calls["n"] == 2  # 同输入重试 1 次后 fail-closed


def test_replay_seal_stable():
    assert so.seal(ok_bazi()) == so.seal(ok_bazi())
    assert so.canonical(CAST) == so.canonical(json.loads(json.dumps(CAST)))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("三段封存测试全部通过 ✓(含 Codex 探针回归/隔离断言/矛盾拒绝/弃答与缺席路径)")
