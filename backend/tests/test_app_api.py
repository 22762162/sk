from __future__ import annotations

import json
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
    def test_native_auth_compatibility_path_redirects_to_authenticated_shell(self):
        response = self.client.get("/__native_auth", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")

    def test_scope_confirmation_and_personal_injection_fail_before_any_model_call(self):
        profile = self.client.post("/api/app/profiles", json={
            "name": "合成隔离主体", "birth": "1990-06-15T08:30", "gender": "male",
        }).json()["profile"]
        base = {"profile_id": profile["id"], "period": "day", "category": "career", "question": "合成测试工作如何推进"}
        with patch.object(backend_app, "_run_consult_payload") as call:
            self.assertEqual(self.client.post("/api/app/questions/start", json=base).status_code, 422)
            self.assertEqual(self.client.post("/api/app/questions/start", json={
                **base, "scope_confirmed": True, "scene": "personal", "company_id": "wrong-company",
            }).status_code, 422)
            call.assert_not_called()

    def test_company_packet_is_minimized_and_excludes_personal_context(self):
        from backend.tests.test_brain_context import SyntheticClient, TEST_TOKEN
        profile = self.client.post("/api/app/profiles", json={
            "name": "合成隔离甲", "birth": "1990-06-15T08:30", "gender": "male",
            "situation": "个人私事哨兵", "research_context": "个人旧研究哨兵",
        }).json()["profile"]
        company = self.client.post("/api/app/companies", json={
            "name": "合成匿名公司", "context": "合成隔离甲负责合成匿名公司，电话13800138000；已完成阶段验收",
        }).json()["company"]
        member = self.client.post(f"/api/app/companies/{company['id']}/memberships", json={
            "profile_id": profile["id"], "role": "合成负责人", "consent_confirmed": True,
        }).json()["membership"]
        brain_service = backend_app.brain_context.BrainStore(backend_app.APP_STORE, SyntheticClient())
        brain_service.bind(company["id"], "", "synthetic-scope", 0)
        preview = brain_service.preview(company["id"], "", backend_app.datetime.now(backend_app.TZ).strftime("%Y-%m"))
        approval = brain_service.confirm(preview["id"], {"knowledge:synthetic": "合成隔离甲负责合成匿名公司，已核对进度哨兵"}, True)
        captured = {}
        def stop_after_capture(req, **kwargs):
            captured["situation"] = req.situation
            captured["context"] = kwargs["decision_context"]
            return {"ok": False, "error": "合成停止（未调用模型）"}
        with patch.object(backend_app, "_run_consult_payload", side_effect=stop_after_capture), \
             patch.object(backend_app, "_app_transit", return_value=({"output": {}}, None)), \
             patch.object(backend_app, "_desk_chart", return_value={"pillars": {"day": "甲子"}}), \
             patch.dict(os.environ, {"SANJIAN_BRAIN_ACCESS_TOKEN": TEST_TOKEN}):
            rejected = self.client.post("/api/app/questions/start", json={
                "profile_id": profile["id"], "period": "month", "category": "career",
                "question": "合成未授权不能调用", "brain_snapshot_id": approval["id"],
            })
            self.assertEqual(rejected.status_code, 401)
            started = self.client.post("/api/app/questions/start", json={
                "profile_id": profile["id"], "period": "month", "category": "career",
                "question": "合成匿名公司本月的项目如何推进", "scene": "company",
                "company_id": company["id"], "membership_ids": [member["id"]], "scope_confirmed": True,
                "brain_snapshot_id": approval["id"],
            }, headers={"X-Sanjian-Brain-Access": TEST_TOKEN})
            self.assertEqual(started.status_code, 202)
            for _ in range(100):
                result = self.client.get("/api/consult/result", params={"job_id": started.json()["job_id"]}).json()
                if result["status"] != "running": break
                time.sleep(.01)
        text = json.dumps(captured, ensure_ascii=False)
        for forbidden in (profile["name"], profile["id"], profile["birth"], company["name"], company["id"], "13800138000", "个人私事哨兵", "个人旧研究哨兵"):
            self.assertNotIn(forbidden, text)
        self.assertIn("已完成阶段验收", text)
        self.assertIn("已核对进度哨兵", text)
        for forbidden in ("合成敏感流水原文哨兵", "合成公司来源原文哨兵", "synthetic-scope", TEST_TOKEN):
            self.assertNotIn(forbidden, text)
        self.assertEqual(captured["context"]["brain_evidence"]["content_hash"], approval["content_hash"])
        self.assertEqual(captured["context"]["confirmed_personal_events"], [])
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.client.get("/api/app/predictions", params={"scene": "company", "company_id": company["id"]}).json()["predictions"], [])

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

    def test_three_role_guard_rejects_single_provider_or_missing_view(self) -> None:
        roles, protocol = backend_app._app_three_role_analysis({"debaters": [{
            "role": "debater_a", "provider": "anthropic", "model": "synthetic",
            "school": "ziping", "school_name": "子平格局派",
            "claims": [{"claim": "只有一个合成观点"}],
        }]})
        self.assertEqual(len(roles), 1)
        self.assertFalse(protocol["complete"])
        self.assertTrue(protocol["fail_closed"])

        direct_roles, direct_protocol = backend_app._app_three_role_analysis({
            "question_round": {"responses": [{
                "role": "debater_a", "provider": "anthropic", "model": "synthetic",
                "school": "ziping", "school_name": "子平格局派",
                "answer": "只讨论未来几年财运，没有回答合成任务。",
                "suggestion": "", "relevant_and_valid": False,
            }]},
        })
        self.assertEqual(len(direct_roles), 1)
        self.assertTrue(direct_protocol["direct_question"])
        self.assertFalse(direct_protocol["complete"])

    def test_business_metrics_relevance_and_ten_god_guards(self) -> None:
        question = ("这个月合成流水下滑，现在才120万人民币，目标达到5%要500万人民币。"
                    "现在这十天低于预期，后面20天能否完成任务？")
        metrics = backend_app._app_business_metrics(question, "2026-08-31")
        self.assertEqual(metrics["current"], 120.0)
        self.assertEqual(metrics["target"], 500.0)
        self.assertEqual(metrics["gap"], 380.0)
        self.assertEqual(metrics["required_daily"], 19.0)
        self.assertEqual(metrics["current_daily"], 12.0)
        self.assertEqual(metrics["required_lift_pct"], 58.33)
        self.assertEqual(metrics["completion_pct"], 24.0)
        self.assertIn("日均 19 万元", backend_app._app_metric_summary(metrics))

        self.assertFalse(backend_app._app_answer_relevant(
            "未来几年财气较旺，但合同细节需要留意。", question, metrics
        ))
        self.assertTrue(backend_app._app_answer_relevant(
            "按剩余缺口和日均要求看，完成任务难度较高，除非后续流水连续达标。",
            question, metrics,
        ))
        self.assertTrue(backend_app._app_answer_relevant(
            "这段关系本月更倾向先沟通再观察，对方态度仍需用实际互动核对。",
            "这段关系本月有什么变化，对方是什么想法？", {},
        ))
        self.assertTrue(backend_app._app_ten_god_text_valid(
            "火为财星，土为官杀，金为印星，木为食伤。", "壬"
        ))
        self.assertFalse(backend_app._app_ten_god_text_valid("财星土弱。", "壬"))
        self.assertFalse(backend_app._app_ten_god_text_valid("癸水克甲木。", "壬"))

    def test_question_round_directly_answers_and_drops_invalid_prior_claims(self) -> None:
        question = ("本月合成流水当前100万，目标300万，前10天低于预期，"
                    "剩余20天能否完成任务？")
        metrics = backend_app._app_business_metrics(question, "2026-08-31")
        payload = {
            "chart": {"line": "合成四柱", "output": {"day": {"stem": "壬", "ganzhi": "壬申"}}},
            "consultation": {
                "judge": {"by": "anthropic(轮换盲评)"},
                "debaters": [
                    {"role": "debater_a", "provider": "anthropic", "model": "claude-synthetic",
                     "school": "ziping", "school_name": "子平格局派",
                     "claims": [{"claim": "火为财星，任务需看现实节奏", "basis": "合成有效依据"}]},
                    {"role": "debater_b", "provider": "gemini", "model": "gemini-synthetic",
                     "school": "wangshuai", "school_name": "旺衰扶抑派",
                     "claims": [{"claim": "财星土弱", "basis": "合成错误依据"}]},
                    {"role": "debater_c", "provider": "deepseek", "model": "deepseek-synthetic",
                     "school": "tiaohou", "school_name": "调候派",
                     "claims": [{"claim": "后续节奏需要连续观察", "basis": "合成有效依据"}]},
                ],
            },
        }
        packets = {}

        def fake_direct(provider, model, system, user, **kwargs):
            packets[provider] = json.loads(user.split("\n", 1)[0])
            answers = {
                "anthropic": "按剩余目标和日均要求看，本月完成流水任务有条件，但需连续达标。",
                "gemini": "当前流水缺口明确，本月完成任务较难，除非剩余日均持续达到要求。",
                "deepseek": "本月流水仍有望完成，条件是后续进度不再低于剩余日均目标。",
            }
            return ({"answer": answers[provider], "revised": "", "suggestion": "每5天核对一次进度"},
                    f"run-{provider}", {})

        fake_judged = {"verdict": {"summary": "三方认为本月流水任务有条件完成。",
                                    "issues": [{"topic": "达标条件", "verdict": "consensus",
                                                "rationale": "均要求日均达到目标"}]},
                       "run_id": "run-judge"}
        inquiry = {"question": question, "period": "month", "category": "finance", "background": ""}
        with patch.object(backend_app.consult, "_call_json", side_effect=fake_direct), \
             patch.object(backend_app.consult, "_judge", return_value=fake_judged):
            result = backend_app._app_run_question_round(payload, inquiry, metrics)

        self.assertEqual(len(result["responses"]), 3)
        self.assertTrue(all(item["relevant_and_valid"] for item in result["responses"]))
        self.assertEqual(
            packets["gemini"]["independent_role"]["valid_prior_observations"], []
        )
        self.assertEqual(result["judge"]["summary"], "三方认为本月流水任务有条件完成。")

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
                "arm": "D3J",
                "debaters": [
                    {"role": "debater_a", "provider": "anthropic", "model": "claude-synthetic",
                     "school": "ziping", "school_name": "子平格局派", "claims": [
                         {"claim": "子平视角提示事项或有推进", "basis": "合成依据甲"}]},
                    {"role": "debater_b", "provider": "gemini", "model": "gemini-synthetic",
                     "school": "wangshuai", "school_name": "旺衰扶抑派", "claims": [
                         {"claim": "旺衰视角建议观察现实条件", "basis": "合成依据乙"}]},
                    {"role": "debater_c", "provider": "deepseek", "model": "deepseek-synthetic",
                     "school": "tiaohou", "school_name": "调候派", "claims": [
                         {"claim": "调候视角提醒保留调整空间", "basis": "合成依据丙"}]},
                ],
                "judge": {"summary": "三方合成盲评摘要", "issues": [
                    {"verdict": "unresolved"},
                ]},
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

        def fake_question_round(payload, inquiry, metrics):
            self.assertEqual(payload, fake_consultation)
            self.assertEqual(metrics["current"], 100.0)
            self.assertEqual(metrics["target"], 300.0)
            self.assertEqual(metrics["required_daily"], 10.0)
            return {
                "schema_version": "app-question-round-v1",
                "question": inquiry["question"],
                "computed_business_metrics": metrics,
                "responses": [
                    {"role": "debater_a", "provider": "anthropic", "model": "claude-synthetic",
                     "school": "ziping", "school_name": "子平格局派",
                     "answer": "本月合成流水目标有条件完成，但需要保持剩余日均要求。",
                     "revised": "", "suggestion": "月末按是否完成目标复盘。",
                     "relevant_and_valid": True, "run_id": "run-a"},
                    {"role": "debater_b", "provider": "gemini", "model": "gemini-synthetic",
                     "school": "wangshuai", "school_name": "旺衰扶抑派",
                     "answer": "本月完成该流水任务有难度，应把剩余目标拆成可核对节点。",
                     "revised": "", "suggestion": "每周核对一次日均进度。",
                     "relevant_and_valid": True, "run_id": "run-b"},
                    {"role": "debater_c", "provider": "deepseek", "model": "deepseek-synthetic",
                     "school": "tiaohou", "school_name": "调候派",
                     "answer": "本月流水仍有望达标，前提是后续日均进度持续到位。",
                     "revised": "", "suggestion": "记录每日流水是否达到要求。",
                     "relevant_and_valid": True, "run_id": "run-c"},
                ],
                "judge": {"by": "anthropic(原问题轮换盲评)",
                          "summary": "三方均直接回答本月流水任务，结论是有条件达标。",
                          "issues": [{"verdict": "unresolved"}], "run_id": "run-j"},
            }

        with patch.object(backend_app, "_app_transit", return_value=(fake_transit, None)), \
             patch.object(backend_app, "_desk_chart", return_value={"pillars": {"day": "甲辰"}}), \
             patch.object(backend_app, "_run_consult_payload", side_effect=fake_run_consult), \
             patch.object(backend_app, "_app_run_question_round", side_effect=fake_question_round):
            started = self.client.post("/api/app/questions/start", json={
                "profile_id": created["id"], "period": "month", "category": "finance",
                "scope_confirmed": True,
                "question": ("本月合成流水当前100万，目标300万，前10天低于预期，"
                             "剩余20天能否完成任务？"),
                "background": "只有合成背景",
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
        self.assertEqual(snapshot["decision_material"]["scene"], "personal")
        self.assertEqual(snapshot["decision_scope"]["subject"]["id"], created["id"])
        self.assertIn("剩余20天能否完成任务", snapshot["question"])
        self.assertTrue(snapshot["key_time_windows"])
        self.assertFalse(captured["kwargs"]["include_dossier"])
        self.assertEqual(captured["request"].arm, "D3J")
        self.assertIn("本人已确认事实资料", captured["request"].situation)
        self.assertIn("确定性经营指标", captured["request"].situation)
        self.assertNotIn("13800138000", captured["request"].situation)
        self.assertIn("[手机号已省略]", captured["request"].situation)
        self.assertTrue(snapshot["research_context"]["included"])
        self.assertEqual(snapshot["research_context"]["profile_research_version"], 1)
        self.assertEqual(len(snapshot["research_context"]["content_hash"]), 64)
        self.assertIn("2024年：开始负责合成团队", snapshot["research_context"]["facts"])
        self.assertEqual(snapshot["research_context"]["historical_reference"], "")
        self.assertTrue(snapshot["three_role_protocol"]["complete"])
        self.assertEqual(snapshot["three_role_protocol"]["distinct_providers"], 3)
        self.assertEqual([r["provider_label"] for r in snapshot["three_role_analysis"]],
                         ["Claude", "Gemini", "DeepSeek"])
        self.assertTrue(snapshot["three_role_protocol"]["direct_question"])
        self.assertIn("三方盲评", snapshot["conclusion"])
        self.assertIn("有条件完成", snapshot["three_role_analysis"][0]["findings"][0]["claim"])
        self.assertEqual(snapshot["computed_metrics"]["completion_pct"], 33.33)
        self.assertEqual(snapshot["computed_metrics"]["gap"], 200.0)
        self.assertEqual(snapshot["arbitration"]["unresolved"], 1)
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
