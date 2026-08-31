"""Synthetic-only isolation and migration checks for the decision desk."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
import decision_desk
import personal_app
from backend.decision_routes import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def person(name):
    return {"name": name, "birth": "1990-06-15T08:30", "gender": "male",
            "timezone": "Asia/Shanghai", "zi_hour_mode": "split"}


class DecisionDeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "synthetic.sqlite3"
        self.app = personal_app.AppStore(self.path, None)
        self.desk = decision_desk.DeskStore(self.app)
        self.a = self.app.create_profile(person("合成主体甲"))
        self.b = self.app.create_profile(person("合成主体乙"))
        self.co = self.desk.save_company({"name": "合成公司甲", "industry": "测试", "context": "合成阶段"})
        self.other = self.desk.save_company({"name": "合成公司乙", "industry": "测试", "context": "无关背景"})

    def tearDown(self):
        self.tmp.cleanup()

    def member(self, profile=None, company=None, **overrides):
        return self.desk.save_membership((company or self.co)["id"], {
            "profile_id": (profile or self.a)["id"], "project_id": "", "role": "合成负责人",
            "consent_confirmed": True, "starts_on": "2026-01-01", "ends_on": "2026-12-31",
            **overrides,
        })

    def scope(self, members, **overrides):
        values = {"profile_id": self.a["id"], "scene": "company", "company_id": self.co["id"],
                  "membership_ids": [m["id"] for m in members], "as_of": "2026-08-31", **overrides}
        return self.desk.resolve_scope(**values)

    def test_personal_scope_never_uses_active_profile_or_company(self):
        self.desk.append_event(self.a["id"], "2026-08-01", "甲的合成事件")
        self.desk.append_event(self.b["id"], "2026-08-02", "乙的合成事件")
        scope, profiles = self.desk.resolve_scope(self.b["id"], "personal")
        self.assertEqual([p["id"] for p in profiles], [self.b["id"]])
        self.assertEqual(scope["events"][0]["content"], "乙的合成事件")
        self.assertIsNone(scope["company"])
        with self.assertRaises(decision_desk.ScopeError):
            self.desk.resolve_scope(self.b["id"], "personal", self.co["id"])

    def test_company_members_require_consent_dates_and_primary(self):
        m = self.member(consent_confirmed=False)
        with self.assertRaisesRegex(decision_desk.ScopeError, "授权"):
            self.scope([m])
        values = {**m, "consent_confirmed": True, "ends_on": "2026-08-30"}
        m = self.desk.save_membership(self.co["id"], values, m["version"])
        with self.assertRaisesRegex(decision_desk.ScopeError, "日期"):
            self.scope([m])
        m = self.desk.save_membership(self.co["id"], {**m, "ends_on": "2026-08-31"}, m["version"])
        self.assertEqual(len(self.scope([m])[1]), 1)
        second = self.member(self.b)
        with self.assertRaisesRegex(decision_desk.ScopeError, "主参考人"):
            self.scope([second])
        with self.assertRaisesRegex(decision_desk.ScopeError, "重复"):
            self.scope([m, m])

    def test_cross_company_and_cross_project_are_rejected(self):
        foreign = self.member(company=self.other)
        with self.assertRaises(decision_desk.ScopeError):
            self.scope([foreign])
        project = self.desk.save_project(self.co["id"], {"name": "合成项目", "context": "测试"})
        project_member = self.member(project_id=project["id"])
        with self.assertRaises(decision_desk.ScopeError):
            self.scope([project_member])
        scope, _ = self.scope([project_member], project_id=project["id"])
        self.assertEqual(scope["project"]["id"], project["id"])
        with self.assertRaises(decision_desk.ScopeError):
            self.desk.save_project(self.other["id"], {"name": "越界", "context": ""}, project["id"], 1)

    def test_duplicate_person_with_company_and_project_roles_is_rejected(self):
        project = self.desk.save_project(self.co["id"], {"name": "合成项目", "context": ""})
        with self.assertRaisesRegex(decision_desk.ScopeError, "同一人"):
            self.scope([self.member(), self.member(project_id=project["id"])], project_id=project["id"])

    def test_related_person_and_project_version_changes_require_reconfirmation(self):
        project = self.desk.save_project(self.co["id"], {"name": "合成项目", "context": ""})
        first, second = self.member(), self.member(self.b)
        expected = {m["id"]: {"version": 1, "profile_version": 1} for m in (first, second)}
        self.scope([first, second], expected_memberships=expected)
        self.app.update_profile(self.b["id"], 1, {"name": "更新合成乙"})
        with self.assertRaisesRegex(decision_desk.ScopeError, "已更新"):
            self.scope([first, second], expected_memberships=expected)
        self.desk.save_project(self.co["id"], {"name": "合成项目", "context": "新版"}, project["id"], 1)
        with self.assertRaisesRegex(decision_desk.ScopeError, "项目资料已更新"):
            self.scope([first], project_id=project["id"], expected_project_version=1)

    def test_frozen_scope_survives_later_edits_and_omits_private_events(self):
        self.desk.append_event(self.a["id"], "2026-08-01", "不得混入的个人私事")
        m = self.member()
        scope, profiles = self.scope([m], expected_profile_version=1, expected_company_version=1)
        self.app.update_profile(self.a["id"], 1, {"name": "合成新版名称"})
        self.desk.save_company({**self.co, "context": "新版公司背景"}, self.co["id"], 1)
        self.assertEqual(profiles[0]["name"], "合成主体甲")
        self.assertEqual(scope["company"]["context"], "合成阶段")
        self.assertEqual(scope["events"], [])
        with self.assertRaisesRegex(decision_desk.ScopeError, "已更新"):
            self.scope([m], expected_profile_version=1)
        with self.assertRaises(decision_desk.ScopeError):
            self.scope([m], expected_company_version=1)
        with self.assertRaises(decision_desk.ScopeError):
            self.desk.save_company(self.co, self.co["id"], 1)

    def test_events_are_append_only_and_api_rejects_future_or_unconfirmed(self):
        local = FastAPI(); local.include_router(router(self.app))
        client = TestClient(local)
        url = f"/api/app/profiles/{self.a['id']}/events"
        self.assertEqual(client.post(url, json={"occurred_on": "2026-01-01", "content": "合成事实"}).status_code, 422)
        self.assertEqual(client.post(url, json={"occurred_on": "2999-01-01", "content": "未发生", "confirmed": True}).status_code, 409)
        event = client.post(url, json={"occurred_on": "2026-01-01", "content": "合成事实", "confirmed": True}).json()["event"]
        self.assertTrue(event["known_at"])
        for sql in ("UPDATE profile_events SET content='更改' WHERE id=?", "DELETE FROM profile_events WHERE id=?"):
            with self.assertRaises(sqlite3.IntegrityError), self.app._connect() as con:
                con.execute(sql, (event["id"],))

    def prediction(self, scope):
        inquiry = self.app.create_inquiry(self.a["id"], "day", "career", "合成独立测试问题", "",
                                          "2026-08-01T00:00:00+00:00", "2026-08-01", "2026-08-01", scope)
        return self.app.lock_prediction(inquiry["id"], self.a["id"], {"conclusion": "合成内容", "scope": scope},
                                        "test", "test", "test", "test", .4)

    def test_company_reviews_are_not_personal_calibration(self):
        scope, _ = self.scope([self.member()])
        prediction = self.prediction(scope)
        self.app.add_review(prediction["id"], "hit", None, "合成回访", "")
        self.assertEqual(len(self.app.list_predictions(scene="company", company_id=self.co["id"])), 1)
        self.assertEqual(self.app.list_predictions(scene="personal"), [])
        self.assertEqual(self.app.stats(self.a["id"])["overall"]["sample_size"], 0)

    def test_v2_migration_preserves_hashes_snapshots_reviews_and_is_repeatable(self):
        prediction = self.prediction({"scene": "personal"})
        self.app.add_review(prediction["id"], "partial", None, "合成回访", "")
        with self.app._connect() as con:
            original = tuple(con.execute("SELECT snapshot_json,content_hash FROM prediction_snapshots").fetchone())
            # Strip only v3 additions in this disposable synthetic fixture.
            con.execute("DROP INDEX inquiry_company")
            for column in ("scene", "company_id", "project_id", "scope_json"):
                con.execute(f"ALTER TABLE inquiries DROP COLUMN {column}")
            for table in ("company_memberships", "company_projects", "companies", "profile_events"):
                con.execute(f"DROP TABLE {table}")
            con.execute("UPDATE app_meta SET value='2' WHERE key='schema_version'")
        personal_app.AppStore(self.path, None)
        migrated = personal_app.AppStore(self.path, None)
        with migrated._connect() as con:
            self.assertEqual(tuple(con.execute("SELECT snapshot_json,content_hash FROM prediction_snapshots").fetchone()), original)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM profiles").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM prediction_reviews").fetchone()[0], 1)
        self.assertEqual(migrated.get_prediction(prediction["id"])["review"]["outcome"], "partial")
        self.assertEqual(len(migrated.list_predictions(scene="personal")), 1)


if __name__ == "__main__":
    unittest.main()
