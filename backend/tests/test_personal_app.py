from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
import personal_app  # noqa: E402


def profile_values(name: str, active: bool = False) -> dict:
    return {
        "name": name,
        "birth": "1990-06-15T08:30",
        "gender": "male",
        "place": "合成城市",
        "longitude": 116.4,
        "timezone": "Asia/Shanghai",
        "zi_hour_mode": "split",
        "industry": "测试行业",
        "occupation": "测试岗位",
        "situation": "合成背景",
        "is_active": active,
    }


class AppStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = personal_app.AppStore(Path(self.tmp.name) / "app.sqlite3", None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add_prediction(self, profile_id: str, index: int, confidence: float = 0.35) -> dict:
        inquiry = self.store.create_inquiry(
            profile_id, "day", "career", f"合成问题 {index}", "",
            f"2026-08-{index + 1:02d}T01:00:00+00:00",
            f"2026-08-{index + 1:02d}", f"2026-08-{index + 1:02d}",
        )
        return self.store.lock_prediction(
            inquiry["id"], profile_id,
            {"schema_version": "prediction-snapshot-v1", "conclusion": f"合成结论 {index}"},
            "app-test-v1", "model-test-v1", "none-v0",
            "personal-calibration-v1:insufficient", confidence,
        )

    def test_profiles_switch_and_optimistic_update(self) -> None:
        first = self.store.create_profile(profile_values("基本盘甲"))
        second = self.store.create_profile(profile_values("基本盘乙"))
        self.assertTrue(first["is_active"])
        self.assertFalse(second["is_active"])

        activated = self.store.activate_profile(second["id"])
        self.assertTrue(activated["is_active"])
        self.assertEqual(self.store.active_profile()["id"], second["id"])

        current = self.store.get_profile(second["id"])
        updated = self.store.update_profile(
            second["id"], current["version"], {**profile_values("已更新"), "is_active": True}
        )
        self.assertEqual(updated["name"], "已更新")
        with self.assertRaises(personal_app.StoreConflict):
            self.store.update_profile(
                second["id"], current["version"], profile_values("过期写入")
            )

    def test_confirmed_research_context_has_its_own_version(self) -> None:
        values = {
            **profile_values("研究资料基本盘"),
            "research_context": "2024年：开始负责合成业务团队",
            "research_source": "manual",
        }
        profile = self.store.create_profile(values)
        self.assertEqual(profile["research_version"], 1)
        self.assertTrue(profile["research_confirmed_at"])

        unchanged = self.store.update_profile(
            profile["id"], profile["version"], {**values, "name": "只改名称"}
        )
        self.assertEqual(unchanged["research_version"], 1)

        changed_values = {
            **values,
            "research_context": "2024年：开始负责合成业务团队\n2025年：完成合成项目交付",
            "research_source": "advanced_dossier_reviewed",
        }
        changed = self.store.update_profile(
            profile["id"], unchanged["version"], changed_values
        )
        self.assertEqual(changed["research_version"], 2)

        cleared = self.store.update_profile(
            profile["id"], changed["version"], {
                **changed_values, "research_context": "", "research_source": "",
            }
        )
        self.assertEqual(cleared["research_version"], 3)
        self.assertEqual(cleared["research_confirmed_at"], "")

    def test_v1_database_migrates_without_losing_profiles(self) -> None:
        legacy_db = Path(self.tmp.name) / "legacy-v1.sqlite3"
        with sqlite3.connect(legacy_db) as con:
            con.executescript(
                """
                CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO app_meta(key,value) VALUES('schema_version','1');
                CREATE TABLE profiles (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,birth TEXT NOT NULL,gender TEXT NOT NULL,
                    place TEXT NOT NULL DEFAULT '',longitude REAL,timezone TEXT NOT NULL,
                    zi_hour_mode TEXT NOT NULL,industry TEXT NOT NULL DEFAULT '',
                    occupation TEXT NOT NULL DEFAULT '',situation TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL
                );
                INSERT INTO profiles VALUES(
                    'profile-legacy','旧版合成盘','1990-06-15T08:30','male','合成城市',116.4,
                    'Asia/Shanghai','split','测试行业','测试岗位','合成背景',1,1,
                    '2026-08-01T00:00:00+00:00','2026-08-01T00:00:00+00:00'
                );
                """
            )
        migrated = personal_app.AppStore(legacy_db, None)
        profile = migrated.get_profile("profile-legacy")
        self.assertEqual(profile["name"], "旧版合成盘")
        self.assertEqual(profile["research_context"], "")
        self.assertEqual(profile["research_version"], 0)
        with sqlite3.connect(legacy_db) as con:
            version = con.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()[0]
        self.assertEqual(version, str(personal_app.SCHEMA_VERSION))

    def test_prediction_and_review_are_append_only(self) -> None:
        profile = self.store.create_profile(profile_values("基本盘"))
        prediction = self.add_prediction(profile["id"], 0)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._connect() as con:
                con.execute(
                    "UPDATE prediction_snapshots SET confidence=.9 WHERE id=?",
                    (prediction["id"],),
                )

        reviewed = self.store.add_review(
            prediction["id"], "partial", "2026-08-01T10:00", "合成结果", ""
        )
        self.assertEqual(reviewed["review"]["outcome"], "partial")
        with self.assertRaises(personal_app.StoreConflict):
            self.store.add_review(prediction["id"], "hit", None, "改判", "")

    def test_small_sample_is_suppressed_then_future_confidence_calibrates(self) -> None:
        profile = self.store.create_profile(profile_values("基本盘"))
        for index in range(7):
            prediction = self.add_prediction(profile["id"], index)
            self.store.add_review(prediction["id"], "hit", None, "合成结果", "")
        stats = self.store.stats(profile["id"])
        self.assertFalse(stats["overall"]["sufficient_sample"])
        self.assertIsNone(stats["overall"]["hit_rate"])
        self.assertFalse(self.store.calibration(profile["id"], "career", "day", 0.35)["adjusted"])

        prediction = self.add_prediction(profile["id"], 7)
        self.store.add_review(prediction["id"], "hit", None, "合成结果", "")
        stats = self.store.stats(profile["id"])
        self.assertTrue(stats["overall"]["sufficient_sample"])
        self.assertEqual(stats["overall"]["hit_rate"], 1.0)
        calibrated = self.store.calibration(profile["id"], "career", "day", 0.35)
        self.assertTrue(calibrated["adjusted"])
        self.assertGreater(calibrated["confidence"], 0.35)

    def test_legacy_predictions_are_imported_idempotently_without_rewrite(self) -> None:
        legacy = Path(self.tmp.name) / "predictions.jsonl"
        row = {
            "id": "pred-legacy-001", "created_at": "2026-07-14T00:00:00+00:00",
            "domain": "事业", "statement": "合成旧版预测", "window_start": "2026-07-01",
            "window_end": "2026-07-31", "status": "hit", "reviewed_at": "2026-08-01T00:00:00+00:00",
            "note": "合成复盘", "chart_line": "合成命盘", "chart_hash": "abc",
        }
        legacy.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        before = legacy.read_bytes()
        self.assertEqual(self.store.import_legacy_predictions(legacy), 1)
        self.assertEqual(self.store.import_legacy_predictions(legacy), 0)
        self.assertEqual(legacy.read_bytes(), before)
        imported = self.store.list_predictions()
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["snapshot"]["source"], "legacy_prediction")
        self.assertEqual(imported[0]["review"]["outcome"], "hit")


if __name__ == "__main__":
    unittest.main()
