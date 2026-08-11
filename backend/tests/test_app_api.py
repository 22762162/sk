from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


_TEMP = tempfile.TemporaryDirectory()
os.environ["SANJIAN_APP_DB"] = str(Path(_TEMP.name) / "api.sqlite3")

from fastapi.testclient import TestClient  # noqa: E402
from backend import app as backend_app  # noqa: E402


class AppApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(backend_app.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        _TEMP.cleanup()

    def test_profile_bootstrap_update_conflict_and_question_validation(self) -> None:
        synthetic = {
            "name": "合成基本盘", "birth": "1990-06-15T08:30", "gender": "male",
            "place": "合成城市", "longitude": 116.4, "timezone": "Asia/Shanghai",
            "zi_hour_mode": "split", "industry": "测试行业", "occupation": "测试岗位",
            "situation": "合成背景", "is_active": True,
        }
        created = self.client.post("/api/app/profiles", json=synthetic)
        self.assertEqual(created.status_code, 201)
        profile = created.json()["profile"]

        bootstrap = self.client.get("/api/app/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(bootstrap.json()["active_profile"]["id"], profile["id"])
        self.assertEqual(bootstrap.json()["minimum_sample_size"], 8)

        update = {**synthetic, "name": "更新后的合成盘", "expected_version": profile["version"]}
        updated = self.client.put(f"/api/app/profiles/{profile['id']}", json=update)
        self.assertEqual(updated.status_code, 200)
        conflict = self.client.put(f"/api/app/profiles/{profile['id']}", json=update)
        self.assertEqual(conflict.status_code, 409)

        invalid = self.client.post("/api/app/questions/start", json={
            "profile_id": profile["id"], "period": "day", "category": "career",
            "question": "短", "background": "",
        })
        self.assertEqual(invalid.status_code, 422)

    def test_unverified_timezone_is_rejected_instead_of_silently_miscalculated(self) -> None:
        response = self.client.post("/api/app/profiles", json={
            "name": "合成外区盘", "birth": "1992-03-01T12:00", "gender": "female",
            "timezone": "Asia/Tokyo", "zi_hour_mode": "split",
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("时区", response.json()["error"])

    def test_advanced_research_candidates_only_include_user_facts(self) -> None:
        profile = self.client.post("/api/app/profiles", json={
            "name": "资料同步合成盘", "birth": "1993-04-05T10:20", "gender": "male",
            "timezone": "Asia/Shanghai", "zi_hour_mode": "split",
        }).json()["profile"]
        synthetic_facts = [
            {"year": 2024, "text": "开始负责合成业务团队"},
            {"year": 2025, "text": "完成合成项目交付"},
        ]
        synthetic_records = [{
            "id": "consult-compatible", "saved_at": "2026-08-01T00:00:00+00:00",
            "birth": "1993-04-05T10:20", "chart_line": "合成四柱", "n_chats": 2,
        }, {
            "id": "consult-other", "saved_at": "2026-08-02T00:00:00+00:00",
            "birth": "1994-04-05T10:20", "chart_line": "另一合成盘", "n_chats": 0,
        }]
        with patch.object(backend_app.dossier, "facts", return_value=synthetic_facts), \
             patch.object(backend_app.records, "listing", return_value=synthetic_records):
            response = self.client.get(
                f"/api/app/profiles/{profile['id']}/research-candidates"
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["facts"]), 2)
        self.assertIn("2024年：开始负责合成业务团队", data["candidate_context"])
        self.assertIn("不会自动导入", data["excluded"])
        self.assertIn("大运", data["computed_each_question"])
        self.assertEqual([item["id"] for item in data["records"]], ["consult-compatible"])

    def test_historical_research_record_binds_only_to_same_birth_as_reference(self) -> None:
        profile = self.client.post("/api/app/profiles", json={
            "name": "旧记录绑定合成盘", "birth": "1993-04-05T10:20", "gender": "male",
            "timezone": "Asia/Shanghai", "zi_hour_mode": "split",
            "research_context": "2025年：完成合成项目交付", "research_source": "manual",
        }).json()["profile"]
        synthetic_record = {
            "id": "consult-compatible", "saved_at": "2026-08-01T00:00:00+00:00",
            "birth": "1993-04-05T10:20",
            "payload": {"consultation": {"plain_summary": {
                "overview": "合成旧研究，联系电话13800138000",
                "dayun": "合成大运参考",
                "consensus": "合成共识参考",
                "domains": [{"domain": "事业", "reading": "合成事业参考"}],
                "yearly": [{"year": 2027, "reading": "不应导入的逐年断语"}],
            }, "judge": {"summary": "不应导入的裁判细节"}}},
        }
        with patch.object(backend_app.records, "get", return_value=synthetic_record):
            response = self.client.post(
                f"/api/app/profiles/{profile['id']}/research-record-bind",
                json={"record_id": "consult-compatible", "expected_version": profile["version"]},
            )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["profile"]
        self.assertEqual(updated["research_source"], "advanced_record_reviewed")
        self.assertEqual(updated["research_version"], 2)
        self.assertIn("2025年：完成合成项目交付", updated["research_context"])
        self.assertIn("历史高级研究参考·非事实参考", updated["research_context"])
        self.assertIn("[手机号已省略]", updated["research_context"])
        self.assertNotIn("不应导入的逐年断语", updated["research_context"])
        self.assertNotIn("不应导入的裁判细节", updated["research_context"])
        facts, reference = backend_app._app_research_parts(updated)
        self.assertEqual(facts, "2025年：完成合成项目交付")
        self.assertIn("历史高级研究参考·非事实参考", reference)

        mismatch = {**synthetic_record, "birth": "1994-04-05T10:20"}
        with patch.object(backend_app.records, "get", return_value=mismatch):
            rejected = self.client.post(
                f"/api/app/profiles/{profile['id']}/research-record-bind",
                json={"record_id": "consult-other", "expected_version": updated["version"]},
            )
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("出生时间不一致", rejected.json()["error"])

    def test_question_job_locks_structured_snapshot_and_review_is_separate(self) -> None:
        created = self.client.post("/api/app/profiles", json={
            "name": "问事合成盘", "birth": "1991-02-03T09:15", "gender": "female",
            "place": "合成城市", "longitude": 116.4, "timezone": "Asia/Shanghai",
            "zi_hour_mode": "split", "is_active": True,
            "research_context": "2024年：开始负责合成团队，联系电话13800138000",
            "research_source": "advanced_dossier_reviewed",
        }).json()["profile"]
        pillar_output = {
            key: {"ganzhi": value} for key, value in
            {"year": "庚午", "month": "己丑", "day": "甲辰", "hour": "己巳"}.items()
        }
        fake_transit = {"output": pillar_output, "meta": {"sources": "合成历源"}}
        fake_consultation = {
            "ok": True,
            "chart": {"output": pillar_output},
            "consultation": {
                "consultation_id": "consult-synthetic", "manifest_id": "consult-synthetic",
                "arm": "S1",
                "debaters": [{"provider": "synthetic", "model": "model-v1", "claims": [
                    {"claim": "本月事业事项或有推进，但应以实际反馈为准"}
                ]}],
                "plain_summary": {"overview": "合成综述", "domains": [{
                    "domain": "事业方向", "reading": "本月事业事项或有推进，但应以实际反馈为准",
                    "tendency": "favorable", "confidence": "medium",
                }]},
            },
        }
        captured = {}

        def fake_run_consult(req, **kwargs):
            captured["request"] = req
            captured["kwargs"] = kwargs
            return fake_consultation

        with patch.object(backend_app, "_app_transit", return_value=(fake_transit, None)), \
             patch.object(backend_app, "_run_consult_payload", side_effect=fake_run_consult):
            started = self.client.post("/api/app/questions/start", json={
                "profile_id": created["id"], "period": "month", "category": "career",
                "question": "本月合成岗位事项是否适合继续推进？", "background": "只有合成背景",
            })
            self.assertEqual(started.status_code, 202)
            job_id = started.json()["job_id"]
            result = None
            for _ in range(30):
                result = self.client.get("/api/consult/result", params={"job_id": job_id}).json()
                if result.get("status") != "running":
                    break
                time.sleep(0.02)
        self.assertEqual(result["status"], "done")
        prediction = result["result"]["prediction"]
        snapshot = prediction["snapshot"]
        self.assertEqual(snapshot["schema_version"], "prediction-snapshot-v1")
        self.assertEqual(snapshot["question"], "本月合成岗位事项是否适合继续推进？")
        self.assertTrue(snapshot["key_time_windows"])
        self.assertFalse(captured["kwargs"]["include_dossier"])
        self.assertIn("本人已确认事实资料", captured["request"].situation)
        self.assertNotIn("13800138000", captured["request"].situation)
        self.assertIn("[手机号已省略]", captured["request"].situation)
        self.assertTrue(snapshot["research_context"]["included"])
        self.assertEqual(snapshot["research_context"]["profile_research_version"], 1)
        self.assertEqual(len(snapshot["research_context"]["content_hash"]), 64)
        self.assertIn("2024年：开始负责合成团队", snapshot["research_context"]["facts"])
        self.assertEqual(snapshot["research_context"]["historical_reference"], "")
        self.assertTrue(prediction["content_hash"])

        reviewed = self.client.post(f"/api/app/predictions/{prediction['id']}/review", json={
            "outcome": "unclear", "actual_at": None, "result": "时间窗尚无足够事实", "note": "合成复盘",
        })
        self.assertEqual(reviewed.status_code, 201)
        self.assertEqual(reviewed.json()["prediction"]["snapshot"]["conclusion"],
                         snapshot["conclusion"])
        self.assertEqual(reviewed.json()["prediction"]["review"]["outcome"], "unclear")


if __name__ == "__main__":
    unittest.main()
