"""Synthetic-only security, protocol, migration and replay tests."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "consult-engine"))
import brain_context as brain
import decision_desk
import personal_app
from backend import brain_routes

TEST_TOKEN = "synthetic-test-access-not-a-secret-0000"


def packet(scope="synthetic-scope", period="2026-08"):
    now = brain.stamp().isoformat()
    return {"ok": True, "schema_version": brain.SCHEMA, "scope_id": scope, "period": period,
            "fetched_at": now, "coverage": {"knowledge_truncated": False, "revenue_complete": True, "revenue_missing_groups": 0},
            "items": [{"id": "knowledge:synthetic", "kind": "knowledge", "scope_id": scope, "level": "L2",
                       "known_at": now, "text": "合成公司来源原文哨兵", "source_system": "manual", "verification": "source_marked_verified"},
                      {"id": "revenue:2026-08:CNY", "kind": "revenue", "scope_id": scope, "level": "L4",
                       "known_at": now, "text": "合成敏感流水原文哨兵", "source_system": "brain.revenue_snapshots",
                       "verification": "provider_reported_not_audited"}]}


class SyntheticClient:
    def scopes(self):
        return [{"id": "synthetic-scope", "label": "合成授权范围"}]

    def context(self, scope_id, period):
        return brain.validate_context(packet(scope_id, period), scope_id, period)


class ProtocolTest(unittest.TestCase):
    def test_loopback_only_no_credentials_or_proxy_and_get_only(self):
        for url in ("https://example.test", "http://localhost:8793", "http://127.0.0.1:8793/x",
                    "http://127.0.0.1:8793?x=y", "http://user:pw@127.0.0.1:8793", "http://127.0.0.1:bad", "http://127.0.0.2:8793"):
            self.assertFalse(brain.BrainClient(url, TEST_TOKEN).configured(), url)
        calls = []
        def reply(request):
            calls.append(request)
            return httpx.Response(200, json={"ok": True, "schema_version": brain.SCHEMA, "scopes": []})
        client = brain.BrainClient("http://127.0.0.1:8793", TEST_TOKEN, httpx.MockTransport(reply))
        with patch.dict(os.environ, {"HTTP_PROXY": "http://bad.invalid", "HTTPS_PROXY": "http://bad.invalid"}):
            self.assertEqual(client.scopes(), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].method, "GET")
        self.assertEqual(calls[0].headers["authorization"], "Bearer " + TEST_TOKEN)

    def test_unconfigured_redirect_errors_oversize_and_malformed_fail_closed(self):
        self.assertFalse(brain.BrainClient(token="").configured())
        for response in (httpx.Response(302, headers={"location": "http://example.test"}),
                         httpx.Response(503, text="private-dsn-sentinel"), httpx.Response(200, text="broken"),
                         httpx.Response(200, content=b"x" * (brain.MAX_RESPONSE + 1))):
            calls = []
            def reply(req):
                calls.append(req); return response
            client = brain.BrainClient("http://127.0.0.1:8793", TEST_TOKEN, httpx.MockTransport(reply))
            with self.assertRaises(brain.BrainError) as caught:
                client.scopes()
            self.assertNotIn("private-dsn", str(caught.exception))
            self.assertEqual(len(calls), 1)

    def test_levels_scope_origin_duplicate_time_and_coverage_fail_closed(self):
        changes = [("level", "L5"), ("level", "unknown"), ("scope_id", "foreign"),
                   ("kind", "unknown"), ("source_system", "SanJian-derived"),
                   ("verification", "guess"), ("known_at", "2026-08-01"),
                   ("known_at", (brain.stamp() + timedelta(days=1)).isoformat())]
        for key, value in changes:
            data = packet(); data["items"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(brain.BrainError):
                brain.validate_context(data, "synthetic-scope", "2026-08")
        for change in (lambda d: d.update(scope_id="other"), lambda d: d.update(period="2026-09"),
                       lambda d: d.update(fetched_at=(brain.stamp() - timedelta(hours=1)).isoformat()),
                       lambda d: d["items"].append(d["items"][0]),
                       lambda d: d["items"][1].update(level="L2"),
                       lambda d: d["coverage"].update(revenue_complete=False, revenue_missing_groups=1)):
            data = packet(); change(data)
            with self.assertRaises(brain.BrainError): brain.validate_context(data, "synthetic-scope", "2026-08")


class BrainStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = personal_app.AppStore(Path(self.tmp.name) / "synthetic.sqlite3", None)
        self.desk = decision_desk.DeskStore(self.app)
        self.profile = self.app.create_profile({"name": "合成甲", "birth": "1990-06-15T08:30", "gender": "male", "timezone": "Asia/Shanghai", "zi_hour_mode": "split"})
        self.company = self.desk.save_company({"name": "合成公司", "industry": "测试", "context": ""})
        self.service = brain.BrainStore(self.app, SyntheticClient())
        self.service.bind(self.company["id"], "", "synthetic-scope", 0)

    def tearDown(self):
        self.tmp.cleanup()

    def approve(self):
        preview = self.service.preview(self.company["id"], "", "2026-08")
        return self.service.confirm(preview["id"], {"knowledge:synthetic": "合成去标识必要摘要"}, True)

    def inquiry(self, snapshot_id, scope=None, period="2026-08"):
        if scope is None:
            scope = {"scene": "company", "company": self.company, "project": None}
        return self.app.create_inquiry(self.profile["id"], "month", "career", "合成问题如何推进", "", "2026-08-31T00:00:00Z",
                                       "2026-08-01", "2026-08-31", scope, snapshot_id, period)

    def test_auth_precedes_preview_binding_and_confirm_and_disables_cache(self):
        app = FastAPI(); app.include_router(brain_routes.router(self.service))
        with TestClient(app) as client, patch.dict(os.environ, {"SANJIAN_BRAIN_ACCESS_TOKEN": TEST_TOKEN}):
            for url in ("scopes", "binding?company_id=" + self.company["id"]):
                self.assertEqual(client.get("/api/app/brain/" + url).status_code, 401)
            for url in ("binding", "preview", "confirm"):
                self.assertEqual(client.post("/api/app/brain/" + url, json={}).status_code, 401)
            response = client.get("/api/app/brain/scopes", headers={"X-Sanjian-Brain-Access": TEST_TOKEN})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn(TEST_TOKEN, response.text)
            for invalid_month in ("2026-08\n", "２０２６-08", "2026-13"):
                response = client.post("/api/app/brain/preview",
                                       headers={"X-Sanjian-Brain-Access": TEST_TOKEN},
                                       json={"company_id": self.company["id"], "period": invalid_month})
                self.assertEqual(response.status_code, 422)

    def test_reject_sensitive_unselected_unconfirmed_and_contact_summaries(self):
        preview = self.service.preview(self.company["id"], "", "2026-08")
        for summaries, consent in (({"revenue:2026-08:CNY": "敏感流水"}, True),
                                   ({"wrong-id": "错误来源"}, True), ({}, True),
                                   ({"knowledge:synthetic": "合成摘要"}, False),
                                   ({"knowledge:synthetic": "联系13800138000"}, True)):
            with self.assertRaises(brain.BrainError): self.service.confirm(preview["id"], summaries, consent)

    def test_only_minimized_summaries_persist_never_raw_l2_l4(self):
        approval = self.approve()
        inquiry = self.inquiry(approval["id"])
        content = brain.canonical(inquiry)
        self.assertIn("合成去标识必要摘要", content)
        for raw in ("合成公司来源原文哨兵", "合成敏感流水原文哨兵", "knowledge:synthetic"):
            self.assertNotIn(raw, content)
            with self.app._connect() as con:
                self.assertNotIn(raw, con.execute("SELECT snapshot_json FROM brain_snapshots").fetchone()[0])
        self.assertEqual(inquiry["scope"]["brain_snapshot"]["content_hash"], approval["content_hash"])
        with self.assertRaises(sqlite3.IntegrityError), self.app._connect() as con:
            con.execute("UPDATE brain_snapshots SET content_hash='bad'")

    def test_single_use_atomic_under_concurrency_and_failure_rolls_back_inquiry(self):
        approval = self.approve()
        def run(_):
            try: return self.inquiry(approval["id"])["id"]
            except brain.BrainError: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(sum(bool(r) for r in results), 1)
        with self.app._connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM inquiries").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM brain_uses").fetchone()[0], 1)

    def test_scene_period_project_and_company_cannot_be_reused(self):
        approval = self.approve()
        for scope, period in (({"scene": "personal"}, "2026-08"),
                              ({"scene": "company", "company": {**self.company, "id": "wrong"}}, "2026-08"),
                              ({"scene": "company", "company": self.company, "project": {"id": "wrong", "version": 1}}, "2026-08"),
                              (None, "2026-09")):
            with self.assertRaises(brain.BrainError): self.inquiry(approval["id"], scope, period)
        self.inquiry(approval["id"])

    def test_rebinding_company_changes_and_expiry_invalidate_preview_and_approval(self):
        preview = self.service.preview(self.company["id"], "", "2026-08")
        self.service.bind(self.company["id"], "", "synthetic-scope", 1)
        with self.assertRaises(brain.BrainError): self.service.confirm(preview["id"], {"knowledge:synthetic": "合成摘要"}, True)
        approval = self.approve()
        future = brain.stamp() + timedelta(minutes=11)
        with patch.object(brain, "stamp", return_value=future), self.assertRaises(brain.BrainError): self.inquiry(approval["id"])
        self.desk.save_company({**self.company, "context": "合成新版"}, self.company["id"], 1)
        with self.assertRaises(brain.BrainError): self.inquiry(approval["id"])

    def test_unknown_scope_cross_project_binding_and_version_conflict_rejected(self):
        for args in ((self.company["id"], "wrong", "synthetic-scope", 0),
                     (self.company["id"], "", "wrong", 1),
                     (self.company["id"], "", "synthetic-scope", 0)):
            with self.assertRaises(brain.BrainError): self.service.bind(*args)

    def test_v3_upgrade_is_repeatable_and_v4_rejects_downgrade(self):
        self.app.create_inquiry(self.profile["id"], "day", "career", "历史合成问题", "", "2026-01-01", "2026-01-01", "2026-01-01")
        with self.app._connect() as con:
            con.execute("UPDATE app_meta SET value='3' WHERE key='schema_version'")
            con.execute("DROP TABLE brain_uses"); con.execute("DROP TABLE brain_snapshots"); con.execute("DROP TABLE brain_bindings")
        upgraded = personal_app.AppStore(self.app.db_path, None)
        personal_app.AppStore(self.app.db_path, None)
        with upgraded._connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM inquiries").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0], "4")
        with patch.object(personal_app, "SCHEMA_VERSION", 3), self.assertRaisesRegex(RuntimeError, "降级"):
            personal_app.AppStore(self.app.db_path, None)


if __name__ == "__main__":
    unittest.main()
