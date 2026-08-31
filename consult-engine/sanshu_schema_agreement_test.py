"""schema↔validator 一致性对照(B2 闭环):同一夹具双侧判定必须一致,已知分歧显式登记。

运行:uv run --with jsonschema --with pytest python3 -m pytest consult-engine/sanshu_schema_agreement_test.py -q
CI 于 divination job 安装 jsonschema 后执行。validator 面向模型原始输出(raw);
sealed 变体仅由编排器产出,单独做 schema 结构断言。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

jsonschema = pytest.importorskip("jsonschema")
import sanshu_validator as sv  # noqa: E402

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "sanshu-sealed-v1.json")
                    .read_text(encoding="utf-8"))
H64 = "a" * 64

# 已知且有意的分歧(schema 无法表达,由 validator 补充执行;契约描述已明示):
# real_calendar —— 2026-02-30 过日期 pattern 但非真实历法
# cross_terms  —— 跨段独有词表扫描
# conf_cap     —— combined 置信度 ≤ max(单法)
DOCUMENTED_DIVERGENCE = {"real_calendar"}


def _schema_valid(defs_name: str, obj) -> bool:
    v = jsonschema.Draft202012Validator({"$ref": f"#/$defs/{defs_name}", "$defs": SCHEMA["$defs"]})
    return not list(v.iter_errors(obj))


def _validator_valid(kind: str, obj) -> bool:
    if kind == "bazi":
        return not sv.validate_bazi(obj)
    if kind == "gua":
        return not sv.validate_gua(obj, "liuyao", H64)
    return not sv.validate_combined(obj, "high", "high")


def ok_event():
    return {"statement": "本窗口内目标事项出现明确进展", "window": {"start": "2026-09-01", "end": "2026-09-30"},
            "metric": {"indicator": "事项进展", "comparator": "发生", "threshold": None, "unit": None},
            "adjudication": "以本人当期记录为准判定发生与否"}


def ok_bazi():
    return {"status": "ok", "reading": "对照用合成八字段落内容,长度补齐" + "验" * 8,
            "confidence": "medium", "yingqi": {"start": "2026-09-01", "end": "2026-09-30"},
            "verifiable_events": [ok_event()], "method_basis": "对照用合成依据"}


def ok_gua():
    return {**ok_bazi(), "reading": "对照用合成卦段落内容,长度补齐" + "验" * 8,
            "method": "liuyao", "cast_hash": H64}


def ok_combined():
    c = ok_bazi()
    c.pop("reading")
    return {**c, "answer": "对照用合成综合回答,先给结论",
            "reasoning": "对照用合成推理内容,长度补齐" + "验" * 8, "dissent_note": ""}


CASES = [
    # (case_id, kind, obj, expect_agree_valid or ("divergence", tag))
    ("bazi_ok", "bazi", ok_bazi(), True),
    ("gua_ok", "gua", ok_gua(), True),
    ("combined_ok", "combined", ok_combined(), True),
    ("null", "bazi", None, False),
    ("empty_obj", "gua", {}, False),
    ("int_section", "gua", 123, False),
    ("missing_reading", "bazi", {k: v for k, v in ok_bazi().items() if k != "reading"}, False),
    ("wrong_type_conf", "bazi", {**ok_bazi(), "confidence": []}, False),
    ("extra_field", "bazi", {**ok_bazi(), "foo": 1}, False),
    ("abstain_ok", "bazi", {"status": "abstain", "reason": "对照用合成弃答理由"}, True),
    ("abstain_smuggle_answer", "combined",
     {"status": "abstain", "reason": "对照用合成弃答理由", "answer": "夹带的结论内容在此"}, False),
    ("gua_abstain_with_meta", "gua",
     {"status": "abstain", "reason": "对照用合成弃答理由", "method": "liuyao", "cast_hash": H64}, True),
    ("gua_abstain_missing_meta", "gua", {"status": "abstain", "reason": "对照用合成弃答理由"}, False),
    ("cmp_ge_missing_threshold", "bazi",
     {**ok_bazi(), "verifiable_events": [{**ok_event(),
      "metric": {"indicator": "签约数", "comparator": ">=", "threshold": None, "unit": "单"}}]}, False),
    ("cmp_event_with_threshold", "bazi",
     {**ok_bazi(), "verifiable_events": [{**ok_event(),
      "metric": {"indicator": "签约", "comparator": "发生", "threshold": 1, "unit": None}}]}, False),
    ("bad_month_13", "bazi", {**ok_bazi(), "yingqi": {"start": "2026-13-01", "end": "2026-13-02"}}, False),
    ("fake_calendar_0230", "bazi",
     {**ok_bazi(), "yingqi": {"start": "2026-02-30", "end": "2026-02-30"}}, ("divergence", "real_calendar")),
]


@pytest.mark.parametrize("case_id,kind,obj,expect", CASES, ids=[c[0] for c in CASES])
def test_schema_validator_agreement(case_id, kind, obj, expect):
    s_ok = _schema_valid(f"{kind}_section_raw", obj)
    v_ok = _validator_valid(kind, obj)
    if isinstance(expect, tuple):
        tag = expect[1]
        assert tag in DOCUMENTED_DIVERGENCE
        assert s_ok is True and v_ok is False, f"{case_id}: 登记分歧形态变化,须重审契约"
        return
    assert s_ok == v_ok == expect, f"{case_id}: schema={s_ok} validator={v_ok} 期望={expect}"


def test_sealed_variants_struct_bounds():
    sealed_ev = {**ok_event(), "event_id": "ev-" + "0" * 12}
    sealed_bazi = {**ok_bazi(), "verifiable_events": [sealed_ev]}
    assert _schema_valid("bazi_section_sealed", sealed_bazi)
    assert not _schema_valid("bazi_section_sealed", ok_bazi())      # 封存版缺 event_id 不合规
    assert not _schema_valid("bazi_section_raw", sealed_bazi)       # 原始版不得含 event_id
    sealed_gua = {**ok_gua(), "verifiable_events": [dict(sealed_ev)]}
    assert _schema_valid("gua_section_sealed", sealed_gua)
    sealed_comb = {**ok_combined(), "verifiable_events": [dict(sealed_ev)]}
    assert _schema_valid("combined_section_sealed", sealed_comb)
