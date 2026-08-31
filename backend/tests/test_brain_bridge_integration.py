"""Actual bridge HTTP schema -> App client -> one-use inquiry, synthetic databases only."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "consult-engine"))
import brain_context as brain
import decision_desk
import personal_app
from integrations.huohuo_bridge.config import BridgeConfig, ScopeCfg
from integrations.huohuo_bridge.service import create_app
from integrations.huohuo_bridge.source import SqlAlchemySource

TOKEN = "synthetic-bridge-integration-test-0000"


class BridgeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = "sqlite:///" + str(Path(self.tmp.name) / "synthetic-brain.sqlite3")
        engine = create_engine(db)
        with engine.begin() as con:
            con.execute(text("CREATE TABLE knowledge_items(id TEXT, content TEXT, knowledge_layer TEXT, confidentiality_level TEXT, project_id TEXT, verified_by_owner BOOLEAN, source_system TEXT, created_at TIMESTAMP)"))
            con.execute(text("CREATE TABLE revenue_snapshots(id TEXT, period_type TEXT, period_key TEXT, entity_type TEXT, entity_id TEXT, revenue_amount REAL, currency TEXT, synced_at TIMESTAMP)"))
            now = datetime.now(timezone.utc).isoformat()
            for kid, project, level in (("synthetic-k", "p-test", "L2"), ("foreign-k", "p-foreign", "L2"), ("private-k", "p-test", "L5")):
                con.execute(text("INSERT INTO knowledge_items VALUES(:id,:body,'company_reference',:level,:project,1,'manual',:now)"),
                            {"id": kid, "body": "原文哨兵-" + kid, "level": level, "project": project, "now": now})
            for group, amount in (("g-a", 12.5), ("g-b", 10.25), ("g-foreign", 999)):
                con.execute(text("INSERT INTO revenue_snapshots VALUES(:id,'monthly','2026-08','group',:id,:amount,'CNY',:now)"),
                            {"id": group, "amount": amount, "now": now})
        engine.dispose()
        cfg = BridgeConfig(TOKEN, {"synthetic-scope": ScopeCfg("合成授权范围", "p-test", ("g-a", "g-b"))}, db)
        self.source = SqlAlchemySource(db)
        self.bridge = TestClient(create_app(cfg, self.source))
        def forward(req):
            res = self.bridge.get(req.url.raw_path.decode(), headers={"authorization": req.headers["authorization"]})
            return httpx.Response(res.status_code, content=res.content, headers=res.headers)
        client = brain.BrainClient("http://127.0.0.1:8793", TOKEN, httpx.MockTransport(forward))
        self.app = personal_app.AppStore(Path(self.tmp.name) / "synthetic-app.sqlite3", None)
        self.desk = decision_desk.DeskStore(self.app)
        self.person = self.app.create_profile({"name": "合成主体", "birth": "1990-06-15T08:30", "gender": "male", "timezone": "Asia/Shanghai", "zi_hour_mode": "split"})
        self.co = self.desk.save_company({"name": "合成公司", "industry": "合成", "context": ""})
        self.service = brain.BrainStore(self.app, client)
        self.service.bind(self.co["id"], "", "synthetic-scope", 0)

    def tearDown(self):
        self.bridge.close()
        self.source._engine.dispose()
        self.tmp.cleanup()

    def test_round_trip_excludes_foreign_and_l5_and_persists_only_approved_summary(self):
        preview = self.service.preview(self.co["id"], "", "2026-08")
        self.assertEqual({i["id"] for i in preview["items"]}, {"knowledge:synthetic-k", "revenue:2026-08:CNY"})
        self.assertIn("22.75 CNY", next(i["text"] for i in preview["items"] if i["kind"] == "revenue"))
        approved = self.service.confirm(preview["id"], {"knowledge:synthetic-k": "已经人工核对的合成业务摘要"}, True)
        scope = {"scene": "company", "company": self.co, "project": None}
        inquiry = self.app.create_inquiry(self.person["id"], "month", "career", "合成项目如何推进", "",
                                         "2026-08-31", "2026-08-01", "2026-08-31", scope, approved["id"], "2026-08")
        frozen = brain.canonical(inquiry)
        self.assertIn("已经人工核对的合成业务摘要", frozen)
        for private in ("原文哨兵", "22.75", "foreign-k", "g-a", "g-b", TOKEN):
            self.assertNotIn(private, frozen)
        self.assertEqual(scope["brain_snapshot"]["content_hash"], approved["content_hash"])

    def test_missing_month_is_marked_incomplete_never_zero_or_cached(self):
        preview = self.service.preview(self.co["id"], "", "2026-07")
        self.assertFalse(preview["coverage"]["revenue_complete"])
        self.assertEqual(preview["coverage"]["revenue_missing_groups"], 2)
        self.assertFalse(any(i["kind"] == "revenue" for i in preview["items"]))


if __name__ == "__main__":
    unittest.main()
