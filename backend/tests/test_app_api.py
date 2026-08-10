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

    def test_question_job_locks_structured_snapshot_and_review_is_separate(self) -> None:
        created = self.client.post("/api/app/profiles", json={
            "name": "问事合成盘", "birth": "1991-02-03T09:15", "gender": "female",
            "place": "合成城市", "longitude": 116.4, "timezone": "Asia/Shanghai",
            "zi_hour_mode": "split", "is_active": True,
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
        with patch.object(backend_app, "_app_transit", return_value=(fake_transit, None)), \
             patch.object(backend_app, "_run_consult_payload", return_value=fake_consultation):
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
