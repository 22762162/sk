"""Independent synthetic regression probes for PR50. No gateway, secrets or real data."""

from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import liuyao
import meihua
import sanshu_orchestrator as so


def section(combined=False):
    result = {
        "status": "ok",
        "confidence": "low",
        "yingqi": {"start": "2026-09-01", "end": "2026-09-30"},
        "verifiable_events": [{
            "statement": "合成任务在规定时间内完成。",
            "window": {"start": "2026-09-01", "end": "2026-09-30"},
            "metric": {"indicator": "完成任务数", "comparator": ">=", "threshold": 1, "unit": "个"},
            "adjudication": "依据事前规定的合成任务记录核对。",
        }],
        "method_basis": "仅供程序验证的合成依据",
    }
    if combined:
        result.update(answer="此段仅为程序验证的合成回答内容。",
                      reasoning="此段仅为程序验证的合成解释不代表任何现实判断。")
    else:
        result["reading"] = "此段仅为程序验证的合成说明不代表任何现实判断。"
    return result


class CrossReviewTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        clock = mock.patch.object(so, "_now", return_value="2026-09-01T00:00:00+00:00")
        clock.start()
        self.addCleanup(clock.stop)
        if hasattr(so, "MANIFEST_DIR"):
            temp = tempfile.TemporaryDirectory(prefix="sanshu-cross-review-")
            self.addCleanup(temp.cleanup)
            output = mock.patch.object(so, "MANIFEST_DIR", Path(temp.name))
            output.start()
            self.addCleanup(output.stop)
        self.cast = liuyao.cast([7, 8, 7, 8, 7, 8], "甲子", "子")
        # Engineering placeholders only, not candidate/runtime prompt content.
        self.prompts = dict.fromkeys(("bazi", "gua", "combined"), "SYNTHETIC_TEST_PLACEHOLDER")

    def caller(self, role, system, user):
        self.calls.append({"role": role, "system": system, "user": user})
        data = section(combined=role == "combined")
        if role == "gua":
            meta = re.search(r"method=([^,]+),cast_hash=([^\)]+)", user)
            data.update(method=meta[1], cast_hash=None if meta[2] == "None" else meta[2])
        return json.dumps(data, ensure_ascii=False), f"synthetic-run-{len(self.calls)}"

    def run_chain(self, **overrides):
        kwargs = dict(caller=self.caller, provider="anthropic", prompts=self.prompts,
                      question="这个月任务进展如何", deadline="2026-09-30",
                      bazi_material="合成材料标记 NATAL_SENTINEL", cast_snapshot=self.cast,
                      method="liuyao")
        kwargs.update(overrides)
        return so.run_provider_chain(**kwargs)

    def test_baseline_three_calls(self):
        self.assertEqual(self.run_chain()["combined_status"], "ok")
        self.assertEqual([c["role"] for c in self.calls], ["bazi", "gua", "combined"])

    def test_meihua_engine_snapshot_is_accepted(self):
        result = self.run_chain(cast_snapshot=meihua.cast_numbers(5, 8, "子"), method="meihua")
        self.assertEqual(result["combined_status"], "ok")

    def test_shape_only_cast_is_not_trusted(self):
        shaped = {"rules_version": "liuyao-rules-v1", "ben": {"name": "水火既济"}, "yao": [None] * 6}
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(cast_snapshot=shaped)
        self.assertEqual(self.calls, [])

    def test_engine_snapshot_tampering_is_rejected(self):
        changed = copy.deepcopy(self.cast)
        changed["yao"][0]["liuqin"] = "INVALID_SYNTHETIC_VALUE"
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(cast_snapshot=changed)
        self.assertEqual(self.calls, [])

    def test_window_start_cannot_precede_frozen_window(self):
        data = section()
        data["yingqi"]["start"] = "1900-01-01"
        self.assertTrue(so._windows_within(data, "2026-09-01", "2026-09-30"))

    def test_manifest_write_failure_prevents_success(self):
        with mock.patch.object(Path, "mkdir", side_effect=OSError("synthetic read-only storage")):
            with self.assertRaises(so.OrchestrationError):
                self.run_chain()

    def test_returned_sections_match_their_seals(self):
        result = self.run_chain()
        for name in ("bazi", "gua"):
            self.assertEqual(result[f"{name}_seal"], so.seal(result[name]))

    def test_invalid_cast_is_rejected_before_any_call(self):
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(cast_snapshot={"unexpected": "not-an-engine-snapshot"})
        self.assertEqual(self.calls, [])

    def test_method_mismatch_is_rejected_before_any_call(self):
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(method="meihua")
        self.assertEqual(self.calls, [])

    def test_deadline_is_not_a_cross_method_material_channel(self):
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(deadline="2026-09-30\n【八字材料】日主甲木 NATAL_SENTINEL")
        self.assertEqual(self.calls, [])

    def test_future_known_facts_are_rejected_before_any_call(self):
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(facts_summary="仅供合成测试的事实背景。",
                           facts_meta={"known_at": "2099-01-01T00:00:00Z",
                                       "confirmed_at": "2099-01-01T00:00:00Z"})
        self.assertEqual(self.calls, [])

    def test_events_cannot_exceed_question_deadline(self):
        with self.assertRaises(so.OrchestrationError):
            self.run_chain(deadline="2026-09-10")

    def test_missing_bazi_never_calls_bazi_or_combined(self):
        try:
            self.run_chain(bazi_material="")
        except so.OrchestrationError:
            pass
        self.assertFalse(any(c["role"] in {"bazi", "combined"} for c in self.calls))

    def test_caller_exception_is_controlled_and_has_audit_receipt(self):
        def failing(*args):
            raise TimeoutError("synthetic timeout")
        with self.assertRaises(so.OrchestrationError) as caught:
            self.run_chain(caller=failing)
        self.assertTrue(getattr(caught.exception, "manifest", None))

    def test_invalid_outputs_keep_attempt_receipts(self):
        def invalid(*args):
            self.calls.append(args)
            return "not-json", f"synthetic-invalid-{len(self.calls)}"
        with self.assertRaises(so.OrchestrationError) as caught:
            self.run_chain(caller=invalid)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(getattr(caught.exception, "manifest", None))

    def test_combined_abstention_not_marked_success(self):
        def abstaining(role, system, user):
            if role == "combined":
                self.calls.append({"role": role, "system": system, "user": user})
                return json.dumps({"status": "abstain", "reason": "合成依据不足以形成结论。"}), "synthetic-abstain"
            return self.caller(role, system, user)
        result = self.run_chain(caller=abstaining)
        self.assertEqual(result["combined_status"], "abstain")

    def test_snapshot_is_frozen_before_first_call(self):
        original = copy.deepcopy(self.cast)
        def mutating(role, system, user):
            if role == "bazi":
                self.cast["day_ganzhi"] = "乙丑"
            return self.caller(role, system, user)
        self.run_chain(caller=mutating)
        gua_user = next(c["user"] for c in self.calls if c["role"] == "gua")
        self.assertIn(so.canonical(original), gua_user)


if __name__ == "__main__":
    unittest.main(verbosity=2)
