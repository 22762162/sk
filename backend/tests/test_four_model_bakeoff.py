from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "evals" / "four_model_bakeoff" / "run_bakeoff.py"
SPEC = importlib.util.spec_from_file_location("run_bakeoff", MODULE_PATH)
assert SPEC and SPEC.loader
run_bakeoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_bakeoff
SPEC.loader.exec_module(run_bakeoff)


class FourModelBakeoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = run_bakeoff.load_config()
        self.questions = run_bakeoff.build_question_bank(self.config)

    def test_frozen_bank_has_exact_category_quotas_and_four_unique_options(self) -> None:
        self.assertEqual(len(self.questions), 60)
        self.assertEqual(
            Counter(item["category"] for item in self.questions),
            Counter(self.config["categories"]),
        )
        self.assertEqual(len({item["id"] for item in self.questions}), 60)
        for item in self.questions:
            self.assertEqual(len(item["semantic_options"]), 4)
            self.assertEqual(len(set(item["semantic_options"])), 4)
            self.assertIn(item["correct"], item["semantic_options"])

    def test_materialization_is_repeatable_and_hides_expected_answers(self) -> None:
        first = run_bakeoff.materialize_questions(self.questions, self.config, "模型A", 0)
        second = run_bakeoff.materialize_questions(self.questions, self.config, "模型A", 0)
        self.assertEqual(first, second)
        public = run_bakeoff.public_batch(first[:15])
        self.assertEqual(len(public), 15)
        self.assertNotIn("expected_choice", json.dumps(public, ensure_ascii=False))
        self.assertNotIn("expected_value", json.dumps(public, ensure_ascii=False))
        for item in first:
            self.assertIn(item["expected_choice"], "ABCD")
            self.assertEqual(item["options"][item["expected_choice"]], item["expected_value"])

    def test_answer_parser_scores_content_but_flags_order_or_schema_errors(self) -> None:
        expected = ["Q1", "Q2"]
        valid = '{"answers":[{"id":"Q1","answer":"A"},{"id":"Q2","answer":"D"}]}'
        answers, schema_valid, errors = run_bakeoff.parse_answers(valid, expected)
        self.assertEqual(answers, {"Q1": "A", "Q2": "D"})
        self.assertTrue(schema_valid)
        self.assertEqual(errors, [])

        reordered = '{"answers":[{"id":"Q2","answer":"D"},{"id":"Q1","answer":"A"}]}'
        answers, schema_valid, errors = run_bakeoff.parse_answers(reordered, expected)
        self.assertEqual(answers, {"Q2": "D", "Q1": "A"})
        self.assertFalse(schema_valid)
        self.assertIn("order_mismatch", errors)

        fenced = '```json\n{"answers":[{"id":"Q1","answer":"A"},{"id":"Q2","answer":"D"}]}\n```'
        answers, schema_valid, errors = run_bakeoff.parse_answers(fenced, expected)
        self.assertEqual(answers, {"Q1": "A", "Q2": "D"})
        self.assertFalse(schema_valid)
        self.assertEqual(errors, ["response_not_strict_json"])

    def test_dry_run_writes_nothing_and_exposes_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            result = run_bakeoff.run(output, dry_run=True)
            self.assertFalse(output.exists())
            self.assertEqual(result["question_count"], 60)
            self.assertEqual(len(result["config_hash"]), 64)
            self.assertEqual(len(result["question_bank_hash"]), 64)
            self.assertEqual(set(result["model_blind_map"]), {"模型A", "模型B", "模型C", "模型D"})

    def test_summary_marks_only_complete_models_eligible(self) -> None:
        state = run_bakeoff._new_checkpoint(self.config, self.questions)
        blind_id = "模型A"
        state["runs"][blind_id] = {}
        batch_size = self.config["batch_size"]
        for repetition in range(self.config["repetitions"]):
            items = run_bakeoff.materialize_questions(self.questions, self.config, blind_id, repetition)
            for start in range(0, len(items), batch_size):
                batch_number = start // batch_size
                state["runs"][blind_id][run_bakeoff._batch_key(repetition, batch_number)] = {
                    "status": "success",
                    "schema_valid": True,
                    "decoded_answers": {
                        item["id"]: item["expected_value"] for item in items[start:start + batch_size]
                    },
                    "latency_seconds": 1.0,
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
        summary = run_bakeoff.summarize(state, self.config, self.questions)
        row = summary["models"][blind_id]
        self.assertTrue(row["ranking_eligible"])
        self.assertEqual(row["exact_choice_accuracy"], 1.0)
        self.assertEqual(row["cross_repeat_stability"], 1.0)
        self.assertEqual(row["schema_valid_rate"], 1.0)
        self.assertFalse(summary["models"]["模型B"]["ranking_eligible"])


if __name__ == "__main__":
    unittest.main()
