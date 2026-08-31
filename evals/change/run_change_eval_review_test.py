"""Independent synthetic P19 review probes: no gateway calls or real records.

P19 depends on P18. Before integration, run with the reviewed P18 consult-engine
directory on PYTHONPATH. Expected failures are evidence, never xfailed or waived.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    "reviewed_change_runner", Path(__file__).with_name("run_change_eval.py"))
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


class ChangeEvalReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sk-p19-review-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.case = {
            "id": "synthetic-review-1", "scene": "personal", "domain": "进度",
            "method": "meihua", "question": "本月合成项目能否完成", "deadline": "2026-09-10",
            "bazi_material": "合成命盘材料，仅用于隔离测试，不含个人数据",
            "n1": 12, "n2": 28, "hour_branch": "午", "facts_summary": "",
        }
        self.cases = self.root / "cases.jsonl"
        self.cases.write_text(json.dumps(self.case, ensure_ascii=False) + "\n", encoding="utf-8")

    def invoke(self, *, mode="dry", chain=None):
        argv = ["run_change_eval.py", "--cases", str(self.cases), "--prompts-dir", str(self.root),
                "--mode", mode, "--arm", "sanshu", "--cap", "12"]
        buf = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, "ROOT", self.root))
            stack.enter_context(patch.object(runner, "load_prompts", return_value={
                k: "synthetic test instruction" for k in ("bazi", "gua", "combined")}))
            # A fake factory makes accidental model traffic impossible even for CLI mode=real.
            factory = stack.enter_context(patch.object(runner, "real_caller_factory", return_value=None))
            if chain is not None:
                stack.enter_context(patch.object(runner.so, "run_provider_chain", side_effect=chain))
            stack.enter_context(patch.object(sys, "argv", argv))
            stack.enter_context(contextlib.redirect_stdout(buf))
            result = runner.main()
        return result, buf.getvalue(), factory.call_count

    @staticmethod
    def success(*args, **kwargs):
        return {"provider": args[1], "bazi": None, "gua": None,
                "combined": {"status": "abstain", "reason": "synthetic review only"},
                "combined_status": "abstain", "manifest": {"calls": {
                    "combined": [{"attempt": 1, "ok": True}]}}}

    @staticmethod
    def failure(*args, **kwargs):
        raise runner.so.OrchestrationError("synthetic validation failure", {
            "calls": {"bazi": [
                {"attempt": 1, "ok": False, "errors": ["独有词泄漏"]},
                {"attempt": 2, "ok": False, "errors": ["独有词泄漏"]}]}})

    def test_baseline_rejects_the_same_out_of_deadline_window(self):
        caller = runner.dry_caller_factory("synthetic-hash", "meihua")
        with self.assertRaises(runner.so.OrchestrationError):
            runner.run_facts_baseline(caller, "synthetic-provider", self.case)

    def test_failed_case_keeps_auditable_receipt(self):
        self.invoke(chain=self.failure)
        receipts = list((self.root / "evals/change/reports/raw").glob("**/*.json"))
        self.assertEqual(1, len(receipts), "failed cases must not disappear from raw audit receipts")

    def test_failed_retry_is_in_aggregate_counts(self):
        _, report, _ = self.invoke(chain=self.failure)
        row = next(line for line in report.splitlines() if line.startswith("| anthropic |"))
        cells = [value.strip() for value in row.strip("|").split("|")]
        self.assertEqual("1", cells[3], "retried failures must count in retried, not only failed")
        self.assertEqual("1", cells[6], "blocked leakage must include ultimately failed cases")

    def test_real_mode_requires_frozen_gate_before_any_provider(self):
        result, report, factory_calls = self.invoke(mode="real", chain=self.success)
        self.assertEqual(0, factory_calls, "unlocked/unapproved real evaluation must stop in preflight")
        self.assertNotEqual(0, result)
        self.assertNotIn("PASS(", report)

    def test_same_second_runs_do_not_overwrite_evidence(self):
        class FrozenDateTime:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        with patch.object(runner, "datetime", FrozenDateTime):
            self.invoke(chain=self.success)
            self.invoke(chain=self.success)
        reports = list((self.root / "evals/change/reports").glob("*-summary.md"))
        self.assertEqual(2, len(reports), "each invocation must retain a unique immutable report")


if __name__ == "__main__":
    unittest.main()
